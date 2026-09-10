import unittest
import numpy as np
from alignment_engine import match_features,validate_corrections

class AlignmentTests(unittest.TestCase):
 def test_stretch_and_leading_audio(self):
  ref=np.repeat(np.eye(12),4,axis=1)
  audio=np.concatenate([np.ones((12,8))*.2,np.repeat(ref,2,axis=1),np.ones((12,6))*.2],axis=1)
  x,y,cost=match_features(ref,audio,.1)
  self.assertLess(cost,.1);self.assertLess(abs(y[0]-.8),.21);self.assertLess(abs(y[-1]-10.3),.31)
 def test_score_longer_than_audio_keeps_axis_order(self):
  audio=np.repeat(np.eye(12),4,axis=1);ref=np.repeat(audio,2,axis=1)
  x,y,cost=match_features(ref,audio,.1)
  self.assertAlmostEqual(x[-1],9.5);self.assertLessEqual(y[-1],4.7);self.assertLess(cost,.1)
 def test_review_rejects_overlap_nan_and_changed_ids(self):
  original=[{'id':1},{'id':2}]
  valid=[{'id':1,'start':0,'end':1,'matched':True},{'id':2,'start':1,'end':2,'matched':True}]
  validate_corrections(valid,original,3)
  for rows in [[{**valid[0],'end':2},valid[1]],[{**valid[0],'start':float('nan')},valid[1]],[{**valid[0],'id':3},valid[1]]]:
   with self.assertRaises(ValueError):validate_corrections(rows,original,3)
