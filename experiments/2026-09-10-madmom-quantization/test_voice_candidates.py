import copy
import unittest
from voice_candidates import estimate_candidates, review_candidates


class VoiceCandidatesTest(unittest.TestCase):
    def test_rejects_overlapping_voice_without_truncating_held_note(self):
        notes = [dict(id='a', pitch=69, start=36., duration=1., voice_candidate='0:2'),
                 dict(id='b', pitch=64, start=36.5, duration=.5, voice_candidate='0:2')]
        original = copy.deepcopy(notes)
        safe, issues = review_candidates(notes)
        self.assertEqual(len(issues), 1)
        self.assertTrue(all('voice_candidate' not in n for n in safe))
        self.assertEqual(safe[0]['duration'], 1.)
        self.assertEqual(notes, original)

    def test_accepts_equal_span_chord_and_preserves_rest(self):
        notes = [dict(id='a', pitch=72, start=0., duration=.5, voice_candidate='0:1'),
                 dict(id='b', pitch=76, start=0., duration=.5, voice_candidate='0:1'),
                 dict(id='c', pitch=74, start=1., duration=.5, voice_candidate='0:1')]
        safe, issues = review_candidates(notes)
        self.assertEqual(safe, notes)
        self.assertEqual(issues, [])

    def test_preserves_held_notes_chords_and_true_gaps(self):
        notes = [
            dict(id='bass', pitch=48, start=0., duration=4.),
            dict(id='a', pitch=72, start=0., duration=.5),
            dict(id='b', pitch=76, start=0., duration=.5),
            dict(id='c', pitch=74, start=1., duration=.5),
            dict(id='d', pitch=76, start=2., duration=.5),
        ]
        original = copy.deepcopy(notes)
        result = estimate_candidates(notes)
        self.assertTrue(all('voice_candidate' in n for n in result))
        self.assertEqual(notes, original)
        for before, after in zip(notes, result):
            self.assertEqual(before, {k:v for k,v in after.items() if k != 'voice_candidate'})
        self.assertNotEqual(result[0]['voice_candidate'], result[1]['voice_candidate'])

    def test_does_not_merge_hands_into_one_chord(self):
        notes = [dict(id='l', pitch=48, start=0., duration=1.),
                 dict(id='r', pitch=72, start=0., duration=1.)]
        result = estimate_candidates(notes, per_staff=True)
        self.assertNotEqual(result[0]['voice_candidate'], result[1]['voice_candidate'])

    def test_empty(self):
        self.assertEqual(estimate_candidates([]), [])

    def test_rejects_invalid_timing_and_duplicate_ids(self):
        n = dict(id='a', pitch=60, start=0., duration=1.)
        for notes in [[n, n], [{**n, 'duration':0}], [{**n, 'start':float('nan')}]]:
            with self.assertRaises(ValueError):
                estimate_candidates(notes)

if __name__ == '__main__':
    unittest.main()
