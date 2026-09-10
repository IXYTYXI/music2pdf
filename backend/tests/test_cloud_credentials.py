import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cloud_credentials as credentials
from dataset_cloud import sessions
from dataset_app import app
from fastapi.testclient import TestClient

class Vault:
    def __init__(self): self.values={}
    def set_password(self,s,k,v): self.values[s,k]=v
    def get_password(self,s,k): return self.values.get((s,k))
    def delete_password(self,s,k): del self.values[s,k]

class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.vault=Vault()
        self.patches=[patch.object(credentials,'PROFILE',Path(self.temp.name)/'profile.json'),patch.object(credentials,'vault',return_value=self.vault)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in self.patches:p.stop()
        sessions.clear();self.temp.cleanup()
    def test_store_read_delete_no_plaintext(self):
        credentials.save('https://account/bucket','example-access','example-secret')
        self.assertNotIn('example-secret',credentials.PROFILE.read_text())
        self.assertEqual(credentials.load('https://account/bucket'),('example-access','example-secret'))
        with self.assertRaises(ValueError): credentials.load('different-source')
        credentials.forget();self.assertFalse(credentials.PROFILE.exists());self.assertEqual(self.vault.values,{})
    def test_unavailable_vault_no_fallback(self):
        with patch.object(credentials,'vault',side_effect=RuntimeError('private-detail')):
            with self.assertRaisesRegex(ValueError,'系统凭据库'): credentials.save('link','access','secret')
        self.assertFalse(credentials.PROFILE.exists())
    @patch('dataset_cloud.boto3.client')
    def test_reconnect_without_retyping_after_session_reset(self,client):
        client.return_value.list_objects_v2.return_value={'Contents':[]}
        api=TestClient(app);link='https://abc.r2.cloudflarestorage.com/music-scores/imslp'
        first=api.post('/api/cloud/connect',json={'link':link,'access':'example-access','secret':'example-secret','remember':True})
        self.assertEqual(first.status_code,200)
        sessions.clear()
        cfg=api.get('/api/cloud/config').json();self.assertTrue(cfg['saved']);self.assertNotIn('example-secret',json.dumps(cfg))
        second=api.post('/api/cloud/connect',json={'link':cfg['link'],'use_saved':True})
        self.assertEqual(second.status_code,200)
        self.assertEqual(client.call_args.kwargs['aws_secret_access_key'],'example-secret')
        self.assertEqual(api.post('/api/cloud/forget',json={}).status_code,200)
        self.assertFalse(sessions);self.assertFalse(credentials.PROFILE.exists())
