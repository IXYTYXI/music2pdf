import json
from pathlib import Path
import tempfile
import unittest
from recording_collector import RecordingCollector


class Source:
    calls = 0
    fail = False
    def search(self, query, limit):
        self.calls += 1
        if self.fail: raise RuntimeError('Source temporarily unavailable')
        return {'candidates': [{'id': 'archive-abc123', 'provider': 'archive', 'title': 'Beethoven Symphony No. 5 Op.67 orchestra',
            'url': 'https://archive.org/download/test/track.mp3', 'source_url': 'https://archive.org/details/test',
            'extension': '.mp3', 'license': {'url': 'https://creativecommons.org/publicdomain/zero/1.0/', 'download_allowed': True},
            'access': 'downloadable'}], 'truncated': True}


class Download:
    def download(self, asset, path):
        import hashlib
        data = b'ID3' + b'0' * 20
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.work = self.root / 'imslp-1'
        self.work.mkdir()
        self.metadata = {'catalog': {'id': '1', 'title': 'Symphony No. 5 Op.67', 'composer': 'Beethoven, Ludwig van'},
                         'information': {'Instrumentation': 'orchestra'}}
        (self.work / 'metadata.json').write_text(json.dumps(self.metadata))
        self.source = Source()
        self.collector = RecordingCollector(self.root, {'archive': self.source}, Download())
        self.addCleanup(self.collector.close)

    def test_restart_deduplicates_and_preserves_imslp_metadata(self):
        self.collector.search(max_works=1)
        count = self.source.calls
        self.collector.search(max_works=1)
        self.assertEqual(self.source.calls, count)
        self.assertEqual(len(self.collector.candidates('imslp-1')), 1)
        self.assertEqual(json.loads((self.work/'metadata.json').read_text()), self.metadata)
        sidecar = json.loads((self.work/'recordings/metadata.json').read_text())
        self.assertTrue(sidecar['searches'][0]['truncated'])
        self.assertFalse(sidecar['training_ready'])

    def test_provider_failure_can_retry_without_duplicate_candidates(self):
        self.source.fail = True
        self.collector.search(max_works=1)
        self.assertEqual(self.collector.status()['searches'].get('failed'), 1)
        self.source.fail = False
        self.collector.search(max_works=1, retry=True)
        self.assertEqual(self.collector.status()['searches'].get('done'), 1)
        self.assertEqual(len(self.collector.candidates('imslp-1')), 1)

    def test_selection_required_and_download_has_provenance(self):
        self.collector.search(max_works=1)
        with self.assertRaises(ValueError):
            self.collector.download('imslp-1', 'archive-abc123', '')
        row = self.collector.download('imslp-1', 'archive-abc123', 'Checked work and orchestral version')
        self.assertEqual(row['state'], 'downloaded')
        self.assertTrue((self.root/row['path']).exists())
        self.assertFalse(row['match']['training_ready'])
        self.assertEqual(row['review_note'], 'Checked work and orchestral version')
        self.assertEqual(row, self.collector.download('imslp-1', 'archive-abc123', 'Recheck'))

    def test_unknown_license_cannot_download(self):
        self.collector.search(max_works=1)
        row = self.collector.db.execute('SELECT data FROM candidates').fetchone()
        value = json.loads(row[0]); value['license']['download_allowed'] = False
        with self.collector.db:
            self.collector.db.execute('UPDATE candidates SET data=?', (json.dumps(value),))
        with self.assertRaises(ValueError):
            self.collector.download('imslp-1', 'archive-abc123', 'Checked version')

    def test_corrupt_download_is_retried(self):
        self.collector.search(max_works=1)
        row = self.collector.download('imslp-1', 'archive-abc123', 'Checked')
        (self.root/row['path']).write_bytes(b'broken')
        row = self.collector.download('imslp-1', 'archive-abc123', 'Checked again')
        self.assertTrue((self.root/row['path']).read_bytes().startswith(b'ID3'))

    def test_corrupt_owned_file_can_recover_after_network_failure(self):
        self.collector.search(max_works=1)
        row = self.collector.download('imslp-1', 'archive-abc123', 'Checked')
        (self.root/row['path']).write_bytes(b'broken')
        from unittest.mock import patch
        with patch.object(self.collector.http, 'download', side_effect=RuntimeError('Network failed')):
            with self.assertRaises(RuntimeError):
                self.collector.download('imslp-1', 'archive-abc123', 'Retry')
        row = self.collector.download('imslp-1', 'archive-abc123', 'Retry after recovery')
        self.assertEqual(row['state'], 'downloaded')

    def test_symlink_destination_and_traversal_rejected(self):
        self.collector.search(max_works=1)
        (self.work/'audio').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.collector.download('imslp-1', 'archive-abc123', 'Checked')
        with self.assertRaises(ValueError):
            self.collector.candidates('../imslp-1')

    def test_limit_is_number_of_newly_processed_works(self):
        self.collector.search(max_works=1)
        other = self.root/'imslp-2'; other.mkdir()
        (other/'metadata.json').write_text(json.dumps(self.metadata))
        self.collector.search(max_works=1)
        self.assertEqual(len(self.collector.candidates('imslp-2')), 1)

    def test_failed_download_refreshes_current_permission(self):
        from unittest.mock import patch
        self.collector.search(max_works=1)
        candidate = self.source.search('', 1)['candidates'][0]
        with patch.object(self.collector.http, 'download', side_effect=RuntimeError('Network')):
            with self.assertRaises(RuntimeError):
                self.collector.download('imslp-1', candidate['id'], 'Checked')
        candidate['access'] = 'restricted'
        with patch.object(self.source, 'search', return_value={'candidates': [candidate], 'truncated': False}):
            self.collector.search(max_works=1, refresh=True)
        with self.assertRaises(ValueError):
            self.collector.download('imslp-1', candidate['id'], 'Retry')

    def test_absent_candidate_becomes_stale_and_reranked(self):
        from unittest.mock import patch
        self.collector.search(max_works=1)
        self.metadata['catalog']['title'] = 'Symphony No.6 Op.68'
        (self.work/'metadata.json').write_text(json.dumps(self.metadata))
        with patch.object(self.source, 'search', return_value={'candidates': [], 'truncated': False}):
            self.collector.search(max_works=1)
        row = self.collector.candidates('imslp-1')[0]
        self.assertTrue(row['stale'])
        self.assertEqual(row['match']['tier'], 'conflict')
        with self.assertRaises(ValueError):
            self.collector.download('imslp-1', row['id'], 'Checked')

    def test_resume_repairs_existing_outdated_sidecar(self):
        from unittest.mock import patch
        self.collector.search(max_works=1)
        with patch.object(self.collector, 'export', side_effect=RuntimeError('Interrupted')):
            with self.assertRaises(RuntimeError): self.collector.search(max_works=1, limit=6)
        self.collector.search(max_works=1, limit=6)
        sidecar = json.loads((self.work/'recordings/metadata.json').read_text())
        self.assertEqual(sidecar['searches'][0]['limit'], 6)

    def test_download_source_is_preserved_across_refresh(self):
        from unittest.mock import patch
        self.collector.search(max_works=1)
        candidate = self.source.search('', 1)['candidates'][0]
        self.collector.download('imslp-1', candidate['id'], 'Checked')
        candidate['title'] = 'Changed source description'
        with patch.object(self.source, 'search', return_value={'candidates': [candidate], 'truncated': False}):
            self.collector.search(max_works=1, refresh=True)
        row = self.collector.candidates('imslp-1')[0]
        self.assertEqual(row['title'], candidate['title'])
        self.assertNotEqual(row['download_source']['title'], candidate['title'])

    def test_download_rechecks_work_identity_before_using_candidate(self):
        self.collector.search(max_works=1)
        self.metadata['catalog']['title'] = 'Symphony No.6 Op.68'
        (self.work/'metadata.json').write_text(json.dumps(self.metadata))
        with self.assertRaises(ValueError):
            self.collector.download('imslp-1', 'archive-abc123', 'Checked old candidate')


if __name__ == '__main__': unittest.main()
