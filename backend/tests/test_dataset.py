import tempfile
import unittest
from pathlib import Path
from dataset import scan_dataset, split_dataset, export_dataset

class DatasetTests(unittest.TestCase):
    def corpus(self, root, n=10):
        for i in range(n):
            p=root/f'work-{i}'
            (p/'audio').mkdir(parents=True);(p/'scores').mkdir()
            (p/'audio'/'a.mp3').write_bytes(f'audio{i}'.encode())
            (p/'audio'/'b.mp3').write_bytes(f'version{i}'.encode())
            (p/'scores'/'score.pdf').write_bytes(f'pdf{i}'.encode())

    def test_grouping_is_reproducible_and_all_versions_stay_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.corpus(root)
            scan=scan_dataset(root)
            first=split_dataset(scan,[80,10,10],42)
            self.assertEqual(first,split_dataset(scan,[80,10,10],42))
            self.assertEqual([len(first[k]) for k in ['train','validation','test']],[8,1,1])
            ids=[w['id'] for values in first.values() for w in values]
            self.assertEqual(len(ids),len(set(ids)))
            self.assertTrue(all(len(w['audio'])==2 for values in first.values() for w in values))
            self.assertTrue(all(not w['training_ready'] for w in scan['works']))

    def test_duplicate_content_across_works_is_grouped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.corpus(root,4)
            (root/'work-1/audio/a.mp3').write_bytes(b'audio0')
            scan=scan_dataset(root)
            parts=split_dataset(scan,[80,10,10],42)
            membership={w['id']:s for s,works in parts.items() for w in works}
            self.assertEqual(membership['work-0'],membership['work-1'])
            self.assertEqual(scan['group_count'],3)

    def test_missing_pair_excluded_and_small_dataset_not_misleading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.corpus(root,2)
            (root/'work-1/scores/score.pdf').unlink()
            scan=scan_dataset(root)
            self.assertEqual(scan['eligible_count'],1)
            with self.assertRaises(ValueError):split_dataset(scan,[80,10,10],42)

    def test_export_preserves_inputs_and_rejects_stale_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.corpus(root,3)
            scan=scan_dataset(root)
            report=export_dataset(root,[80,10,10],42,scan['fingerprint'])
            self.assertTrue((Path(report['directory'])/'train.jsonl').is_file())
            self.assertEqual((root/'work-0/audio/a.mp3').read_bytes(),b'audio0')
            (root/'work-0/audio/a.mp3').write_bytes(b'changed')
            with self.assertRaises(ValueError):export_dataset(root,[80,10,10],42,scan['fingerprint'])

    def test_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'linked').symlink_to(root,target_is_directory=True)
            self.assertEqual(scan_dataset(root)['works'],[])

if __name__=='__main__':unittest.main()
