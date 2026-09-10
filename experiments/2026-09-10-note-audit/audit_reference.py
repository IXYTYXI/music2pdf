import json
from pathlib import Path
import numpy as np,soundfile as sf
p=Path('.work/phrase-audit');src='outputs/feasibility-2026-09-10/samples/imslp-929871/audio/IMSLP579780.mp3';y,sr=sf.read(src,always_2d=True);y=y.mean(axis=1)
# Manual transcription of original PDF, post-inference evaluation only.
bars=[([79,81,76],[60,67,60]),([77,76,77,79,77],[62,69,62]),([77,79,74],[62,71,67]),([76,74,76,77,76],[60,67,60]),([76,72,76],[57,64,57]),([76,77,79,81,77],[62,69,62]),([79,81,76],[59,67,59]),([72],[60,55,48])]
beats=np.array(json.loads(Path('.work/full-music-analysis/analysis.json').read_text())['families'][1]['beat_times'])
expected=[]
for m,(rh,lh) in enumerate(bars):
 for hand,ns in [('right',rh),('left',lh)]:
  positions=[0,.5,1,1.5,2] if len(ns)==5 else list(range(len(ns)))
  for j,(pitch,beat) in enumerate(zip(ns,positions)):
   t=float(np.interp(m*3+beat,np.arange(len(beats)),beats));expected.append({'measure':m+1,'hand':hand,'beat':beat+1,'pitch':pitch,'candidate_time':t,'duration_beats':.5 if len(ns)==5 and j<4 else 1})
raw=json.loads(Path('outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json').read_text());events=[n for n in raw if 4.25<=n['start']<19.65];free=set(range(len(events)))
for e in sorted(expected,key=lambda n:n['candidate_time']):
 candidates=[i for i in free if events[i]['pitch']==e['pitch'] and abs(events[i]['start']-e['candidate_time'])<=.18]
 if candidates:
  i=min(candidates,key=lambda i:abs(events[i]['start']-e['candidate_time']));free.remove(i);e['matched_model']=events[i];e['onset_delta_ms']=(events[i]['start']-e['candidate_time'])*1000
 else:e['matched_model']=None
# Quantify frequency evidence independently from raw PCM. Not a note ground-truth classifier.
windows=[]
for label,a,b,pitches in [('bar4_expected_E5',11.34,11.47,[76,77]),('bar4_delayed_E5',11.63,11.77,[76,77]),('bar6_expected_A5',14.82,14.96,[79,81]),('bar8_same_quarter_note',18.10,18.26,[72]),('bar2_low_G2',6.29,6.43,[43,62,77])]:
 z=y[round(a*sr):round(b*sr)];N=262144;mag=abs(np.fft.rfft(z*np.hanning(len(z)),n=N));freq=np.fft.rfftfreq(N,1/sr);rows=[]
 for pitch in pitches:
  f=440*2**((pitch-69)/12);ix=np.flatnonzero(abs(freq-f)<6);j=ix[np.argmax(mag[ix])];rows.append({'pitch':pitch,'frequency_peak':float(freq[j]),'amplitude':float(mag[j])})
 maximum=max(r['amplitude'] for r in rows)
 for r in rows:r['db_relative_strongest_listed']=20*np.log10(max(r['amplitude'],1e-12)/maximum)
 windows.append({'label':label,'start':a,'end':b,'bands':rows,'limit':'Zero padding does not increase true frequency resolution; local energy does not prove independent key attack.'})
result={'scope':'First eight score measures up to repeat boundary; original-recording 4.25-19.65 seconds. Beat-projected correspondence is not manual audio timing truth.','expected':expected,'unmatched_model':[events[i] for i in sorted(free)],'model_event_count':len(events),'reference_note_count':len(expected),'matched_count':sum(e['matched_model'] is not None for e in expected),'spectral_windows':windows}
(p/'audit.json').write_text(json.dumps(result,indent=2));print('notes',len(events),'ref',len(expected),'matches',result['matched_count']);print('unmatched expected',[(e['measure'],e['beat'],e['pitch'],round(e['candidate_time'],3)) for e in expected if not e['matched_model']]);print('extras',[(round(n['start'],3),n['pitch']) for n in result['unmatched_model']]);print(json.dumps(windows,indent=2))
