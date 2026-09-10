"""First-phrase experiment: generate without reference, then evaluate separately."""
import json
from pathlib import Path
import numpy as np
from consensus import corroborate

out = Path('.work/phrase-consensus')
out.mkdir(parents=True, exist_ok=True)
bp = json.loads(Path('outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json').read_text())
bp = [n for n in bp if 4.25 <= n['start'] < 19.65]
piano = [dict(id=f'piano-{i}', pitch=n['midi_note'], start=n['onset_time'],
              duration=n['offset_time']-n['onset_time'], velocity=n['velocity']/127, track='piano')
         for i,n in enumerate(json.loads(Path('.work/phrase-model-comparison/notes.json').read_text()))]
omni = [json.loads(Path(p).read_text()) for p in ('.work/omnizart/notes.json', '.work/omnizart/v2/notes.json')]
kept, rejected = corroborate(bp, [piano, *omni])
# A missing BP event requires piano + Omnizart support, not two Omnizart votes.
supported_piano, _ = corroborate(piano, omni)
_, absent_bp = corroborate(supported_piano, [bp])
added = [n for n in absent_bp if 4.25 <= n['start'] < 19.65]
candidate = sorted(kept+added, key=lambda n:(n['start'],n['pitch']))
(out/'candidate.json').write_text(json.dumps(candidate, indent=2))
(out/'changes.json').write_text(json.dumps(dict(rejected=rejected, added=added), indent=2))

beats = np.array(json.loads(Path('.work/madmom-quantization/beats.json').read_text())['candidates']['joint']['beats'])[:,0]
def beat(t):
    i=int(np.clip(np.searchsorted(beats,t)-1, 0, len(beats)-2))
    return i+(t-beats[i])/(beats[i+1]-beats[i])
def quantize(ns):
    result=[]
    for n in ns:
        a=max(0,float(np.floor(beat(n['start'])*4+.5)/4))
        z=max(a+.25,float(np.floor(beat(n['start']+n['duration'])*4+.5)/4))
        result.append({**n,'start':a,'duration':z-a})
    return result
(out/'cases.json').write_text(json.dumps({'before':quantize(bp),'candidate':quantize(candidate)}, indent=2))

# Reference only enters AFTER candidate and rendering inputs have been saved.
reference=json.loads(Path('.work/phrase-audit/audit.json').read_text())['expected']
def evaluate(ns, tolerance):
    pairs=sorted((abs(n['start']-e['candidate_time']),i,j)
                 for i,n in enumerate(ns) for j,e in enumerate(reference)
                 if n['pitch']==e['pitch'] and abs(n['start']-e['candidate_time'])<=tolerance)
    used_n,used_e=set(),set()
    for _,i,j in pairs:
        if i not in used_n and j not in used_e: used_n.add(i);used_e.add(j)
    return dict(events=len(ns), matched=len(used_n), unmatched=len(ns)-len(used_n), missing=len(reference)-len(used_e),
                missing_reference=[dict(measure=e['measure'],beat=e['beat'],pitch=e['pitch']) for j,e in enumerate(reference) if j not in used_e])
report=dict(scope_seconds=[4.25,19.65], reference_events=len(reference),
            inference_onset_tolerance_seconds=.1,
            limits=['Beat-projected reference times are not hand-labeled audio onsets.',
                    'Same central-C staff split and duration quantization in both versions.',
                    'Meter 3/4 is a fixed comparison setting, not newly inferred.',
                    'Model agreement is not truth; candidate is not production.'],
            evaluations={str(t):{'before':evaluate(bp,t),'candidate':evaluate(candidate,t)} for t in (.05,.1,.18)})
(out/'evaluation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
