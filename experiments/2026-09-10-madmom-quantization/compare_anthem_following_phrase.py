import json
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
Path('.work/expanded-comparison').mkdir(parents=True, exist_ok=True)
beats=np.array(json.loads(Path('.work/madmom-quantization/beats.json').read_text())['candidates']['joint']['beats'])[:,0]
bars=[([67,69,64],[60,60,60]),([67,71,67],[59,57,55,57,59]),([69,72,69],[57,57,57]),([67,71,64],[55,53,52,53,55]),([69,72,65],[53,52,50,52,53])]
ref=[]
for i,(rh,lh) in enumerate(bars):
 for staff,ns in [(1,rh),(2,lh)]:
  positions=[0,.5,1,1.5,2] if len(ns)==5 else [0,1,2]
  for j,(pitch,pos) in enumerate(zip(ns,positions)):
   q=24+3*i+pos;dur=.5 if len(ns)==5 and j<4 else 1
   t=float(np.interp(q,np.arange(len(beats)),beats));end=float(np.interp(q+dur,np.arange(len(beats)),beats))
   ref.append(dict(measure=i+9,beat=pos+1,staff=staff,pitch=pitch,start=t,duration=end-t))
Path('.work/expanded-comparison/reference.json').write_text(json.dumps(ref,indent=2))
bp=json.loads(Path('outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json').read_text());bp=[{**n,'staff':1 if n['pitch']>=60 else 2} for n in bp]
anthem=json.loads(Path('.work/anthemscore/comparison.json').read_text())['notes'];anthem=[{**n,'staff':int(n['staff'])} for n in anthem]
models={k:[n for n in ns if 19.5<=n['start']<29.05] for k,ns in [('BP',bp),('AnthemScore',anthem)]}
results={}
for name,ns in models.items():
 results[name]={}
 for tol in [.05,.1,.18]:
  cost=np.ones((len(ref),len(ns)+len(ref)))*10
  for i,e in enumerate(ref):
   for j,n in enumerate(ns):
    dt=abs(e['start']-n['start'])
    if e['pitch']==n['pitch'] and dt<=tol:cost[i,j]=dt
  rows,cols=linear_sum_assignment(cost);pairs=[(i,j) for i,j in zip(rows,cols) if j<len(ns) and cost[i,j]<1]
  usedr={i for i,j in pairs};usedn={j for i,j in pairs}
  results[name][str(tol)]=dict(events=len(ns),matched=len(pairs),unmatched=len(ns)-len(pairs),missing=len(ref)-len(pairs),wrong_staff=sum(ref[i]['staff']!=ns[j]['staff'] for i,j in pairs),duration_errors_over_150ms=sum(abs(ref[i]['duration']-ns[j]['duration'])>.15 for i,j in pairs),missing_reference=[e for i,e in enumerate(ref) if i not in usedr],unmatched_events=[n for j,n in enumerate(ns) if j not in usedn])
report=dict(scope='Original score measures 9-13; recording 19.5-29.05 seconds; no repeated section in this excerpt',reference_count=len(ref),new_inference=False,reference_input_to_tools=False,limits=['AnthemScore is existing default arrangement output, not raw notes.','Reference onset and duration seconds are projected from madmom beats, not manually annotated audio truth.','BP staff is our exporter central-C rule, not acoustic model output.','Same piece only; this does not establish cross-piece accuracy.'],results=results)
Path('.work/expanded-comparison/results.json').write_text(json.dumps(report,indent=2))
for name,rs in results.items():
 for t,r in rs.items(): print(name,t,{k:v for k,v in r.items() if not isinstance(v,list)})
