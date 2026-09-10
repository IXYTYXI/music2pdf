"""Create an auditable candidate from frozen model outputs; never overwrite input."""
from pathlib import Path
import json
import numpy as np
from rhythm_cleanup import merge_fragments

p = Path('.work/rhythm-repair')
p.mkdir(parents=True, exist_ok=True)
notes = json.loads(Path('outputs/失败/Gae仅听录音转谱-2026-09-10/运行记录/notes.json').read_text())
piano = json.loads(Path('.work/phrase-model-comparison/notes.json').read_text())
onsets = np.load('.work/madmom-quantization/onset-activations.npy')


def attack(t):
    lo, hi = max(0, int(round((t-.05)*100))), min(len(onsets), int(round((t+.05)*100))+1)
    return float(np.max(onsets[lo:hi])) if hi > lo else 1.0


evidence, considered = [], []
groups = {}
for n in notes:
    groups.setdefault((n.get('track'), n['pitch']), []).append(n)
for group in groups.values():
    ordered = sorted(group, key=lambda n: n['start'])
    for a, b in zip(ordered, ordered[1:]):
        if abs(b['start']-(a['start']+a['duration'])) > .03:
            continue
        support = [n for n in piano if n['midi_note'] == a['pitch'] and
                   abs(n['onset_time']-a['start']) <= .08 and
                   n['onset_time'] < b['start']-.05 and n['offset_time'] > b['start']+.05]
        first, second = attack(a['start']), attack(b['start'])
        e = dict(first=a['id'], second=b['id'], pitch=a['pitch'], boundary=b['start'],
                 first_attack=first, second_attack=second,
                 no_new_attack=first >= .5 and second < .05,
                 independent_sustain=bool(support), supporting_model_events=support)
        considered.append(e)
        if e['no_new_attack'] and e['independent_sustain']:
            evidence.append(e)
out, changes = merge_fragments(notes, evidence)
changed_ids = {c[k] for c in changes for k in ('first','second')}
lookup = {n['id']:n for n in out}
assert all(lookup[n['id']] == n for n in notes if n['id'] not in changed_ids)
(p/'notes.json').write_text(json.dumps(out, indent=2))
(p/'audit.json').write_text(json.dumps(dict(before=len(notes), after=len(out),
    considered=considered, changes=changes, untouched_events_verified=True,
    status='Candidate only; onset evidence and second model are not independent performance ground truth.',
    score_input=False), indent=2))
print(json.dumps(dict(before=len(notes),after=len(out),changes=changes),indent=2))
