"""Symbolic score time is a reference, never measured performance time."""
import math
from pathlib import Path
from music21 import converter, tempo, stream, expressions


def read_timeline(path, fallback_bpm=None, repeats=True):
    if fallback_bpm is not None and (not math.isfinite(fallback_bpm) or not 10 <= fallback_bpm <= 600):
        raise ValueError('初始速度须为10–600个四分音符/分钟。')
    score = converter.parse(str(path), forceSource=True)
    warnings=[]
    if repeats:
        try: score=score.expandRepeats()
        except Exception as exc: raise ValueError('反复结构无法自动展开，请在 MuseScore 展开或修正后重试。') from exc
    else: warnings.append('本次按书写顺序读取，未展开反复。')
    score=score.toSoundingPitch()
    parts=list(score.parts)
    if not parts: raise ValueError('乐谱没有可读取的声部。')
    changes={}
    for mark in score.recurse().getElementsByClass(tempo.MetronomeMark):
        bpm=mark.getQuarterBPM()
        if bpm and not mark.numberImplicit:
            if not math.isfinite(bpm) or not 10<=bpm<=600:raise ValueError('乐谱速度超出10–600 BPM范围，请先校对。')
            offset=float(mark.getOffsetInHierarchy(score))
            if offset in changes and abs(changes[offset]-bpm)>0.01:warnings.append('声部间存在不同速度标记，使用先出现的标记，请核对。')
            changes.setdefault(offset,float(bpm))
    if not changes or min(changes)>0:
        if fallback_bpm is None:raise ValueError('开头没有明确的数值速度，请填写初始速度；Allegro等文字不作为确定BPM。')
        changes[0]=float(fallback_bpm);warnings.append('起始速度由用户提供，为理论时间参考。')
    offsets=sorted(changes)
    def seconds(quarter):
        result=0.0
        for i,start in enumerate(offsets):
            if start>=quarter:break
            end=offsets[i+1] if i+1<len(offsets) else quarter
            result+=max(0,min(end,quarter)-start)*60/changes[start]
        return result
    events=[]
    expressive=False
    for pi,part in enumerate(parts):
        for n in part.recurse().notes:
            if any(isinstance(e,expressions.Fermata) for e in n.expressions):expressive=True
            duration=float(n.quarterLength)
            if duration<=0:continue
            offset=float(n.getOffsetInHierarchy(score))
            pitches=getattr(n,'pitches',[])
            for pitch in pitches:
                events.append({'part':pi,'midi':float(pitch.ps),'quarter':offset,'duration_quarter':duration,'start':seconds(offset),'end':seconds(offset+duration)})
    if not events:raise ValueError('乐谱没有可用于对齐的有音高音符。')
    measures=[];occurrences={}
    first=list(parts[0].getElementsByClass(stream.Measure))
    for i,m in enumerate(first):
        start=float(m.offset);end=float(first[i+1].offset) if i+1<len(first) else max(float(score.highestTime),start+float(m.duration.quarterLength))
        number=str(m.number)+str(m.numberSuffix or '')
        occurrences[number]=occurrences.get(number,0)+1
        ts=m.timeSignature or m.getContextByClass('TimeSignature')
        measures.append({'id':i+1,'number':number,'occurrence':occurrences[number],'quarter':start,'end_quarter':end,'start':seconds(start),'end':seconds(end),'meter':ts.ratioString if ts else '?','bpm':changes[max(x for x in offsets if x<=start)]})
    if not measures:raise ValueError('乐谱缺少小节结构。')
    if expressive:warnings.append('存在延长记号；理论时长未推断演奏者实际延长量。')
    warnings.append('渐快、渐慢、自由速度及实际发声起止需录音匹配和人工核对。')
    return {'measures':measures,'notes':events,'tempos':[{'quarter':q,'quarter_bpm':changes[q]} for q in offsets],'parts':len(parts),'duration':seconds(float(score.highestTime)),'warnings':list(dict.fromkeys(warnings)),'timing':'theoretical','repeats_expanded':repeats}
