"""Local HTTP API. Run one uvicorn process, bound to loopback."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from service import DATA, PRESETS, JobQueue, run_job

MAX_BYTES = 200 * 1024 * 1024
EXTENSIONS = {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.aac'}


def create_app(root=None, runner=run_job, max_bytes=MAX_BYTES):
    @asynccontextmanager
    async def lifespan(app):
        app.state.queue = JobQueue(root or DATA / 'jobs', runner=runner)
        yield
        await asyncio.to_thread(app.state.queue.close)

    app = FastAPI(title='Music2PDF RTX 4060 分轨服务', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])

    def get_job(job_id):
        try:
            return app.state.queue.get(job_id)
        except KeyError:
            raise HTTPException(404, '任务不存在，或服务已重启。')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'device': 'cuda', 'gpu_verified': False,
                'note': 'API 存活不代表 GPU 可用；运行 python cli.py doctor 检查。'}

    @app.get('/presets')
    def presets():
        return PRESETS

    @app.post('/jobs', status_code=202, openapi_extra={'requestBody': {
        'required': True, 'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}}
    }})
    async def upload(request: Request, filename: str, preset: str = 'four'):
        # Block browser-originated cross-site writes. Same-origin /docs remains usable.
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, '此本地接口只接受同源请求。')
        suffix = Path(filename).suffix.lower()
        if suffix not in EXTENSIONS or preset not in PRESETS:
            raise HTTPException(400, '不支持的音频扩展名或分轨预设。')
        queue = app.state.queue
        try:
            job_id = queue.reserve(preset)
        except OverflowError as exc:
            raise HTTPException(429, str(exc))
        try:
            size = 0
            with (queue.root / job_id / ('input' + suffix)).open('wb') as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, '音频超过上传大小限制（默认 200 MiB）。')
                    stream.write(chunk)
            if size == 0:
                raise HTTPException(400, '音频文件为空。')
            queue.start(job_id)
        except BaseException:
            queue.discard(job_id)
            raise
        return queue.get(job_id)

    @app.get('/jobs/{job_id}')
    def status(job_id: str):
        return get_job(job_id)

    @app.get('/jobs/{job_id}/log', response_class=PlainTextResponse)
    def log(job_id: str):
        get_job(job_id)
        path = app.state.queue.root / job_id / 'worker.log'
        if not path.exists():
            return '任务尚未开始。'
        with path.open('rb') as stream:
            stream.seek(max(0, os.fstat(stream.fileno()).st_size - 65536))
            return stream.read().decode('utf-8', errors='replace')

    @app.get('/jobs/{job_id}/files/{filename}')
    def download(job_id: str, filename: str):
        job = get_job(job_id)
        if job['status'] != 'completed' or filename not in job['result']['files'] or Path(filename).name != filename:
            raise HTTPException(404, '分轨文件不存在。')
        path = app.state.queue.root / job_id / 'stems' / filename
        if not path.is_file():
            raise HTTPException(404, '分轨文件已被移除。')
        return FileResponse(path, media_type='audio/wav', filename=filename)

    @app.delete('/jobs/{job_id}', status_code=204)
    def delete(job_id: str, request: Request):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, '此本地接口只接受同源请求。')
        get_job(job_id)
        try:
            app.state.queue.discard(job_id)
        except KeyError:
            raise HTTPException(404, '任务已被删除。')
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return Response(status_code=204)

    return app


app = create_app()
