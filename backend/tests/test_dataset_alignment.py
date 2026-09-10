import tempfile,json,zipfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from music21 import stream,note,tempo
import dataset_alignment as api
from dataset_app import app

class AlignmentApiTests(unittest.TestCase):
 @patch.object(api,'muse',return_value=None)
 def test_prepare_protects_source_and_rejects_wrong_work(self,muse):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);p=root/'piece/scores/source.musicxml';p.parent.mkdir(parents=True)
   s=stream.Score();part=stream.Part();m=stream.Measure(number=1);m.append(tempo.MetronomeMark(number=120));m.append(note.Note('C4',quarterLength=4));part.append(m);s.append(part);s.write('musicxml',fp=p)
   before=p.read_bytes();client=TestClient(app)
   with patch.object(api,'DATA',root/'state'):
    r=client.post('/api/alignment/prepare',json={'root':folder,'work':'piece','score':'piece/scores/source.musicxml'})
    self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['timeline']['duration'],2);self.assertEqual(p.read_bytes(),before)
    mxl=p.with_suffix('.mxl')
    with zipfile.ZipFile(mxl,'w') as z:
     z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>');z.writestr('score.xml',before)
    compressed=client.post('/api/alignment/prepare',json={'root':folder,'work':'piece','score':'piece/scores/source.mxl'})
    self.assertEqual(compressed.status_code,200,compressed.text)
    original_xml=client.get('/api/alignment/scores/'+compressed.json()['id']+'/file',params={'name':'score.musicxml'})
    self.assertEqual(original_xml.content,before)
    bad=client.post('/api/alignment/prepare',json={'root':folder,'work':'../outside','score':'x'})
    self.assertEqual(bad.status_code,400)
    self.assertEqual(client.get('/api/alignment/scores/'+r.json()['id']+'/file',params={'name':'../source.musicxml'}).status_code,404)
 def test_review_retains_automatic_proposal(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(api,'DATA',Path(folder)):
   key='a'*32;p=Path(folder)/'jobs'/key;p.mkdir(parents=True)
   d={'rows':[{'id':1,'start':0,'end':1,'matched':True}],'audio_window':[0,10],'training_ready':False}
   api.save(p/'automatic.json',d);api.save(p/'state.json',{'id':key,'status':'needs_review','request':{}})
   r=TestClient(app).post('/api/alignment/jobs/'+key+'/review',json={'rows':[{'id':1,'start':1,'end':2,'matched':True}],'reviewed':True})
   self.assertEqual(r.status_code,200);self.assertEqual(json.loads((p/'automatic.json').read_text()),d);self.assertFalse(r.json()['training_ready'])
