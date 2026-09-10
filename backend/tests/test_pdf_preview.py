import tempfile
import unittest
from pathlib import Path
import pymupdf
from fastapi.testclient import TestClient
from dataset_app import app

class PdfPreviewTests(unittest.TestCase):
 def test_pages_errors_and_paths(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);score=root/'work/scores/test.pdf';score.parent.mkdir(parents=True)
   with pymupdf.open() as doc:
    doc.new_page().insert_text((30,30),'First page')
    doc.new_page().insert_text((30,30),'Second page')
    doc.save(score)
   client=TestClient(app);params={'root':folder,'path':'work/scores/test.pdf'}
   self.assertEqual(client.get('/api/pdf/info',params=params).json()['pages'],2)
   first=client.get('/api/pdf/page',params={**params,'page':1})
   second=client.get('/api/pdf/page',params={**params,'page':2})
   self.assertEqual(first.status_code,200);self.assertTrue(first.content.startswith(b'\x89PNG'));self.assertNotEqual(first.content,second.content)
   self.assertEqual(client.get('/api/pdf/page',params={**params,'page':3}).status_code,404)
   self.assertEqual(client.get('/api/pdf/page',params={**params,'page':0}).status_code,422)
   self.assertEqual(client.get('/api/pdf/info',params={**params,'path':'../outside.pdf'}).status_code,404)
   score.write_bytes(b'invalid PDF')
   self.assertEqual(client.get('/api/pdf/info',params=params).status_code,400)
