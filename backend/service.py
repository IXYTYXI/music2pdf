"""One GPU process at a time; the API process never imports torch."""
import copy
import json
import shutil
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PRESETS = {
    'four': {'model': 'HTDemucs4', 'description': '人声、鼓、贝斯、其他'},
    'six': {'model': 'HTDemucs4_6stems', 'description': '人声、鼓、贝斯、其他、吉他、钢琴（实验）'},
    'vocals': {'model': 'mel_band_roformer_vocals_becruily', 'description': '人声与伴奏'},
}
BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'


def run_process(command, folder, timeout=1800):
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'result.json'
    manifest.unlink(missing_ok=True)
    with (folder / 'worker.log').open('wb') as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError('任务超过 30 分钟或指定超时，进程已停止；详见 worker.log。') from exc
    if result.returncode:
        raise RuntimeError('模型进程失败；请查看 worker.log。显存不足时关闭占用 GPU 的应用，或先选择 four。')
    if not manifest.is_file():
        raise RuntimeError('模型没有生成结果清单，不能视为分离成功。')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    files = data.get('files', [])
    if not files or any(Path(f).name != f or not (folder / 'stems' / f).is_file() for f in files):
        raise RuntimeError('分轨文件缺失或清单无效。')
    return data


def run_job(folder, preset):
    inputs = list(folder.glob('input.*'))
    if len(inputs) != 1:
        raise ValueError('需要一个输入音频文件。')
    return run_process([
        sys.executable, str(BASE / 'worker.py'), '--input', str(inputs[0]),
        '--output', str(folder), '--preset', preset,
        '--models', str(DATA / 'models'),
    ], folder)


class JobQueue:
    def __init__(self, root, runner=run_job, capacity=4):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.runner = runner
        self.jobs = {}
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(capacity)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.futures = []

    def reserve(self, preset):
        if not self.slots.acquire(blocking=False):
            raise OverflowError('队列已满，请等待已有任务完成。')
        job_id = uuid.uuid4().hex
        try:
            (self.root / job_id).mkdir()
            with self.lock:
                self.jobs[job_id] = {'id': job_id, 'preset': preset, 'status': 'uploading'}
            return job_id
        except BaseException:
            self.slots.release()
            raise

    def get(self, job_id):
        with self.lock:
            return copy.deepcopy(self.jobs[job_id])

    def start(self, job_id):
        with self.lock:
            if self.jobs[job_id]['status'] != 'uploading':
                raise ValueError('任务已提交。')
            self.jobs[job_id]['status'] = 'queued'
        future = self.executor.submit(self._run, job_id)
        self.futures.append(future)
        self.futures = [f for f in self.futures if not f.done()]

    def _run(self, job_id):
        try:
            with self.lock:
                self.jobs[job_id]['status'] = 'running'
                preset = self.jobs[job_id]['preset']
            result = self.runner(self.root / job_id, preset)
            with self.lock:
                self.jobs[job_id].update(status='completed', result=result)
        except Exception as exc:
            with self.lock:
                self.jobs[job_id].update(status='failed', error=str(exc))
        finally:
            self.slots.release()

    def discard(self, job_id):
        with self.lock:
            status = self.jobs[job_id]['status']
            if status in ('queued', 'running'):
                raise ValueError('任务正在排队或运行，请完成后删除。')
            del self.jobs[job_id]
        shutil.rmtree(self.root / job_id, ignore_errors=True)
        if status == 'uploading':
            self.slots.release()

    def wait(self):
        for future in self.futures:
            future.result()

    def close(self):
        self.executor.shutdown(wait=True)
