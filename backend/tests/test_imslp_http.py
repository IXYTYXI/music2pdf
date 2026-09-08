import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from imslp_http import HTTP, AccessBlocked, valid_signature
from imslp_lock import run_lock

class Response:
    def __init__(self, data=b'', status=200, headers=None, url='https://imslp.org/file.pdf'):
        self.data, self.status_code, self.headers, self.url = data, status, headers or {}, url
        self.is_redirect = status in (301, 302, 303, 307, 308)
        self.closed = False
    def iter_content(self, size):
        for start in range(0, len(self.data), size): yield self.data[start:start+size]
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

class HTTPTests(unittest.TestCase):
    def setUp(self): self.http = HTTP(respect_robots=True)
    def test_catalog_json_response_is_decoded(self):
        http = HTTP()
        with patch.object(http, 'get', return_value=Response(b'{"metadata":{"start":2000}}')):
            self.assertEqual(http.json('https://imslp.org/imslpscripts/API.ISCR.php'),
                             {'metadata': {'start': 2000}})

    def test_default_download_does_not_require_robots_permission(self):
        http = HTTP()
        with patch.object(http, '_raw', return_value=Response(b'%PDF-1.7')) as raw:
            response = http.get('https://imslp.org/wiki/Special:ImagefromIndex/12')
            self.assertEqual(response.data, b'%PDF-1.7')
            self.assertEqual(raw.call_args.args[0], 'https://imslp.org/wiki/Special:ImagefromIndex/12')
            self.assertEqual(raw.call_count, 1)

    def test_default_still_stops_on_authentication_failure(self):
        with patch.object(HTTP, '_raw', return_value=Response(status=403)):
            with self.assertRaises(AccessBlocked): HTTP().get('https://imslp.org/wiki/Special:ImagefromIndex/12')

    def test_known_javascript_redirect_flow(self):
        http = HTTP()
        gate = Response(b'<script>form.action = "/friendlyredirect2.html#"; input.name = "friendlyredirect";</script>', url='https://imslp.org/friendlyredirect.html#/wiki/Special:ImagefromIndex/12')
        gate2 = Response(b"<script>document.cookie = 'redirectPassed=1; path=/;';</script>")
        with patch.object(http, '_raw', side_effect=[gate, gate2, Response(b'%PDF-1.7')]) as raw:
            result = http.get('https://imslp.org/wiki/Special:ImagefromIndex/12')
            self.assertEqual(result.data, b'%PDF-1.7')
            self.assertEqual(raw.call_count, 3)
            self.assertEqual(raw.call_args_list[1].kwargs['method'], 'POST')
            self.assertEqual(http.session.cookies.get('redirectPassed'), '1')

    def test_file_disclaimer_uses_same_file_normal_link(self):
        http = HTTP()
        page = Response(b'<a href="/wiki/Special:IMSLPDisclaimerAccept/12">I understand</a>', headers={'Content-Type':'text/html'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(http, 'get', side_effect=[page, Response(b'%PDF-1.7')]) as get:
            http.download({'id':'12', 'url':'https://imslp.org/wiki/Special:ImagefromIndex/12', 'extension':'.pdf'}, Path(tmp)/'x.pdf')
            self.assertEqual(get.call_args.args[0], 'https://imslp.org/wiki/Special:IMSLPDisclaimerAccept/12')

    def test_legacy_http_redirect_upgraded_to_https(self):
        http = HTTP()
        with patch.object(http, '_raw', side_effect=[Response(status=302, headers={'Location':'http://imslp.org/wiki/Special:IMSLPImageHandler/12'}), Response(b'%PDF-1.7')]) as raw:
            http.get('https://imslp.org/wiki/Special:IMSLPDisclaimerAccept/12')
            self.assertEqual(raw.call_args.args[0], 'https://imslp.org/wiki/Special:IMSLPImageHandler/12')

    def test_nonmember_countdown_is_observed_before_download(self):
        http = HTTP()
        html = b'<script>var msg={"js-a4":"15"};</script><span id="sm_dl_wait" data-id="https://vmirror.imslp.org/files/score.pdf"></span>'
        page = Response(html,headers={'Content-Type':'text/html'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(http,'get',side_effect=[page,Response(b'%PDF-1.7')]) as get, patch('imslp_http.time.sleep') as sleep:
            http.download({'id':'12','url':'https://imslp.org/wiki/Special:ImagefromIndex/12','extension':'.pdf'},Path(tmp)/'x.pdf')
            sleep.assert_called_once_with(15)
            self.assertEqual(get.call_args.args[0],'https://vmirror.imslp.org/files/score.pdf')

    def test_robots_blocks_before_download_request(self):
        with patch.object(self.http, '_raw', return_value=Response(b'User-agent: *\nDisallow: /wiki/Special:\n')) as raw:
            with self.assertRaises(AccessBlocked): self.http.get('https://imslp.org/wiki/Special:ImagefromIndex/12')
            self.assertEqual(raw.call_count, 1)
    def test_cross_origin_redirect_checked(self):
        with patch.object(self.http, '_raw', side_effect=[Response(b'User-agent: *\nDisallow:\n'), Response(status=302, headers={'Location': 'http://127.0.0.1/private'})]) as raw:
            with self.assertRaises(AccessBlocked): self.http.get('https://imslp.org/wiki/A')
            self.assertEqual(raw.call_count, 2)
    def test_network_error_does_not_disable_robots(self):
        with patch.object(self.http, '_raw', return_value=Response(status=503)):
            with self.assertRaises(AccessBlocked): self.http.get('https://imslp.org/wiki/A')
    def test_retry_after_and_server_error_retries(self):
        with patch.object(self.http.session, 'get', side_effect=[Response(status=429, headers={'Retry-After': '3'}), Response(b'ok')]) as get, patch('imslp_http.time.sleep') as sleep:
            self.assertEqual(self.http._raw('https://imslp.org/wiki/A', 2).data, b'ok')
            self.assertEqual(get.call_count, 2)
            self.assertIn(((3.0,),), [c for c in sleep.call_args_list])
    def test_very_long_retry_after_stops(self):
        with patch.object(self.http.session, 'get', return_value=Response(status=429, headers={'Retry-After': '120'})), patch('imslp_http.time.sleep'):
            with self.assertRaises(AccessBlocked): self.http._raw('https://imslp.org/wiki/A', 2)
    def test_valid_download_then_invalid_file_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'score.pdf'
            info = self.http._save(Response(b'%PDF-1.7\ncontent'), path, '.pdf')
            self.assertEqual(info['bytes'], path.stat().st_size)
            for response in [Response(b'<html>login</html>'), Response(b'%PDF-1.7\ncut', headers={'Content-Length': '900'})]:
                with self.assertRaises(ValueError): self.http._save(response, path, '.pdf')
                self.assertEqual(path.read_bytes(), b'%PDF-1.7\ncontent')
                self.assertFalse(path.with_suffix('.pdf.part').exists())
    def test_oversized_file_leaves_no_partial(self):
        self.http.max_bytes = 4
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'x.pdf'
            with self.assertRaises(ValueError): self.http._save(Response(b'%PDF-123456'), path, '.pdf')
            self.assertEqual(list(Path(tmp).iterdir()), [])
    def test_html_challenge_never_downloaded(self):
        with patch.object(self.http, 'get', return_value=Response(b'<html>Sign in</html>', headers={'Content-Type': 'text/html'})):
            with self.assertRaises(AccessBlocked): self.http.download({'url': 'https://imslp.org/a', 'extension': '.pdf'}, Path('unused.pdf'))
    def test_signature_validation(self):
        self.assertTrue(valid_signature(b'%PDF-1.7', '.pdf'))
        self.assertTrue(valid_signature(b'OggS1234', '.ogg'))
        self.assertFalse(valid_signature(b'error', '.mp3'))
        self.assertFalse(valid_signature(b'<html>blocked', '.pdf'))
    def test_lock_released_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lock'
            with run_lock(path):
                with self.assertRaises(RuntimeError):
                    with run_lock(path): pass
            with run_lock(path): pass

if __name__ == '__main__': unittest.main()
