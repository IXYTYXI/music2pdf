import tempfile
import unittest
from pathlib import Path
from music21 import stream,tempo,note,meter,duration,instrument,bar
from score_timeline import read_timeline

class TimelineTests(unittest.TestCase):
 def render(self,score,**kwargs):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.musicxml';score.write('musicxml',fp=p);return read_timeline(p,**kwargs)
 def test_dotted_tempo_change_and_sound_pitch(self):
  s=stream.Score();p=stream.Part();p.insert(0,instrument.Clarinet())
  m=stream.Measure(number=1);m.append(meter.TimeSignature('6/8'));m.append(tempo.MetronomeMark(number=60,referent=duration.Duration(1.5)));m.append(note.Note('C4',quarterLength=3));p.append(m)
  m2=stream.Measure(number=2);m2.append(tempo.MetronomeMark(number=120));m2.append(note.Note('D4',quarterLength=3));p.append(m2);s.append(p)
  t=self.render(s);self.assertAlmostEqual(t['measures'][0]['end'],2);self.assertAlmostEqual(t['duration'],3.5);self.assertEqual(t['notes'][0]['midi'],58)
 def test_missing_tempo_requires_input(self):
  s=stream.Score();p=stream.Part();m=stream.Measure(number=1);m.append(note.Note('C4',quarterLength=4));p.append(m);s.append(p)
  with self.assertRaisesRegex(ValueError,'初始速度'):self.render(s)
  self.assertEqual(self.render(s,fallback_bpm=120)['duration'],2)
 def test_repeated_measures_keep_occurrences(self):
  s=stream.Score();p=stream.Part();m=stream.Measure(number=1);m.append(tempo.MetronomeMark(number=120));m.append(note.Note('C4',quarterLength=4));m.leftBarline=bar.Repeat(direction='start');m.rightBarline=bar.Repeat(direction='end',times=2);p.append(m);s.append(p)
  t=self.render(s);self.assertEqual(len(t['measures']),2);self.assertNotEqual(t['measures'][0]['id'],t['measures'][1]['id'])
