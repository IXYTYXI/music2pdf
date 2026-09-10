from pathlib import Path
import json,time,hashlib
import torch,soundfile as sf,librosa
from piano_transcription_inference import PianoTranscription
p=Path('.work/phrase-model-comparison');torch.set_num_threads(4)
src=Path('outputs/feasibility-2026-09-10/samples/imslp-929871/audio/IMSLP579780.mp3')
x,sr=sf.read(src,dtype='float32',always_2d=True)
x=librosa.resample(x.mean(axis=1),orig_sr=sr,target_sr=16000)
start=time.monotonic()
model=PianoTranscription(device='cpu',checkpoint_path='.work/amt-comparison/piano-model.pth')
r=model.transcribe(x,str(p/'full.mid'))
(p/'notes.json').write_text(json.dumps(r['est_note_events'],indent=2,default=lambda v:v.item()))
(p/'run.json').write_text(json.dumps({'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'duration':len(x)/16000,'seconds':time.monotonic()-start,'events':len(r['est_note_events']),'score_input':False},indent=2))
print((p/'run.json').read_text())
