import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from dataset_app import app

class DatasetApiTests(unittest.TestCase):
    def test_complete_workflow_and_guards(self):
        with tempfile.TemporaryDirectory() as tmp, TestClient(app) as client:
            self.assertEqual(client.get('/').status_code,200)
            for i in range(3):
                r=client.post('/api/create',json={'root':tmp,'work':f'work-{i}'})
                self.assertEqual(r.status_code,200)
                p=Path(r.json()['directory'])
                (p/'audio/a.mp3').write_bytes(f'audio{i}'.encode())
                (p/'scores/a.pdf').write_bytes(f'pdf{i}'.encode())
            scan=client.post('/api/scan',json={'root':tmp}).json()
            body={'root':tmp,'fingerprint':scan['fingerprint'],'seed':42,'ratios':[80,10,10]}
            preview=client.post('/api/preview',json=body)
            self.assertEqual(preview.status_code,200)
            self.assertEqual(client.post('/api/export',json=body).status_code,200)
            self.assertEqual(client.get('/api/file',params={'root':tmp,'path':'work-0/audio/a.mp3'}).content,b'audio0')
            self.assertEqual(client.get('/api/file',params={'root':tmp,'path':'../secret.mp3'}).status_code,404)
            self.assertEqual(client.post('/api/create',json={'root':tmp,'work':'../bad'}).status_code,400)
            self.assertEqual(client.post('/api/create',json={'root':tmp,'work':'new'},headers={'Origin':'https://evil.example'}).status_code,403)
            body['ratios']=[100,0,0]
            self.assertEqual(client.post('/api/preview',json=body).status_code,400)

if __name__=='__main__':unittest.main()
