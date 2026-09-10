"""Conservative, evidence-gated rhythm cleanup. Never infer voice from middle C."""
from copy import deepcopy
import math


def _copy_validated(notes):
    out = deepcopy(notes)
    ids = set()
    for n in out:
        if n['id'] in ids:
            raise ValueError('Duplicate note id')
        ids.add(n['id'])
        if not all(math.isfinite(n[k]) for k in ('pitch', 'start', 'duration')) or n['duration'] <= 0:
            raise ValueError('Invalid note value')
    return out


def _protected(note):
    return any(note.get(k) for k in ('staccato', 'rest_after', 'protect_duration'))


def clean_score_stream(notes, subdivision=4, max_raw_gap=.125):
    """Beat units. Requires voice_id AND an explicit continuous_to note id.

    raw_end/raw_start must be unquantized beat positions on the same beat map.
    Missing metadata means keep the original timing, not assume legato.
    Thresholds are conservative experimental bounds, not musical standards.
    """
    if subdivision <= 0 or not math.isfinite(subdivision) or max_raw_gap < 0 or not math.isfinite(max_raw_gap):
        raise ValueError('Invalid cleanup settings')
    out = _copy_validated(notes)
    grid = 1.0 / subdivision
    voices = {}
    changes = []
    for n in out:
        if n.get('voice_id') is not None:
            voices.setdefault((n.get('track'), n['voice_id']), {}).setdefault(n['start'], []).append(n)
    for groups in voices.values():
        ordered = sorted(groups.items())
        for (start, current), (next_start, following) in zip(ordered, ordered[1:]):
            if next_start - start > 1 or next_start - start < grid - 1e-9:
                continue
            if any(_protected(n) for n in current):
                continue
            if len({n['duration'] for n in current}) != 1:
                continue  # Different lengths may encode independent held voices.
            targets = {n['id'] for n in following}
            links = {n.get('continuous_to') for n in current}
            if len(links) != 1 or not links.issubset(targets):
                continue
            if any('raw_end' not in n for n in current) or any('raw_start' not in n for n in following):
                continue
            raw_start = min(n['raw_start'] for n in following)
            gaps = [raw_start - n['raw_end'] for n in current]
            if any(not math.isfinite(g) or abs(g) > max_raw_gap + 1e-9 for g in gaps):
                continue
            duration = next_start - start
            if abs(duration - current[0]['duration']) > grid + 1e-9:
                continue
            for n in current:
                if abs(n['duration'] - duration) > 1e-9:
                    changes.append(dict(id=n['id'], before=n['duration'], after=duration,
                                        reason='explicit_same_voice_connection', next_id=n['continuous_to']))
                    n['duration'] = duration
    return out, changes


def merge_fragments(notes, evidence, max_boundary_seconds=.03):
    """Seconds. Opt-in fragment candidates, not blanket merging of equal pitches.

    Evidence must identify a boundary without a new attack and an independent
    model/signal observation that supports one sustained event across it.
    Both tests are fallible; caller must retain the original and audit output.
    """
    if not math.isfinite(max_boundary_seconds) or max_boundary_seconds < 0:
        raise ValueError('Invalid merge settings')
    out = _copy_validated(notes)
    lookup = {n['id']: n for n in out}
    removed = set()
    changes = []
    for e in evidence:
        if e.get('no_new_attack') is not True or e.get('independent_sustain') is not True:
            continue
        a, b = lookup.get(e['first']), lookup.get(e['second'])
        if a is None or b is None or a['id'] == b['id'] or a['id'] in removed or b['id'] in removed:
            continue
        if a['pitch'] != b['pitch'] or a.get('track') != b.get('track') or a.get('voice_id') != b.get('voice_id'):
            continue
        if _protected(a) or _protected(b):
            continue
        if b['start'] <= a['start'] or abs(b['start'] - (a['start'] + a['duration'])) > max_boundary_seconds:
            continue
        if any(n['id'] not in (a['id'], b['id']) and n['pitch'] == a['pitch'] and
               n.get('track') == a.get('track') and a['start'] < n['start'] < b['start'] for n in out):
            continue
        before = dict(a)
        a['duration'] = max(a['start'] + a['duration'], b['start'] + b['duration']) - a['start']
        a['source_ids'] = list(dict.fromkeys(a.get('source_ids', [a['id']]) + b.get('source_ids', [b['id']])))
        removed.add(b['id'])
        changes.append(dict(first=a['id'], second=b['id'], before=before['duration'], after=a['duration'],
                            reason='no_attack_and_independent_sustain_candidate', evidence=deepcopy(e)))
    return [n for n in out if n['id'] not in removed], changes
