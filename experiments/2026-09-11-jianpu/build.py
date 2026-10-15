from pathlib import Path
import json,sys,math
import numpy as np
sys.path.insert(0,str(Path('experiments/2026-09-11-numbered-preview').resolve()))
from numbered import symbol
out=Path('outputs/查看识谱结果/21-简谱初稿');out.mkdir(parents=True,exist_ok=True)
ns=json.loads(Path('outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json').read_text())
beats=np.array(json.loads(Path('.work/madmom-quantization/beats.json').read_text())['candidates']['joint']['beats'])[:,0]
def tick(t):
 i=int(np.clip(np.searchsorted(beats,t)-1,0,len(beats)-2))
 return max(0,int(math.floor((i+(t-beats[i])/(beats[i+1]-beats[i]))*4+.5)))
groups={}
for n in ns:
 a=tick(n['start']);z=max(a+1,tick(n['start']+n['duration']))
 groups.setdefault((a,z),[]).append(n)
lanes=[]
for (a,z),notes in sorted(groups.items()):
 lane=next((l for l in lanes if l[-1]['end']<=a),None)
 if lane is None:lane=[];lanes.append(lane)
 lane.append(dict(start=a,end=z,notes=notes))
assert sum(len(g['notes']) for l in lanes for g in l)==len(ns)
# Rhythmic units in sixteenth-note ticks; long values use extension dashes.
def units(a,z):
 result=[]
 while a<z:
  left=z-a
  choices=[4,3,2,1] # split at beat boundaries for legible ties
  size=next(k for k in choices if k<=left and k<=4-a%4)
  result.append((a,size));a+=size
 return result
W=1200;left=85;barw=535;step=barw/12;bars=math.ceil(max(g['end'] for l in lanes for g in l)/12)
parts=[]
def text(x,y,s,size=24,extra=''):
 parts.append(f'<text x="{x}" y="{y}" font-size="{size}" {extra}>{s}</text>')
def line(x,y,xx,yy):parts.append(f'<path d="M{x},{y} L{xx},{yy}" stroke="#20352c" fill="none"/>')
def glyph(x,y,pitch,size):
 d,octave=symbol(pitch) if pitch is not None else ('0',0)
 text(x,y,d,25,'text-anchor="middle" font-weight="600"')
 for i in range(abs(octave)):
  cy=y-30-i*6 if octave>0 else y+8+i*6
  parts.append(f'<circle cx="{x}" cy="{cy}" r="1.8"/>')
 count=2 if size==1 else 1 if size in (2,3) else 0
 for j in range(count):line(x-9,y+20+j*5,x+9,y+20+j*5)
 if size==3:text(x+15,y,'·',24)
text(30,45,'录音直接识别 · 简谱初稿',30)
text(30,79,'1=C　　3/4　　参考速度 ♩≈94　　BP 原始识别 → 拍点量化 → 数字记谱',17)
text(30,107,'未校正错音；拍号为试排设置，小节起点未验收。各行是排版声部，不等于左右手。',16)
text(30,132,'上/下点：八度　　数字下横线：短时值　　0：该声部休止　　弧线：同一音持续',16)
y=175
for bar0 in range(0,bars,2):
 active=[(i,l) for i,l in enumerate(lanes) if any(g['start']<(bar0+2)*12 and g['end']>bar0*12 for g in l)]
 for i,lane in active:
  maxch=max([len(g['notes']) for g in lane if g['start']<(bar0+2)*12 and g['end']>bar0*12] or [1]);height=max(90,maxch*65+25)
  base=y+40+(maxch-1)*65
  text(15,base,f'声部{i+1}',13)
  for b in range(bar0,min(bar0+2,bars)):
   bx=left+(b-bar0)*barw;text(bx+5,y-4,str(b+1),12)
   line(bx,y+8,bx,y+height-4);line(bx+barw,y+8,bx+barw,y+height-4)
   a,z=b*12,(b+1)*12;cursor=a
   selected=[g for g in lane if g['start']<z and g['end']>a]
   events=[]
   for g in selected:
    start=max(a,g['start']);end=min(z,g['end'])
    if cursor<start:events.append((cursor,start,None))
    events.append((start,end,g));cursor=end
   if cursor<z:events.append((cursor,z,None))
   for start,end,g in events:
    chunks=units(start,end);notes=sorted(g['notes'],key=lambda n:n['pitch']) if g else [None]
    for ni,n in enumerate(notes):
     yy=base-ni*65
     for ci,(t,dur) in enumerate(chunks):
      x=bx+(t-a)*step+step*.45
      # Quarter continuation is a dash; short continuations repeat with a tie.
      continuation=g is not None and t>g['start']
      if continuation and dur==4 and t%4==0:
       text(x,yy,'−',25,'text-anchor="middle"')
      else:
       glyph(x,yy,n['pitch'] if n else None,dur)
       if continuation:
        parts.append(f'<path d="M{x-25},{yy-37} Q{x-12},{yy-49} {x},{yy-37}" fill="none" stroke="#20352c"/>')
  y+=height
 y+=34
svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {y+15}" width="{W}" height="{y+15}" style="font-family:system-ui,sans-serif;fill:#20352c;background:white">'+''.join(parts)+'</svg>'
(out/'简谱初稿.svg').write_text(svg)
(out/'先看简谱.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>简谱初稿</title><style>body{margin:0;background:#eee;padding:20px}svg{display:block;width:100%;height:auto;max-width:1200px;margin:auto;background:white}p{max-width:1200px;margin:0 auto 14px;font:16px system-ui}</style><p>这是简谱初稿，保留识别结果中的错误。可放大查看；<a href="简谱初稿.svg" download>下载完整简谱图</a>。</p>'+svg+'</html>')
(out/'验收记录.json').write_text(json.dumps(dict(input_notes=len(ns),rendered_source_notes=sum(len(g['notes']) for l in lanes for g in l),lanes=len(lanes),bars=bars,meter='3/4 fixed trial',origin='first detected beat, unverified',source='raw BP JSON, not MusicXML or PDF'),indent=2))
print('notes',len(ns),'lanes',len(lanes),'bars',bars)
