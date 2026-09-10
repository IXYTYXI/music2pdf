import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from fastapi.testclient import TestClient
import pymupdf
import dataset_omr as omr
from dataset_app import app
XML=b'<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1"><measure><note><pitch><step>C</step><octave>4</octave></pitch></note></measure></part></score-partwise>'

class OMRTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.jobs=self.root/'jobs';self.patch=patch.object(omr,'JOBS',self.jobs);self.patch.start()
 def tearDown(self):
  self.patch.stop();omr.active.clear();self.tmp.cleanup()
 def test_xml_validation(self):
  self.assertEqual(omr.summary(XML)['notes'],1)
  for data in [b'<html/>',b'<score-partwise/>',b'<!DOCTYPE a [<!ENTITY x "secret">]><score-partwise/>']:
   with self.assertRaises(ValueError):omr.summary(data)
 @patch.object(omr,'engine',return_value='/engine')
 @patch.object(omr.executor,'submit')
 def test_start_history_review_and_immutable_source(self,submit,engine):
  p=self.root/'work/scores/score.pdf';p.parent.mkdir(parents=True)
  with pymupdf.open() as doc:doc.new_page();doc.save(p)
  original=p.read_bytes();client=TestClient(app);payload={'root':str(self.root),'path':'work/scores/score.pdf','start':1,'end':1}
  r=client.post('/api/omr/jobs',json=payload);self.assertEqual(r.status_code,200);j=r.json();folder=self.jobs/j['id']
  self.assertEqual(client.post('/api/omr/jobs',json={**payload,'end':2}).status_code,400)
  self.assertEqual(client.post('/api/omr/jobs',json={**payload,'path':'../outside.pdf'}).status_code,404)
  j.update(status='needs_review');omr.write_state(folder,j)
  r=client.post('/api/omr/jobs/'+j['id']+'/corrected',json={'filename':'../../score.xml','content':base64.b64encode(XML).decode(),'reviewed':True})
  self.assertEqual(r.status_code,200);self.assertEqual(r.json()['status'],'reviewed');self.assertFalse(r.json()['training_ready']);self.assertEqual(p.read_bytes(),original)
  self.assertEqual(len(client.get('/api/omr/jobs',params={'root':str(self.root),'path':payload['path']}).json()['jobs']),1)
  self.assertEqual(client.get('/api/omr/jobs/'+j['id']+'/file',params={'name':'../state.json'}).status_code,404)
 def test_successful_exit_without_notes_is_failure(self):
  folder=self.jobs/('a'*32);folder.mkdir(parents=True);(folder/'output').mkdir();(folder/'output/empty.xml').write_text('<score-partwise/>')
  state={'id':'a'*32,'status':'queued'}
  with patch.object(omr.subprocess,'run',return_value=MagicMock(returncode=0)):omr.work(folder,'/engine',state)
  self.assertEqual(json.loads((folder/'state.json').read_text())['status'],'failed')
