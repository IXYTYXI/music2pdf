"""Fixed-event characterization; fewer voices does not imply higher accuracy."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import partitura
from voice_candidates import estimate_candidates, review_candidates


def baseline(notes):
    result = deepcopy(notes)
    for staff in (1, 2):
        chords = []
        for n in sorted(result, key=lambda n: (n['start'], n['pitch'])):
            if (1 if n['pitch'] >= 60 else 2) != staff:
                continue
            chord = next((c for c in chords if c[0]['start'] == n['start']
                          and c[0]['duration'] == n['duration']
                          and all(m['pitch'] != n['pitch'] for m in c)), None)
            if chord is None:
                chord = []
                chords.append(chord)
            chord.append(n)
        ends = []
        for chord in chords:
            n = chord[0]
            lane = next((i for i, end in enumerate(ends) if end <= n['start']), len(ends))
            if lane == len(ends):
                ends.append(0)
            ends[lane] = n['start'] + n['duration']
            for m in chord:
                m['voice_candidate'] = f'{staff}:{lane}'
    return result


def summarize(notes):
    conflicts = []
    mixed_staff = []
    for i, a in enumerate(notes):
        for b in notes[i+1:]:
            if a['voice_candidate'] != b['voice_candidate']:
                continue
            overlap = min(a['start']+a['duration'], b['start']+b['duration']) > max(a['start'], b['start'])
            equal_span = a['start'] == b['start'] and a['duration'] == b['duration']
            if overlap and (not equal_span or a['pitch'] == b['pitch']):
                conflicts.append([a['id'], b['id']])
            if overlap and (a['pitch'] >= 60) != (b['pitch'] >= 60):
                mixed_staff.append([a['id'], b['id']])
    return dict(events=len(notes), voices=dict(Counter(n['voice_candidate'] for n in notes)),
                non_chord_overlap_pairs=conflicts, cross_staff_overlap_pairs=mixed_staff)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='.work/madmom-quantization/cases.json')
    parser.add_argument('--output', default='.work/partitura')
    args = parser.parse_args()
    path = Path(args.input)
    notes = json.loads(path.read_text())['dynamic16']
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    variants = {'existing_lane_heuristic': baseline(notes),
                'partitura_global': estimate_candidates(notes, per_staff=False),
                'partitura_per_staff': estimate_candidates(notes)}
    reviewed, issues = review_candidates(variants['partitura_per_staff'])
    assert [{k:v for k,v in n.items() if k != 'voice_candidate'} for n in reviewed] == notes
    (out / 'reviewed-candidates.json').write_text(json.dumps(reviewed, indent=2))
    (out / 'rejected-candidates.json').write_text(json.dumps(issues, indent=2))
    for name, labeled in variants.items():
        assert [{k:v for k,v in n.items() if k != 'voice_candidate'} for n in labeled] == notes
        (out / f'{name}.json').write_text(json.dumps(labeled, indent=2))
    report = dict(partitura_version=partitura.__version__, input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  case='dynamic16', events_unchanged=True,
                  limitations=['Existing quantized notes, not a new audio transcription.',
                               'No reference score used for inference; voice correctness not established.',
                               'Per-staff mode retains the existing central-C split.',
                               'Labels do not authorize gap filling or overlap truncation.'],
                  results={name:summarize(ns) for name, ns in variants.items()})
    (out / 'comparison.json').write_text(json.dumps(report, indent=2))
    for name, row in report['results'].items():
        print(name, 'events', row['events'], 'voices', len(row['voices']),
              'conflicts', len(row['non_chord_overlap_pairs']), 'mixed-staff', len(row['cross_staff_overlap_pairs']))
