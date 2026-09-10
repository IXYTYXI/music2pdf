import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from r2_import import R2Dataset
from dataset import scan_dataset

class Remote:
    def __init__(self):
        self.objects = {'imslp/w1/audio/a.mp3': b'ID3audio', 'imslp/w1/scores/a.pdf': b'%PDF-1.7 score',
                        'imslp/w1/metadata.json': b'{"title":"Work one"}',
                        'imslp/w2/scores/a.pdf': b'%PDF-1.7 other', 'imslp/_state/queue.sqlite3': b'private-state'}
        self.gets = []
    def list_objects_v2(self, **kwargs):
        keys=sorted(k for k in self.objects if k.startswith(kwargs['Prefix']))
        start=int(kwargs.get('ContinuationToken','0')); keys=keys[start:start+2]
        more=start+len(keys)<len(self.objects)
        return {'Contents':[{'Key':k,'Size':len(self.objects[k]),'ETag':'"'+hashlib.md5(self.objects[k]).hexdigest()+'"'} for k in keys], 'IsTruncated':more, 'NextContinuationToken':str(start+len(keys))}
    def get_object(self, Bucket, Key, IfMatch):
        self.gets.append(Key); data=self.objects[Key]
        if IfMatch != '"'+hashlib.md5(data).hexdigest()+'"': raise ValueError('Remote changed')
        return {'Body':io.BytesIO(data),'ContentLength':len(data),'Metadata':{'sha256':hashlib.sha256(data).hexdigest()}}

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.remote=Remote();self.store=R2Dataset(self.remote,'bucket','imslp')
    def test_paginated_inventory_and_work_matching(self):
        catalog=self.store.inventory()
        self.assertEqual([w['id'] for w in catalog['works']],['w1','w2'])
        self.assertTrue(catalog['works'][0]['eligible']);self.assertFalse(catalog['works'][1]['eligible'])
        self.assertEqual(self.remote.gets,[])
    def test_selected_work_import_and_resume(self):
        catalog=self.store.inventory();self.store.pull(self.root,catalog,['w1'])
        self.assertEqual(scan_dataset(self.root)['eligible_count'],1)
        self.assertTrue((self.root/'w1/metadata.json').exists())
        self.assertFalse((self.root/'w2').exists())
        self.store.pull(self.root,catalog,['w1']);self.assertEqual(len(self.remote.gets),3)
    def test_changed_remote_file_is_refreshed(self):
        self.store.pull(self.root,self.store.inventory(),['w1'])
        self.remote.objects['imslp/w1/audio/a.mp3']=b'ID3new audio'
        self.store.pull(self.root,self.store.inventory(),['w1'])
        self.assertEqual((self.root/'w1/audio/a.mp3').read_bytes(),b'ID3new audio')
        self.assertEqual(len(self.remote.gets),4)
    def test_corrupt_local_cache_redownloaded(self):
        self.store.pull(self.root,self.store.inventory(),['w1'])
        (self.root/'w1/audio/a.mp3').write_bytes(b'bad')
        self.store.pull(self.root,self.store.inventory(),['w1'])
        self.assertEqual(len(self.remote.gets),4)
    def test_unmanaged_local_file_not_overwritten(self):
        p=self.root/'w1/audio/a.mp3';p.parent.mkdir(parents=True);p.write_bytes(b'user original')
        result=self.store.pull(self.root,self.store.inventory(),['w1'])
        self.assertEqual(p.read_bytes(),b'user original');self.assertEqual(len(result['failed']),1)
    def test_path_traversal_and_symlinks_rejected(self):
        self.remote.objects['imslp/../scores/x.pdf']=b'x'
        catalog=self.store.inventory();self.assertTrue(catalog['skipped'])
        with tempfile.TemporaryDirectory() as outside:
            (self.root/'w1').symlink_to(outside,target_is_directory=True)
            result=self.store.pull(self.root,catalog,['w1'])
            self.assertTrue(result['failed']);self.assertEqual(list(Path(outside).iterdir()),[])
    def test_changed_after_listing_leaves_no_partial(self):
        catalog=self.store.inventory();self.remote.objects['imslp/w1/audio/a.mp3']=b'changed since list'
        result=self.store.pull(self.root,catalog,['w1'])
        self.assertEqual(len(result['failed']),1)
        self.assertFalse((self.root/'w1/audio/a.mp3').exists())
        self.assertEqual(list(self.root.rglob('*.part')),[])

if __name__=='__main__':unittest.main()
