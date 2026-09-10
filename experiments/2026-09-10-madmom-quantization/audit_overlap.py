"""Trace the observed voice conflict back to independent model events."""
from pathlib import Path
import json
import html

SOURCES = {
    '当前 Basic Pitch': 'outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json',
    '钢琴专用模型': '.work/phrase-model-comparison/notes.json',
    'Omnizart Piano': '.work/omnizart/notes.json',
    'Omnizart PianoV2': '.work/omnizart/v2/notes.json',
}


if __name__ == '__main__':
    records = []
    for model, source in SOURCES.items():
        selected = []
        for n in json.loads(Path(source).read_text()):
            start = n.get('start', n.get('onset_time'))
            pitch = n.get('pitch', n.get('midi_note'))
            end = n['offset_time'] if 'offset_time' in n else start+n['duration']
            if 27.2 <= start <= 27.85 and pitch in (52, 64, 69):
                selected.append(dict(pitch=pitch, start=start, end=end))
        records.append(dict(model=model, source=source, notes=selected))
    out = Path('outputs/查看识谱结果/17-重叠音符定位')
    out.mkdir(parents=True, exist_ok=True)
    (out/'诊断数据.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
    names = {52:'E3（低音 mi）', 64:'E4（高一个八度的 mi）', 69:'A4（la）'}
    rows = ''
    for r in records:
        cells = []
        for pitch in (69, 64, 52):
            events = [n for n in r['notes'] if n['pitch'] == pitch]
            cells.append('<td>'+('<br>'.join(f"{n['start']:.3f}–{n['end']:.3f} 秒" for n in events) or '该窗口无新起音')+'</td>')
        rows += '<tr><th>'+html.escape(r['model'])+'</th>'+''.join(cells)+'</tr>'
    (out/'先看这里.html').write_text('''<!doctype html><html lang="zh"><meta charset="utf-8">
<title>这次重叠到底错在哪</title><style>body{font:18px/1.7 system-ui;margin:40px auto;max-width:1050px;padding:0 24px;color:#172536}h1{font-size:30px}table{border-collapse:collapse;width:100%;font-size:16px}td,th{border:1px solid #ccd4df;padding:12px;text-align:left}.note{background:#fff3cf;padding:18px;border-radius:10px}audio{width:100%}</style>
<h1>先查音高，不能直接截短音符</h1>
<p>约 27.59 秒，当前模型标出 E4；其他三份结果在附近标出 E3。相差一个八度，可能是把低音的泛音认成了另一个音。</p>
<p class="note">这是需要复核的线索，不是已确认的错音。模型也会漏音；E3 与 E4 可以同时存在。没有据此删除或替换音符。</p>
<h2>听原音频的这两秒</h2><p>截取范围：原录音 26.8–28.8 秒。问题起点约在播放器的 0.79 秒。</p>
<audio controls src="原音频-26.8至28.8秒.wav"></audio>
<h2>各模型检测到什么</h2><p>表内是原录音绝对时间；不是乐谱拍数。只列 27.2–27.85 秒内开始的 A4、E4、E3。</p>
<table><tr><th>模型</th><th>A4（la）</th><th>E4（高 mi）</th><th>E3（低 mi）</th></tr>'''+rows+'''</table>
<h2>这次实际修了什么</h2><p>实验流程原来保留了有冲突的候选声部标签；现在会撤回存在非和弦重叠的候选组。音高与时值保持不变，不再为适应这个标签去猜测截短或拉长。</p>
<p>233 个原音符逐字段不变；18 项保护测试通过。此保护仍在实验代码中，正式排谱没有接入 Partitura。</p>
<h2>还没有解决什么</h2><p>尚未确认 E4 是否真是多余泛音，也未证明 A4 应该缩短。因此没有生成“已修好”的乐谱。下一步应针对这个八度分歧核查音高证据；不能用谱面更整齐来代替验证。</p>
</html>''')
    print(json.dumps(records, ensure_ascii=False, indent=2))
