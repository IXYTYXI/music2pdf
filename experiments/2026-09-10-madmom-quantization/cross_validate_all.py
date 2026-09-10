import json, hashlib, shutil, html
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path.cwd(); OUT=ROOT/'outputs/查看识谱结果/19-全段多模型交叉对照';OUT.mkdir(parents=True,exist_ok=True)
paths={'BP':'outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json','Piano':' .work/phrase-model-comparison/notes.json'.strip(),'Omni':' .work/omnizart/notes.json'.strip(),'OmniV2':'.work/omnizart/v2/notes.json'}
models={};manifest={}
for name,path in paths.items():
 raw=Path(path).read_bytes();ns=json.loads(raw);events=[]
 for i,n in enumerate(ns):
  start=n.get('start',n.get('onset_time'));duration=n['offset_time']-start if 'offset_time' in n else n['duration']
  events.append(dict(id=f'{name}:{i}',pitch=n.get('pitch',n.get('midi_note')),start=start,duration=duration,source_id=n.get('id')))
 models[name]=events;manifest[name]=dict(path=path,sha256=hashlib.sha256(raw).hexdigest(),events=len(events))
 archive=OUT/'原始输出';archive.mkdir(exist_ok=True);(archive/f'{name}.json').write_bytes(raw)
source=Path('outputs/feasibility-2026-09-10/samples/imslp-929871/audio/IMSLP579780.mp3')
manifest['audio']=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),duration=52.062)
shutil.copyfile(source,OUT/'原始录音.mp3')
rows=[]
def center(r):return float(np.median([n['start'] for n in r['models'].values()]))
def associate(events,rs,tolerance=.18):
 if not rs:return []
 cost=np.ones((len(events),len(rs)+len(events)))*10
 for i,n in enumerate(events):
  for j,r in enumerate(rs):
   dt=abs(n['start']-center(r))
   if n['pitch']==r['pitch'] and dt<=tolerance:cost[i,j]=dt
 ii,jj=linear_sum_assignment(cost)
 return [(i,j) for i,j in zip(ii,jj) if j<len(rs) and cost[i,j]<1]
for model,events in models.items():
 pairs=associate(events,rows);used=set()
 for i,j in pairs:rows[j]['models'][model]=events[i];used.add(i)
 for i,n in enumerate(events):
  if i not in used:rows.append(dict(pitch=n['pitch'],models={model:n}))
rows.sort(key=lambda r:(center(r),r['pitch']))
for i,r in enumerate(rows):r['id']=i+1;r['time']=center(r)
# AnthemScore is an external reference column; it never changes four-model groups.
anthem_path=Path('.work/anthemscore/comparison.json');ar=json.loads(anthem_path.read_text());anthem=ar['notes']
shutil.copyfile(anthem_path,OUT/'原始输出/AnthemScore-默认编排结果.json')
for i,j in associate(anthem,rows):rows[j]['anthem']=anthem[i]
for r in rows:
 ns=list(r['models'].values());r['missing_models']=[m for m in models if m not in r['models']]
 r['onset_spread_ms']=round(1000*(max(n['start'] for n in ns)-min(n['start'] for n in ns)),1)
 r['duration_spread_ms']=round(1000*(max(n['duration'] for n in ns)-min(n['duration'] for n in ns)),1)
 r['octave_neighbors']=[s['id'] for s in rows if abs(s['pitch']-r['pitch'])==12 and abs(s['time']-r['time'])<=.18]
 r['anthem_status']='matched' if 'anthem' in r else ('outside_coverage' if r['time']>=30 else 'unmatched_in_coverage')
 r['flags']=(['模型间有未匹配音'] if r['missing_models'] else [])+(['起音差异'] if r['onset_spread_ms']>80 else [])+(['时值差异'] if r['duration_spread_ms']>150 else [])+(['附近有八度候选'] if r['octave_neighbors'] else [])
# Every raw model event must appear exactly once, with unchanged pitch/time/duration.
for name,events in models.items():
 restored=[r['models'][name] for r in rows if name in r['models']]
 assert sorted(restored,key=lambda n:n['id'])==sorted(events,key=lambda n:n['id'])
summary=dict(events={m:len(ns) for m,ns in models.items()},rows=len(rows),disputed_rows=sum(bool(r['flags']) for r in rows),all_four_present=sum(len(r['models'])==4 for r in rows),anthem_matched_rows=sum('anthem' in r for r in rows),anthem_unmatched_events=[n for n in anthem if not any(r.get('anthem') is n for r in rows)])
report=dict(manifest=manifest,summary=summary,method='Incremental one-to-one equal-pitch matching within 180ms; order BP,Piano,Omni,OmniV2. Row labels are correspondence hypotheses, not ground truth. Each event preserved exactly once. AnthemScore attached afterwards; default arranged result only, coverage first30s. No original PDF used.',rows=rows)
(OUT/'完整对照数据.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
def note(p):return ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][p%12]+str(p//12-1)
def cell(n):return f"{n['start']:.3f}s<br>持续 {n['duration']:.3f}s" if n else '未匹配'
trs=[]
for r in rows:
 a=cell(r.get('anthem')) if r['anthem_status']!='outside_coverage' else '超出30秒覆盖'
 neighbors='、'.join(f'<a href="#r{x}">#{x}</a>' for x in r['octave_neighbors'])
 flags='；'.join(r['flags']) or '四模型在当前阈值内一致'
 trs.append(f'<tr id="r{r["id"]}" data-disputed="{int(bool(r["flags"]))}"><td>#{r["id"]}<br><button onclick="seek({max(0,r["time"]-1):.3f})">听 {r["time"]:.2f}s</button></td><th>{note(r["pitch"])}</th>'+''.join('<td>'+cell(r['models'].get(m))+'</td>' for m in models)+f'<td>{a}</td><td>{flags}<br>{neighbors}</td></tr>')
page='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>全段音符交叉对照</title><style>body{font:16px/1.6 system-ui;margin:24px;color:#172536}h1{font-size:28px}.player{position:sticky;top:0;background:#fff;padding:10px;box-shadow:0 1px 5px #aaa}audio{width:min(700px,90vw)}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccd4df;padding:8px;text-align:left}tr:target{background:#fff0b0}button{cursor:pointer;padding:7px}.notice{background:#fff3d0;padding:15px}th{background:#f1f5fa}</style>
<h1>52 秒录音：保留各模型输出，逐处交叉对照</h1>
<p>BP 233 个音符 · 钢琴模型 234 个 · Omnizart Piano 198 个 · PianoV2 167 个。没有删音、合并音符或改动时间。</p>
<p class="notice">“未匹配”不等于漏音；“附近有八度候选”不等于识别错了，也可能是真实八度和弦。先定位分歧，再核查。两个 Omnizart 版本不是独立两票。</p>
<p>同音高、起音差不超过180毫秒做一对一关联；分组顺序 BP→钢琴模型→Omni→OmniV2，关联可能受顺序影响。起音差超过80毫秒、时值差超过150毫秒分别标记。重复音可能被分到不同组，应结合附近行听。</p>
<p>AnthemScore 列在分组完成后附加，不充当答案。现有默认编排结果只覆盖前30秒；后22秒尚无它的结果。原谱没有参与本表分组；这里展示的是模型分歧，不是准确率评分。</p>
<div class="player"><audio id="audio" controls src="原始录音.mp3"></audio><br><label><input id="only" type="checkbox" checked onchange="filter()">只显示有分歧的行</label><span id="count"></span></div>
<table><thead><tr><th>位置</th><th>音高</th><th>BP</th><th>钢琴模型</th><th>Omni Piano</th><th>Omni PianoV2</th><th>AnthemScore复核</th><th>分歧与附近八度音</th></tr></thead><tbody>'''+''.join(trs)+'''</tbody></table><script>function seek(t){const a=document.getElementById('audio');a.currentTime=t;a.play().catch(()=>{});}function filter(){let n=0;document.querySelectorAll('tbody tr').forEach(r=>{const show=!document.getElementById('only').checked||r.dataset.disputed==='1';r.hidden=!show;if(show)n++;});document.getElementById('count').textContent=' 当前显示 '+n+' 组';}filter();</script></html>'''
focus=[r for r in rows if 27.45<r['time']<27.85 and r['pitch'] in (52,64)]
links=' · '.join(f'<a href="#r{r["id"]}">{note(r["pitch"])} / {r["time"]:.3f}秒</a>' for r in focus)
page=page.replace('<div class="player">','<h2>先看已知的 E3/E4 分歧</h2><p>'+links+'</p><p>该处原谱已核对为 E3；本表没有用原谱修改任何模型输出。BP 的晚起 E3 被分在另一个组中，说明关联阈值也会影响分组，不能把不同组直接解释成不同音符。</p><div class="player">')
(OUT/'先看这里.html').write_text(page)
print(json.dumps(summary,ensure_ascii=False,indent=2))
