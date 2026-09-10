from pathlib import Path
import json,time,hashlib
import numpy as np
from madmom.features.downbeats import RNNDownBeatProcessor,DBNDownBeatTrackingProcessor
from madmom.features.onsets import CNNOnsetProcessor
p=Path('.work/madmom-quantization')
src=Path('outputs/feasibility-2026-09-10/samples/imslp-929871/audio/IMSLP579780.mp3')
t=time.monotonic();act=RNNDownBeatProcessor()(str(src));np.save(p/'downbeat-activations.npy',act)
print('activations',act.shape,'seconds',round(time.monotonic()-t,2),flush=True)
r={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'model':'madmom native RNNDownBeatProcessor','score_input':False,'candidates':{}}
for label,bars in [('joint',[3,4]),('triple',[3]),('quadruple',[4])]:
 beats=DBNDownBeatTrackingProcessor(beats_per_bar=bars,fps=100)(act)
 r['candidates'][label]={'beats_per_bar':bars,'beats':beats.tolist(),'median_pulse_bpm':float(np.median(60/np.diff(beats[:,0])))}
 print(label,len(beats),r['candidates'][label]['median_pulse_bpm'],flush=True)
(p/'beats.json').write_text(json.dumps(r,indent=2))
onsets=CNNOnsetProcessor()(str(src));np.save(p/'onset-activations.npy',onsets)
print('onsets',onsets.shape,'total_seconds',round(time.monotonic()-t,2),flush=True)
