"""Run numerical imports and alignment outside the web server's thread pool."""
import hashlib,json,sys
from pathlib import Path
from alignment_engine import align
from score_timeline import read_timeline


def run(folder):
    spec=json.loads((folder/'worker-input.json').read_text());v=spec['request'];audio=Path(spec['audio_path'])
    before=audio.stat()
    with audio.open('rb') as f:audio_hash=hashlib.file_digest(f,'sha256').hexdigest()
    timeline=read_timeline(folder/'input.musicxml',v['bpm'],v['repeats'])
    proposal=align(timeline,audio,v['measure_start'],v['measure_end'],v['audio_start'],v['audio_end'])
    after=audio.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('对齐期间录音变化，请重试。')
    with (folder/'input.musicxml').open('rb') as f:score_hash=hashlib.file_digest(f,'sha256').hexdigest()
    proposal.update(score_sha256=score_hash,audio_sha256=audio_hash,audio_path=str(audio),score_source=spec['score_source'],tempo_fallback=v['bpm'])
    tmp=folder/'automatic.tmp';tmp.write_text(json.dumps(proposal,ensure_ascii=False,allow_nan=False));tmp.replace(folder/'automatic.json')

if __name__=='__main__':
    try:run(Path(sys.argv[1]))
    except Exception as e:
        print(str(e) if isinstance(e,ValueError) else '音频特征处理失败：'+type(e).__name__,flush=True)
        raise SystemExit(1)
