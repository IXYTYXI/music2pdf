from pathlib import Path
import json,csv,copy
import pretty_midi
p=Path('.work/phrase-model-comparison')
a=json.loads(Path('.work/phrase-audit/audit.json').read_text())
raw=json.loads(Path('outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json').read_text())
piano=[{'pitch':n['midi_note'],'start':n['onset_time'],'duration':n['offset_time']-n['onset_time'],'velocity':n['velocity']} for n in json.loads((p/'notes.json').read_text())]
result={}
for name,allnotes in [('Basic Pitch',raw),('钢琴专用模型',piano)]:
 notes=[n for n in allnotes if 4.25<=n['start']<19.65]
 expected=copy.deepcopy(a['expected']);free=set(range(len(notes)))
 for e in sorted(expected,key=lambda e:e['candidate_time']):
  candidates=[i for i in free if notes[i]['pitch']==e['pitch'] and abs(notes[i]['start']-e['candidate_time'])<=.18]
  i=min(candidates,key=lambda i:abs(notes[i]['start']-e['candidate_time'])) if candidates else None
  e['matched_model']=notes[i] if i is not None else None
  if i is not None:free.remove(i)
 result[name]={'count':len(notes),'paired':len(notes)-len(free),'expected':expected,'unpaired':[notes[i] for i in sorted(free)],'key_windows':{label:[n for n in notes if lo<n['start']<hi and n['pitch'] in pitches] for label,lo,hi,pitches in [('E5_F5',10.9,11.9,[76,77]),('A4_repeat',14.3,15.2,[69]),('C5_repeat',17.5,18.5,[72])]}}
 midi=pretty_midi.PrettyMIDI();inst=pretty_midi.Instrument(0)
 for n in notes:
  inst.notes.append(pretty_midi.Note(velocity=85,pitch=int(n['pitch']),start=n['start']-4.25,end=min(n['start']+n['duration'],19.65)-4.25))
 midi.instruments.append(inst);midi.write(str(p/('basic.mid' if name=='Basic Pitch' else 'piano.mid')))
(p/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
for name,r in result.items():
 print(name,json.dumps({k:v for k,v in r.items() if k not in ('expected','unpaired')},ensure_ascii=False))
 print('unpaired',[(round(n['start'],3),n['pitch']) for n in r['unpaired']])
 print('missing',[(e['measure'],e['beat'],e['pitch']) for e in r['expected'] if e['matched_model'] is None])
