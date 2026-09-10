"""Experimental labels only: never authorize duration repair from these labels."""
from copy import deepcopy
import math
import numpy as np
from partitura.musicanalysis import estimate_voices


def review_candidates(notes):
    """Reject conflicting candidate groups; never repair note timing to fit labels."""
    result = deepcopy(notes)
    issues = []
    rejected = set()
    for i, a in enumerate(result):
        group = (a.get('track', 'piano'), a.get('voice_candidate'))
        if group[1] is None:
            continue
        for b in result[i+1:]:
            if group != (b.get('track', 'piano'), b.get('voice_candidate')):
                continue
            overlap = min(a['start']+a['duration'], b['start']+b['duration']) - max(a['start'], b['start'])
            chord = (a['start'] == b['start'] and a['duration'] == b['duration']
                     and a['pitch'] != b['pitch'])
            if overlap > 0 and not chord:
                rejected.add(group)
                issues.append(dict(reason='non_chord_overlap', ids=[a['id'], b['id']],
                                   overlap_beats=overlap, candidate=group[1]))
    for n in result:
        if (n.get('track', 'piano'), n.get('voice_candidate')) in rejected:
            n.pop('voice_candidate')
    return result, issues


def estimate_candidates(notes, per_staff=True):
    result = deepcopy(notes)
    ids = set()
    for n in result:
        if n['id'] in ids:
            raise ValueError('Duplicate note id')
        ids.add(n['id'])
        if (not all(math.isfinite(n[k]) for k in ('pitch', 'start', 'duration'))
                or n['duration'] <= 0 or n['start'] < 0
                or int(n['pitch']) != n['pitch'] or not 0 <= n['pitch'] <= 127):
            raise ValueError('Invalid note pitch or timing')
    groups = {}
    for i, n in enumerate(result):
        # This reproduces the existing staff split, NOT inferred hands.
        staff = ('rh' if n['pitch'] >= 60 else 'lh') if per_staff else 'all'
        groups.setdefault((n.get('track', 'piano'), staff), []).append(i)
    for group_index, indices in enumerate(groups.values()):
        array = np.array([(result[i]['pitch'], result[i]['start'], result[i]['duration'])
                          for i in indices],
                         dtype=[('pitch', 'i4'), ('onset_beat', 'f8'), ('duration_beat', 'f8')])
        labels = estimate_voices(array, monophonic_voices=False)
        for i, label in zip(indices, labels):
            result[i]['voice_candidate'] = f'{group_index}:{int(label)}'
    return result
