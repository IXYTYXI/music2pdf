import unittest
from consensus import corroborate

class ConsensusTest(unittest.TestCase):
    def test_repeated_attack_needs_separate_support(self):
        bp = [dict(id='a',pitch=60,start=1.,duration=.2),dict(id='b',pitch=60,start=1.08,duration=.2)]
        kept, rejected = corroborate(bp, [[dict(pitch=60,start=1.01,duration=.3)]])
        self.assertEqual([n['id'] for n in kept], ['a'])
        self.assertEqual([n['id'] for n in rejected], ['b'])

    def test_preserves_supported_note_duration_and_input(self):
        n = dict(id='a',pitch=60,start=1.,duration=.37)
        kept, _ = corroborate([n], [[dict(pitch=60,start=1.02,duration=.8)]])
        self.assertEqual(kept, [n])
        kept[0]['duration'] = 9
        self.assertEqual(n['duration'], .37)

    def test_octave_is_not_same_pitch_support(self):
        n = dict(id='a',pitch=64,start=1.,duration=.3)
        kept, rejected = corroborate([n], [[dict(pitch=52,start=1.,duration=.3)]])
        self.assertEqual(kept, [])
        self.assertEqual(rejected, [n])

if __name__ == '__main__': unittest.main()
