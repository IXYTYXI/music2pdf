import json
import tempfile
import unittest
from pathlib import Path
from imslp_catalog import parse_catalog, parse_work
from imslp_collector import Collector, AccessBlocked
from dataset import scan_dataset

HTML = (Path(__file__).parent / 'fixtures/imslp-work.html').read_text()
URL = 'https://imslp.org/wiki/Prelude_(Example,_Composer)'
def catalog(start=0, more=False):
    return {'0': {'id': 'Prelude', 'permlink': URL.replace('/', r'\/'),
                  'intvals': {'pageid': '42', 'composer': 'Example, Composer', 'worktitle': 'Prelude'}},
            'metadata': {'start': start, 'limit': 1000, 'moreresultsavailable': more}}

class FakeHTTP:
    def __init__(self): self.calls = []; self.block = False
    def json(self, url): self.calls.append(url); return catalog()
    def text(self, url): self.calls.append(url); return HTML
    def download(self, asset, path):
        self.calls.append(asset['url'])
        if self.block: raise AccessBlocked('robots.txt denies access')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'%PDF-1.7\nscore' if asset['kind'] == 'scores' else b'ID3recording')
        return {'sha256': __import__('hashlib').sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}

class ParserTests(unittest.TestCase):
    def test_real_api_escaping_and_cursor(self):
        works, cursor, more = parse_catalog(catalog(more=True), 0)
        self.assertEqual(works[0]['url'], URL)
        self.assertEqual(works[0]['id'], '42')
        self.assertEqual(cursor, 1000)
        self.assertTrue(more)
    def test_malformed_catalog_does_not_advance(self):
        with self.assertRaises(ValueError): parse_catalog({'error': 'maintenance'}, 0)
        bad = catalog(); bad['0'].pop('permlink')
        with self.assertRaises(ValueError): parse_catalog(bad, 0)
    def test_catalog_record_without_pageid_is_kept(self):
        data = catalog(); del data['0']['intvals']['pageid']
        works, _, _ = parse_catalog(data, 0)
        self.assertEqual(len(works), 1)
        self.assertTrue(works[0]['id'].startswith('url-'))

    def test_asset_metadata_stays_in_its_group(self):
        work = parse_work(HTML, URL)
        self.assertEqual(work['information']['Instrumentation'], 'piano')
        self.assertEqual(len(work['assets']), 2)
        audio, score = work['assets']
        self.assertEqual(audio['metadata']['Performer Pages'], 'A pianist')
        self.assertEqual(score['metadata']['Copyright'], 'Public Domain')
        self.assertNotIn('Performer Pages', score['metadata'])
        self.assertEqual(score['extension'], '.pdf')
        self.assertEqual(len(work['streaming']), 1)
    def test_challenge_not_empty_success(self):
        with self.assertRaises(ValueError): parse_work('<html>Just a moment...</html>', URL)

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.http = FakeHTTP(); self.c = Collector(self.root, self.http)
    def tearDown(self): self.c.close(); self.tmp.cleanup()
    def test_automatic_discovery_restart_and_workbench(self):
        self.c.discover(1); self.c.collect(1)
        inventory = scan_dataset(self.root)
        self.assertEqual(inventory['eligible_count'], 1)
        self.assertEqual(inventory['audio_count'], 1)
        calls = len(self.http.calls)
        self.c.close(); self.c = Collector(self.root, self.http)
        self.c.discover(1); self.c.collect(1)
        self.assertEqual(len(self.http.calls), calls)
        self.assertEqual(self.c.status()['assets']['downloaded'], 2)
    def test_filtered_works_can_be_collected_later(self):
        self.c.discover(1); self.c.collect(1, instrument='violin')
        self.assertEqual(scan_dataset(self.root)['audio_count'], 0)
        self.c.collect(1, instrument='piano')
        self.assertEqual(scan_dataset(self.root)['eligible_count'], 1)
    def test_blocked_assets_are_retryable_not_success(self):
        self.c.discover(1); self.http.block = True; self.c.collect(1)
        self.assertEqual(self.c.status()['assets']['blocked'], 2)
        self.http.block = False; self.c.collect(1, retry=True)
        self.assertEqual(self.c.status()['assets']['downloaded'], 2)
    def test_deleted_download_is_recovered(self):
        self.c.discover(1); self.c.collect(1)
        next(self.root.glob('*/scores/*.pdf')).unlink()
        self.c.collect(1)
        self.assertEqual(scan_dataset(self.root)['score_count'], 1)
    def test_second_page_failure_preserves_committed_cursor(self):
        self.http.json = lambda url: catalog(more=True)
        self.c.discover(1)
        self.assertEqual(self.c.status()['cursor'], 1000)
        self.http.json = lambda url: {'error': 'temporary invalid response'}
        with self.assertRaises(ValueError): self.c.discover(1)
        self.assertEqual(self.c.status()['cursor'], 1000)
        self.http.json = lambda url: catalog(start=1000)
        self.c.discover(1)
        self.assertEqual(self.c.status()['cursor'], 2000)
        self.assertTrue(self.c.status()['catalog_exhausted'])

    def test_corrupted_file_is_recovered(self):
        self.c.discover(1); self.c.collect(1)
        target = next(self.root.glob('*/scores/*.pdf'))
        target.write_bytes(b'X' * target.stat().st_size)
        self.c.collect(1)
        self.assertTrue(target.read_bytes().startswith(b'%PDF-'))

    def test_metadata_only_does_not_request_files(self):
        self.c.discover(1); self.c.collect(1, metadata_only=True)
        self.assertEqual(len(self.http.calls), 2)
        self.assertEqual(self.c.status()['assets']['pending'], 2)
        self.c.collect(1)
        self.assertEqual(scan_dataset(self.root)['eligible_count'], 1)

    def test_file_budget_resumes_remaining_files(self):
        self.c.discover(1); self.c.collect(1, max_files=1)
        self.assertEqual(self.c.status()['assets']['downloaded'], 1)
        self.c.collect(1, max_files=1)
        self.assertEqual(self.c.status()['assets']['downloaded'], 2)

    def test_symlink_output_rejected(self):
        self.c.discover(1)
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'imslp-42').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): self.c.collect(1)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_refresh_keeps_downloads(self):
        self.c.discover(1); self.c.collect(1)
        self.c.discover(1, refresh=True); self.c.collect(1, refresh=True)
        downloads = [x for x in self.http.calls if '/Special:' in x]
        self.assertEqual(len(downloads), 2)

if __name__ == '__main__': unittest.main()
