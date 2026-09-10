import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from dataset_app import app
from dataset_cloud import parse_link, sessions

class CloudTests(unittest.TestCase):
    def tearDown(self): sessions.clear()
    def test_links(self):
        self.assertEqual(parse_link('https://abc.r2.cloudflarestorage.com/music-scores/imslp/')['prefix'],'imslp')
        for link in ['http://abc.r2.cloudflarestorage.com/bucket','https://evil.com/bucket','https://abc.r2.cloudflarestorage.com/','https://abc.r2.cloudflarestorage.com/bucket/../secret','https://abc.r2.cloudflarestorage.com/bucket?token=secret']:
            with self.assertRaises(ValueError): parse_link(link)
    @patch('dataset_cloud.boto3.client')
    def test_connection_pull_disconnect(self, client):
        client.return_value.list_objects_v2.return_value={'Contents':[]}
        api=TestClient(app)
        response=api.post('/api/cloud/connect',json={'link':'https://abc.r2.cloudflarestorage.com/music-scores/imslp','access':'id','secret':'private-value'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('private-value',response.text)
        token=response.json()['session']
        self.assertEqual(api.post('/api/cloud/pull',json={'session':token,'works':['missing']}).status_code,400)
        self.assertEqual(api.post('/api/cloud/disconnect',json={'session':token}).status_code,200)
        self.assertEqual(api.post('/api/cloud/pull',json={'session':token,'works':['missing']}).status_code,401)
    @patch('dataset_cloud.boto3.client',side_effect=RuntimeError('private-value'))
    def test_failure_redacted(self, client):
        r=TestClient(app).post('/api/cloud/connect',json={'link':'https://abc.r2.cloudflarestorage.com/music-scores','access':'id','secret':'private-value'})
        self.assertEqual(r.status_code,400);self.assertNotIn('private-value',r.text)
