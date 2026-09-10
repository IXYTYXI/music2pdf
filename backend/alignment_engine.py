"""Chroma DTW produces candidate measure times, not verified note labels."""
import math
import numpy as np


def match_features(reference, audio, step):
    import librosa
    ref=reference / np.maximum(np.linalg.norm(reference,axis=0,keepdims=True),1e-8)
    aud=audio / np.maximum(np.linalg.norm(audio,axis=0,keepdims=True),1e-8)
    cost=np.clip(1-ref.T@aud,0,2)
    # Positive feature changes help anchor attacks inside sustained harmonies.
    ron=np.maximum(np.diff(ref,axis=1,prepend=np.zeros((12,1))),0)
    aon=np.maximum(np.diff(aud,axis=1,prepend=np.zeros((12,1))),0)
    onset_cost=np.maximum(np.sum(ron*ron,axis=0)[:,None]+np.sum(aon*aon,axis=0)[None,:]-2*ron.T@aon,0)
    cost+=0.2*onset_cost
    roff=np.maximum(-np.diff(ref,axis=1,append=np.zeros((12,1))),0)
    aoff=np.maximum(-np.diff(aud,axis=1,append=np.zeros((12,1))),0)
    cost+=0.2*np.maximum(np.sum(roff*roff,axis=0)[:,None]+np.sum(aoff*aoff,axis=0)[None,:]-2*roff.T@aoff,0)
    if min(cost.shape)<3:raise ValueError('选定片段过短，无法对齐。')
    steps_allowed=np.array([[1,1],[1,2],[2,1],[1,3],[3,1]])
    accumulated,steps=librosa.sequence.dtw(C=cost,subseq=True,step_sizes_sigma=steps_allowed,backtrack=False,return_steps=True)
    end=int(np.argmin(accumulated[-1]))
    if not np.isfinite(accumulated[-1,end]):raise ValueError('未找到可行匹配路径，请检查速度和片段范围。')
    # Explicit backtracking preserves score/audio axes even when score has more frames.
    wp=librosa.sequence.dtw_backtracking(steps,step_sizes_sigma=steps_allowed,subseq=True,start=end)[::-1]
    indices=np.unique(wp[:,0]);seconds=np.array([np.median(wp[wp[:,0]==i,1])*step for i in indices])
    return indices*step,seconds,float(np.mean(cost[wp[:,0],wp[:,1]]))


def align(timeline, audio_path, measure_start, measure_end, audio_start, audio_end):
    import librosa
    if not 1<=measure_start<=measure_end<=len(timeline['measures']):raise ValueError('小节范围无效。')
    if not all(math.isfinite(x) for x in (audio_start,audio_end)) or audio_start<0 or audio_end<=audio_start:raise ValueError('音频起止时间无效。')
    duration=float(librosa.get_duration(path=str(audio_path)))
    if audio_end>duration+0.1:raise ValueError('结束时间超出录音长度。')
    measures=timeline['measures'][measure_start-1:measure_end]
    begin,finish=measures[0]['start'],measures[-1]['end']
    # Reduce feature rate for long pairs rather than allocate an unbounded DTW matrix.
    step=max(0.1,math.sqrt((finish-begin)*(audio_end-audio_start)/2_000_000)*1.05)
    if finish<=begin:raise ValueError('乐谱片段没有时长。')
    ref=np.zeros((12,max(3,math.ceil((finish-begin)/step))),dtype=np.float32)
    for n in timeline['notes']:
        start=max(n['start'],begin);end=min(n['end'],finish)
        if end>start:
            lo=max(0,int((start-begin)/step));hi=min(ref.shape[1],max(lo+1,math.ceil((end-begin)/step)))
            ref[round(n['midi'])%12,lo:hi]+=1
    if not np.any(ref):raise ValueError('乐谱片段没有音符。')
    y,sr=librosa.load(str(audio_path),sr=22050,mono=True,offset=audio_start,duration=audio_end-audio_start)
    if len(y)<4096 or np.max(np.abs(y))<1e-5:raise ValueError('录音片段过短或接近静音。')
    hop=max(512,round(step*sr))
    # Actual hop defines the common reference/audio time resolution.
    actual=hop/sr
    if abs(actual-step)>1e-8:
        new_times=np.arange(0,finish-begin,actual)
        ref=np.array([np.interp(new_times,np.arange(ref.shape[1])*step,row) for row in ref],dtype=np.float32)
    chroma=librosa.feature.chroma_stft(y=y,sr=sr,n_fft=4096,hop_length=hop,tuning=0)
    x,ytime,cost=match_features(ref,chroma,actual)
    boundaries=[m['start']-begin for m in measures]+[finish-begin]
    mapped=np.interp(boundaries,x,ytime)+audio_start
    mapped[-1]=min(audio_end,mapped[-1]+actual)
    rows=[]
    for i,m in enumerate(measures):
        rows.append({'id':m['id'],'number':m['number'],'occurrence':m['occurrence'],'meter':m['meter'],'theory_start':m['start'],'theory_end':m['end'],'start':round(float(mapped[i]),3),'end':round(float(mapped[i+1]),3),'matched':True})
    warnings=list(timeline['warnings'])
    warnings+=['自动对齐是候选结果，未经人工标注评估；匹配代价不是准确率。','本版支持连续页段的速度变化，不自动解决任意删节、跳段或不同编配。']
    if cost>0.55:warnings.append('整体匹配代价较高，请检查录音、版本、速度与选定片段是否对应。')
    if any(r['end']<=r['start'] for r in rows):warnings.append('部分小节被压缩到相同时间，需手动修正或标为不匹配。')
    return {'rows':rows,'matching_cost':cost,'resolution_seconds':actual,'warnings':warnings,'reviewed':False,'training_ready':False,'algorithm':'chroma-subsequence-dtw-v1','audio_window':[audio_start,audio_end]}


def validate_corrections(rows, original, duration):
    if [r['id'] for r in rows]!=[r['id'] for r in original]:raise ValueError('小节编号或数量发生变化。')
    previous=-1
    for r in rows:
        a,b=r['start'],r['end']
        if not all(math.isfinite(v) for v in (a,b)) or a<0 or b<a or b>duration:raise ValueError('时间必须位于录音范围内，结束不能早于开始。')
        if r['matched']:
            if b<=a or a<previous:raise ValueError('已匹配小节须按时间顺序排列且不能重叠。')
            previous=b
