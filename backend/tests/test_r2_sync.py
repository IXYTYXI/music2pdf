import base64
import hashlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from botocore.exceptions import ClientError
from r2_sync import Syncer

class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.puts = []
        self.corrupt = False
    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')
        body, metadata = self.objects[Key]
        return {'ContentLength': len(body) + int(self.corrupt), 'Metadata': metadata}
    def put_object(self, Bucket, Key, Body, Metadata, ContentMD5, **kwargs):
        body = Body.read() if hasattr(Body, 'read') else Body
        assert ContentMD5 == base64.b64encode(hashlib.md5(body).digest()).decode()
        self.objects[Key] = body, Metadata
        self.puts.append(Key)
    def get_object(self, Bucket, Key):
        return {'Body': io.BytesIO(self.objects[Key][0])}

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.s3 = MemoryS3()
        self.sync = Syncer(self.root, self.s3, 'music-scores', 'imslp')
        self.addCleanup(self.sync.close)
    def file(self, name, data=b'%PDF-1.7 sample'):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p
    def test_upload_verifies_and_resume_skips_same_content(self):
        p = self.file('imslp-1/scores/x.pdf')
        self.assertTrue(self.sync.sync_file(p, 'imslp/imslp-1/scores/x.pdf'))
        self.assertFalse(self.sync.sync_file(p, 'imslp/imslp-1/scores/x.pdf'))
        self.assertEqual(len(self.s3.puts), 1)
        self.assertEqual(self.sync.summary()['verified_objects'], 1)
        self.assertTrue(p.exists())
    def test_remote_match_after_lost_local_checkpoint_avoids_reupload(self):
        p = self.file('imslp-1/scores/x.pdf')
        key = 'imslp/imslp-1/scores/x.pdf'
        self.s3.objects[key] = p.read_bytes(), {'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        self.sync.sync_file(p, key)
        self.assertEqual(self.s3.puts, [])
        self.assertEqual(self.sync.summary()['verified_objects'], 1)
    def test_failed_verification_is_not_committed(self):
        self.s3.corrupt = True
        with self.assertRaises(ValueError):
            self.sync.sync_file(self.file('imslp-1/scores/x.pdf'), 'imslp/x.pdf')
        self.assertEqual(self.sync.summary()['verified_objects'], 0)
    def test_changed_metadata_is_uploaded_again(self):
        p = self.file('imslp-1/metadata.json', b'{"version":1}')
        self.sync.sync_file(p, 'imslp/imslp-1/metadata.json')
        p.write_bytes(b'{"version":22}')
        self.sync.sync_file(p, 'imslp/imslp-1/metadata.json')
        self.assertEqual(len(self.s3.puts), 2)
    def test_inventory_excludes_parts_symlinks_credentials_and_logs(self):
        good = self.file('imslp-1/audio/a.mp3')
        self.file('imslp-1/audio/a.mp3.part')
        self.file('imslp-1/metadata.json.tmp')
        self.file('.imslp/run.log')
        self.file('.imslp/private-cookies.txt')
        self.file('.imslp/raw/page.html', b'<html>source</html>')
        (self.root / 'imslp-1/audio/link.mp3').symlink_to(good)
        paths = [p.relative_to(self.root).as_posix() for p, key in self.sync.inventory()]
        self.assertEqual(set(paths), {'imslp-1/audio/a.mp3', '.imslp/raw/page.html'})
    def test_sqlite_snapshot_is_readable_and_contains_committed_rows(self):
        p = self.root / '.imslp/queue.sqlite3'
        p.parent.mkdir(exist_ok=True)
        with sqlite3.connect(p) as db:
            db.execute('CREATE TABLE sample (value TEXT)')
            db.execute("INSERT INTO sample VALUES ('saved')")
        snapshot = self.sync.snapshot_queue()
        with sqlite3.connect(snapshot) as db:
            self.assertEqual(db.execute('SELECT * FROM sample').fetchall(), [('saved',)])
        self.assertEqual(snapshot, self.sync.snapshot_queue())
    def test_foreign_remote_object_is_not_overwritten(self):
        p = self.file('imslp-1/scores/x.pdf')
        self.s3.objects['imslp/x.pdf'] = b'other', {}
        with self.assertRaises(ValueError):
            self.sync.sync_file(p, 'imslp/x.pdf')
        self.assertEqual(self.s3.puts, [])

    def test_external_recording_provenance_uses_existing_inventory(self):
        self.file('imslp-1/recordings/metadata.json', b'{"candidates":[]}')
        self.file('imslp-1/recordings/private-token.txt', b'private')
        self.file('imslp-1/audio/external-123.mp3', b'ID3sample')
        keys = {key for path, key in self.sync.inventory()}
        self.assertEqual(keys, {'imslp/imslp-1/recordings/metadata.json',
                                'imslp/imslp-1/audio/external-123.mp3'})

    def test_changing_metadata_is_deferred_then_resynced(self):
        from unittest.mock import patch
        import json
        path = self.file('imslp-1/metadata.json', b'{"version":1}')
        original = self.s3.put_object
        def change_during_upload(**kwargs):
            original(**kwargs)
            replacement = path.with_suffix('.json.tmp')
            replacement.write_bytes(b'{"version":22}')
            replacement.replace(path)
        with patch.object(self.s3, 'put_object', side_effect=change_during_upload):
            self.assertTrue(self.sync.cycle())
        checkpoint = json.loads((self.sync.state/'checkpoint.json').read_text())
        self.assertEqual(len(checkpoint['deferred']), 1)
        self.assertEqual(checkpoint['failures'], [])
        self.assertEqual(self.sync.summary()['verified_objects'], 0)
        self.assertTrue(self.sync.cycle())
        self.assertEqual(self.sync.summary()['verified_objects'], 1)
        self.assertEqual(self.s3.objects['imslp/imslp-1/metadata.json'][0], path.read_bytes())

    def test_remote_verification_failure_is_still_a_failure(self):
        self.file('imslp-1/metadata.json', b'{}')
        self.s3.corrupt = True
        self.assertFalse(self.sync.cycle())
        self.assertEqual(self.sync.summary()['verified_objects'], 0)

if __name__ == '__main__':
    unittest.main()
