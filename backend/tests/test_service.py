import sys
import tempfile
import threading
import unittest
from pathlib import Path

from service import JobQueue, run_process


class ServiceTests(unittest.TestCase):
    def test_failed_process_does_not_accept_partial_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(RuntimeError):
                run_process([sys.executable, '-c', 'raise SystemExit(2)'], root)

    def test_process_requires_result_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                run_process([sys.executable, '-c', 'pass'], Path(folder))

    def test_timeout_terminates_process(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(TimeoutError):
                run_process([sys.executable, '-c', 'import time; time.sleep(10)'], Path(folder), timeout=0.1)

    def test_serial_queue_recovers_after_failure_and_limits_capacity(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []
        def runner(folder, preset):
            calls.append(preset)
            if preset == 'bad':
                entered.set()
                release.wait(3)
                raise RuntimeError('out of memory')
            return {'files': ['input_vocals.wav']}
        with tempfile.TemporaryDirectory() as folder:
            queue = JobQueue(Path(folder), runner=runner, capacity=2)
            try:
                first = queue.reserve('bad')
                queue.start(first)
                self.assertTrue(entered.wait(2))
                second = queue.reserve('good')
                queue.start(second)
                with self.assertRaises(OverflowError):
                    queue.reserve('extra')
                self.assertEqual(calls, ['bad'])
                release.set()
                queue.wait()
                self.assertEqual(queue.get(first)['status'], 'failed')
                self.assertEqual(queue.get(second)['status'], 'completed')
                self.assertEqual(calls, ['bad', 'good'])
                third = queue.reserve('good')
                queue.discard(third)
            finally:
                release.set()
                queue.close()


if __name__ == '__main__':
    unittest.main()
