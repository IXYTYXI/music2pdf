import unittest
from recording_match import work_identity, build_queries, rank_candidate


def work(title='Symphony No. 5, Op. 67', **info):
    return work_identity({'catalog': {'id': '1', 'composer': 'Beethoven, Ludwig van', 'title': title},
                          'information': {'Instrumentation': 'orchestra', **info}})


class MatchTests(unittest.TestCase):
    def test_identity_preserves_alias_and_ignores_imslp_internal_number(self):
        value = work('Symphony No. 5', **{'Alt ernative . Title': 'Schicksalssinfonie', 'Internal Reference Number': 'ILB 250'})
        self.assertIn('Schicksalssinfonie', value['titles'])
        self.assertEqual(value['catalog_numbers'], [])
        self.assertIn('Beethoven', build_queries(value)[0])

    def test_accents_and_composer_order(self):
        identity = work_identity({'catalog': {'composer': 'Fauré, Gabriel', 'title': 'Après un rêve, Op. 7'}})
        rank = rank_candidate(identity, {'title': 'Gabriel Faure - Apres un reve Op.7', 'description': ''})
        self.assertGreaterEqual(rank['score'], 70)
        self.assertTrue(rank['requires_review'])
        self.assertFalse(rank['training_ready'])

    def test_different_opus_cannot_be_high_confidence(self):
        rank = rank_candidate(work(), {'title': 'Beethoven Symphony No. 5 Op. 68 orchestra'})
        self.assertEqual(rank['tier'], 'conflict')
        self.assertTrue(any(x['field'] == 'catalog' for x in rank['conflicts']))

    def test_album_title_does_not_identify_every_track(self):
        rank = rank_candidate(work(), {'title': 'Track 08', 'context_title': 'Beethoven Symphony No. 5 Op. 67'})
        self.assertNotEqual(rank['tier'], 'strong_candidate')
        self.assertIn('track_title', rank['missing'])

    def test_explicit_movement_conflict(self):
        identity = work('Symphony No. 5 Op. 67', **{'Movement': 'II'})
        rank = rank_candidate(identity, {'title': 'Beethoven Symphony No. 5 Op. 67', 'movement': 'IV'})
        self.assertTrue(any(x['field'] == 'movement' for x in rank['conflicts']))

    def test_four_hands_and_solo_require_version_review(self):
        identity = work('Amicizia', **{'Instrumentation': 'piano 4-hands'})
        rank = rank_candidate(identity, {'title': 'Beethoven Amicizia', 'instrumentation': 'piano solo'})
        self.assertTrue(any(x['field'] == 'instrumentation' for x in rank['conflicts']))

    def test_missing_metadata_is_not_guessed(self):
        rank = rank_candidate(work(), {'title': 'Allegro'})
        self.assertEqual(rank['tier'], 'review')
        self.assertIn('composer', rank['missing'])
        self.assertIn('catalog', rank['missing'])

    def test_synthetic_recordings_are_marked(self):
        rank = rank_candidate(work(), {'title': 'Beethoven Symphony No.5 Op.67', 'description': 'MIDI synthesized performance'})
        self.assertTrue(rank['synthetic_hint'])
        self.assertIn('synthetic_performance', rank['warnings'])

    def test_filename_underscores_do_not_hide_catalog_conflicts(self):
        identity = work('Cello Suite No.1 BWV 1007')
        rank = rank_candidate(identity, {'title': 'Bach_French_Suite_BWV_815.ogg'})
        self.assertEqual(rank['tier'], 'conflict')

    def test_transcription_requires_explicit_version_review(self):
        identity = work('Cello Suite No.1 BWV 1007', **{'Instrumentation': 'cello'})
        rank = rank_candidate(identity, {'title': 'Beethoven Cello Suite No.1 BWV 1007 Siloti transcription'})
        self.assertNotEqual(rank['tier'], 'strong_candidate')
        self.assertIn('arrangement_or_transcription', rank['warnings'])

    def test_catalog_range_in_collection_includes_each_number(self):
        identity = work('6 Cello Suites BWV 1007-1012')
        rank = rank_candidate(identity, {'title': 'Beethoven Cello Suite BWV 1008'})
        self.assertFalse(any(c['field'] == 'catalog' for c in rank['conflicts']))
        self.assertIn('bwv:1008', identity['catalog_numbers'])

    def test_explicit_key_conflict_is_not_hidden_by_matching_catalog(self):
        identity = work('Cello Suite No.1 BWV 1007', **{'Key': 'G major'})
        rank = rank_candidate(identity, {'title': 'Beethoven Cello Suite No.1 in C major BWV 1007'})
        self.assertTrue(any(c['field'] == 'key' for c in rank['conflicts']))

    def test_opus_subnumbers_are_distinct_works(self):
        rank = rank_candidate(work('Piano Sonata No.13 Op.27 No.1'),
                              {'title': 'Beethoven Piano Sonata No.14 Op.27 No.2'})
        self.assertEqual(rank['tier'], 'conflict')

    def test_unspecified_opus_subnumber_is_missing_not_conflicting(self):
        rank = rank_candidate(work('Piano Sonata Op.27 No.1'),
                              {'title': 'Beethoven Piano Sonata Op.27'})
        self.assertNotEqual(rank['tier'], 'strong_candidate')
        self.assertFalse(rank['conflicts'])

    def test_numbered_works_with_shared_opus_need_review(self):
        rank = rank_candidate(work('Piano Sonata No.13 Op.27'),
                              {'title': 'Beethoven Piano Sonata No.14 Op.27'})
        self.assertEqual(rank['tier'], 'conflict')


if __name__ == '__main__': unittest.main()
