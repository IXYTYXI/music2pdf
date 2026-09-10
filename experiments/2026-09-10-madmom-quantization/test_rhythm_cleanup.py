import unittest
from copy import deepcopy
from rhythm_cleanup import clean_score_stream, merge_fragments


def note(pitch, start, duration, ident, **extra):
    return dict(id=ident, pitch=pitch, start=start, duration=duration, **extra)


class RhythmCleanupTests(unittest.TestCase):
    def test_unknown_voice_keeps_real_rest_and_input_unchanged(self):
        ns = [note(64, 0, .25, 'a'), note(65, .5, .5, 'b')]
        original = deepcopy(ns)
        out, changes = clean_score_stream(ns)
        self.assertEqual(out, original)
        self.assertEqual(ns, original)
        self.assertEqual(changes, [])

    def test_same_voice_alone_does_not_authorize_filling_a_rest(self):
        ns = [note(64, 0, .25, 'a', voice_id='v'), note(65, .5, .5, 'b', voice_id='v')]
        self.assertEqual(clean_score_stream(ns)[0], ns)

    def test_confirmed_connection_repairs_rounding_gap_using_raw_times(self):
        ns = [note(64, 0, .25, 'a', voice_id='v', continuous_to='b', raw_end=.36),
              note(65, .5, .5, 'b', voice_id='v', raw_start=.48)]
        out, changes = clean_score_stream(ns)
        self.assertEqual(out[0]['duration'], .5)
        self.assertEqual(len(changes), 1)

    def test_confirmed_small_overlap_is_cut_without_merging_repeated_notes(self):
        ns = [note(64, 0, .75, 'a', voice_id='v', continuous_to='b', raw_end=.66),
              note(64, .5, .5, 'b', voice_id='v', raw_start=.62)]
        out, _ = clean_score_stream(ns)
        self.assertEqual([n['duration'] for n in out], [.5, .5])
        self.assertEqual(len(out), 2)

    def test_independent_held_voice_survives(self):
        ns = [note(60, 0, 2, 'held', voice_id='bass'), note(76, .5, .5, 'melody', voice_id='melody')]
        self.assertEqual(clean_score_stream(ns)[0], ns)

    def test_long_overlap_is_not_cut_even_if_connection_is_claimed(self):
        ns = [note(60, 0, 2, 'a', voice_id='v', continuous_to='b', raw_end=2),
              note(76, .5, .5, 'b', voice_id='v', raw_start=.5)]
        self.assertEqual(clean_score_stream(ns)[0], ns)

    def test_chord_members_change_together_only_with_matching_connections(self):
        ns = [note(p, 0, .25, str(p), voice_id='v', continuous_to='next', raw_end=.36) for p in [60,64,67]]
        ns += [note(69, .5, .5, 'next', voice_id='v', raw_start=.48)]
        out, changes = clean_score_stream(ns)
        self.assertEqual([n['duration'] for n in out[:3]], [.5]*3)
        self.assertEqual(len(changes), 3)
        ns[0].pop('continuous_to')
        self.assertEqual(clean_score_stream(ns)[0], ns)

    def test_unequal_length_chord_is_not_regularized(self):
        ns = [note(60,0,2,'a',voice_id='v',continuous_to='c',raw_end=.36),
              note(64,0,.25,'b',voice_id='v',continuous_to='c',raw_end=.36),
              note(67,.5,.5,'c',voice_id='v',raw_start=.48)]
        self.assertEqual(clean_score_stream(ns)[0], ns)

    def test_staccato_or_explicit_rest_is_preserved(self):
        for flag in ['staccato','rest_after','protect_duration']:
            ns = [note(64,0,.25,'a',voice_id='v',continuous_to='b',raw_end=.36,**{flag:True}),
                  note(65,.5,.5,'b',voice_id='v',raw_start=.48)]
            self.assertEqual(clean_score_stream(ns)[0], ns)

    def test_fragment_merge_needs_explicit_evidence_and_preserves_ids(self):
        ns = [note(72,1,.3,'a'),note(72,1.3,.3,'b'),note(72,2,.2,'repeat')]
        evidence = [dict(first='a',second='b',no_new_attack=True,independent_sustain=True)]
        out, changes = merge_fragments(ns, evidence)
        self.assertEqual(len(out),2)
        self.assertAlmostEqual(out[0]['duration'],.6)
        self.assertEqual(out[0]['source_ids'],['a','b'])
        self.assertEqual(out[1]['id'],'repeat')
        self.assertEqual(len(changes),1)
        self.assertEqual(len(merge_fragments(ns,[])[0]),3)

    def test_fragment_merge_rejects_gap_or_different_pitch_or_protected_note(self):
        for second in [note(72,1.5,.3,'b'),note(74,1.3,.3,'b'),note(72,1.3,.3,'b',protect_duration=True)]:
            ns=[note(72,1,.3,'a'),second]
            ev=[dict(first='a',second='b',no_new_attack=True,independent_sustain=True)]
            self.assertEqual(merge_fragments(ns,ev)[0],ns)

    def test_invalid_note_values_and_duplicate_ids_are_rejected(self):
        for ns in [[note(60,0,-1,'a')],[note(60,float('nan'),1,'a')],[note(60,0,1,'a'),note(62,1,1,'a')]]:
            with self.assertRaises(ValueError):clean_score_stream(ns)


if __name__ == '__main__':
    unittest.main()
