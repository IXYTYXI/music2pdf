import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        def runner(folder, preset):
            self.assertEqual((folder / 'input.wav').read_bytes(), b'audio')
            (folder / 'stems').mkdir()
            (folder / 'stems' / 'input_vocals.wav').write_bytes(b'result')
            return {'files': ['input_vocals.wav']}
        self.app = create_app(Path(self.temp.name), runner=runner, max_bytes=10)
        self.client = TestClient(self.app).__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_upload_poll_download_delete(self):
        response = self.client.post('/jobs?filename=../../song.wav&preset=four', content=b'audio')
        self.assertEqual(response.status_code, 202)
        job_id = response.json()['id']
        self.app.state.queue.wait()
        job = self.client.get('/jobs/' + job_id).json()
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(self.client.get(f'/jobs/{job_id}/files/input_vocals.wav').content, b'result')
        self.assertEqual(self.client.get(f'/jobs/{job_id}/files/result.json').status_code, 404)
        self.assertEqual(self.client.delete('/jobs/' + job_id).status_code, 204)
        self.assertEqual(self.client.get('/jobs/' + job_id).status_code, 404)

    def test_invalid_uploads_are_removed(self):
        for suffix, data, status in [('wav', b'', 400), ('wav', b'x' * 11, 413), ('exe', b'audio', 400)]:
            with self.subTest(suffix=suffix, length=len(data)):
                response = self.client.post('/jobs?filename=song.' + suffix, content=data)
                self.assertEqual(response.status_code, status)
                self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_unknown_preset_and_host_rejected(self):
        self.assertEqual(self.client.post('/jobs?filename=x.wav&preset=unknown', content=b'audio').status_code, 400)
        self.assertEqual(self.client.get('/health', headers={'host': 'evil.example'}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
