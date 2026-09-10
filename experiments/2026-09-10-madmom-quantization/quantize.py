from pathlib import Path
import json
import argparse
import numpy as np
from scipy.signal import find_peaks
from rhythm_cleanup import clean_score_stream
parser=argparse.ArgumentParser()
parser.add_argument('--notes', default='outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json')
parser.add_argument('--output-dir', default='.work/madmom-quantization')
args=parser.parse_args()
p=Path('.work/madmom-quantization')
out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
notes=json.loads(Path(args.notes).read_text())
b=np.array(json.loads((p/'beats.json').read_text())['candidates']['joint']['beats'])[:,0]
median=float(np.median(np.diff(b)))
def interp(t,x,y):
 i=int(np.clip(np.searchsorted(x,t)-1,0,len(x)-2))
 return float(y[i]+(t-x[i])/(x[i+1]-x[i])*(y[i+1]-y[i]))
def beat(t):return interp(t,b,np.arange(len(b)))
def seconds(q):return interp(q,np.arange(len(b)),b)
cases={};summary=[]
for label,variable,interval,subdivision in [('fixed120',False,.5,4),('fixed94',False,median,4),('dynamic16',True,median,4),('dynamic8',True,median,2)]:
 transformed=[];deltas=[];duration_deltas=[];collapsed=[]
 for n in notes:
  a=beat(n['start']) if variable else (n['start']-b[0])/interval
  z=beat(n['start']+n['duration']) if variable else (n['start']+n['duration']-b[0])/interval
  start=max(0,float(np.floor(a*subdivision+.5)/subdivision))
  end=max(start+1/subdivision,float(np.floor(z*subdivision+.5)/subdivision))
  t=seconds(start) if variable else b[0]+start*interval
  stop=seconds(end) if variable else b[0]+end*interval
  deltas.append(float(t-n['start']));duration_deltas.append(float((stop-t)-n['duration']))
  transformed.append({**n,'start':start,'duration':end-start,'raw_start':a,'raw_end':z})
 transformed,cleanup_changes=clean_score_stream(transformed,subdivision=subdivision)
 # Recompute after optional, explicitly supported duration repairs.
 duration_deltas=[]
 for original,cleaned in zip(notes,transformed):
  a,z=cleaned['start'],cleaned['start']+cleaned['duration']
  length=seconds(z)-seconds(a) if variable else (z-a)*interval
  duration_deltas.append(length-original['duration'])
 for i,n in enumerate(transformed):
  for prev in transformed[:i]:
   if prev['pitch']==n['pitch'] and prev['start']==n['start'] and prev['id']!=n['id']:collapsed.append([prev['id'],n['id']])
 assert len(transformed)==len(notes)
 cases[label]=transformed
 summary.append({'case':label,'events':len(notes),'cleanup_changes':cleanup_changes,'onset_median_shift_ms':float(np.median(abs(np.array(deltas)))*1000),'onset_p95_shift_ms':float(np.percentile(abs(np.array(deltas)),95)*1000),'onsets_moved_over_80ms':int(sum(abs(np.array(deltas))>.08)),'duration_p95_change_ms':float(np.percentile(abs(np.array(duration_deltas)),95)*1000),'same_pitch_onset_collisions':collapsed,'limit':'Grid origin is first detected beat only, NOT an inferred first downbeat. Meter/phase not selected by this comparison.'})
(out/'cases.json').write_text(json.dumps(cases,indent=2));(out/'quantization.json').write_text(json.dumps(summary,indent=2))
act=np.load(p/'onset-activations.npy');peaks,_=find_peaks(act,height=.3,distance=8)
checks=[]
for label,t in [('A4_first',14.4866),('A4_fragment',14.7653),('C5_first',17.6690),('C5_fragment',18.0418),('E5_repeat_first',11.2799),('E5_repeat_second',11.9182)]:
 nearest=int(peaks[np.argmin(abs(peaks/100-t))]);lo=max(0,round((t-.05)*100));hi=round((t+.05)*100)+1
 checks.append({'label':label,'time':t,'nearest_global_onset':nearest/100,'distance_ms':abs(nearest/100-t)*1000,'local_max_activation':float(max(act[lo:hi])),'limit':'Global onset cannot identify which pitch or hand was struck. Not permission to merge or delete.'})
(out/'onset-checks.json').write_text(json.dumps(checks,indent=2));print(json.dumps(summary,indent=2));print(json.dumps(checks,indent=2))
