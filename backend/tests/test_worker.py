import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from worker import separate


class WorkerTests(unittest.TestCase):
    def test_no_cuda_fails_before_downloading_models(self):
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with tempfile.TemporaryDirectory() as folder, patch.dict('sys.modules', {'torch': torch}):
            root = Path(folder)
            with self.assertRaisesRegex(RuntimeError, 'CUDA'):
                separate(root / 'input.wav', root / 'out', 'four', root / 'models')
            self.assertFalse((root / 'out').exists())

    def test_partial_stems_do_not_mark_four_track_job_successful(self):
        cuda = SimpleNamespace(is_available=lambda: True, set_device=lambda n: None,
                               reset_peak_memory_stats=lambda n: None, synchronize=lambda: None,
                               get_device_name=lambda n: 'Test GPU',
                               max_memory_allocated=lambda n: 0, max_memory_reserved=lambda n: 0)
        torch = SimpleNamespace(cuda=cuda, set_num_threads=lambda n: None)
        class Separator:
            @classmethod
            def from_model_name(cls, *args, **kwargs):
                instance = cls()
                instance.stems = Path(kwargs['store_dirs'])
                return instance
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def process_folder(self, path):
                for name in ['vocals', 'other']:
                    (self.stems / f'input_{name}.wav').write_bytes(b'test')
                return ['input.wav']
        with tempfile.TemporaryDirectory() as folder, patch.dict('sys.modules', {
            'torch': torch, 'pymss': SimpleNamespace(MSSeparator=Separator)
        }):
            root = Path(folder)
            with self.assertRaisesRegex(RuntimeError, '音轨'):
                separate(root / 'input.wav', root / 'out', 'four', root / 'models')
            self.assertFalse((root / 'out' / 'result.json').exists())


if __name__ == '__main__':
    unittest.main()
