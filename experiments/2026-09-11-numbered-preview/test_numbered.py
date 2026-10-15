import unittest
from numbered import symbol, group_onsets

class NumberedTest(unittest.TestCase):
    def test_octaves_and_accidentals(self):
        self.assertEqual(symbol(60), ('1', 0))
        self.assertEqual(symbol(52), ('3', -1))
        self.assertEqual(symbol(64), ('3', 0))
        self.assertEqual(symbol(72), ('1', 1))
        self.assertEqual(symbol(66), ('♯4', 0))
        self.assertEqual(symbol(59), ('7', -1))

    def test_group_does_not_chain_or_change_timing(self):
        ns=[dict(start=t,pitch=60,duration=.3) for t in [1.,1.05,1.10]]
        groups=group_onsets(ns)
        self.assertEqual([len(g) for g in groups],[2,1])
        self.assertEqual([n['start'] for g in groups for n in g],[1.,1.05,1.10])

    def test_empty(self): self.assertEqual(group_onsets([]),[])

if __name__=='__main__': unittest.main()
