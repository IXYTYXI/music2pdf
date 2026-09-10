"""Single-user local dataset workbench; no GPU dependencies."""
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from dataset import scan_dataset, split_dataset, export_dataset, AUDIO

BASE = Path(__file__).resolve().parent
DEFAULT_ROOT = BASE / 'data' / 'datasets' / 'my-corpus'
app = FastAPI(title='Music2PDF 数据工作台')
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])


@app.middleware('http')
async def same_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method != 'GET' and origin and origin != str(request.base_url).rstrip('/'):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': '只允许本地同源操作。'}, status_code=403)
    return await call_next(request)


class Selection(BaseModel):
    root: str = Field(min_length=1)

class Split(Selection):
    ratios: list[int] = Field(default_factory=lambda: [80, 10, 10])
    seed: int = 42
    fingerprint: str = ''

class Create(Selection):
    work: str = Field(min_length=1)


def safe_call(function, *args):
    try:
        return function(*args)
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))


@app.get('/')
def index():
    return FileResponse(BASE / 'dataset_ui' / 'index.html')

@app.get('/api/config')
def config():
    return {'default_root': str(DEFAULT_ROOT), 'exists': DEFAULT_ROOT.is_dir()}

@app.post('/api/create')
def create(value: Create):
    if value.work in ('.', '..') or any(c in value.work for c in '/\\:') or value.work.startswith('.'):
        raise HTTPException(400, '作品名不能包含路径分隔符或以点开头。')
    root = Path(value.root).expanduser().resolve()
    work = root / value.work
    if work.is_symlink() or any((work / k).is_symlink() for k in ('audio', 'scores')):
        raise HTTPException(400, '作品目录不能是符号链接。')
    for kind in ('audio', 'scores'):
        safe_call((work / kind).mkdir, 0o755, True, True)
    return {'directory': str(work)}

@app.post('/api/scan')
def scan(value: Selection):
    return safe_call(scan_dataset, value.root)

@app.post('/api/preview')
def preview(value: Split):
    inventory = safe_call(scan_dataset, value.root)
    if inventory['fingerprint'] != value.fingerprint:
        raise HTTPException(409, '文件发生变化，请重新扫描。')
    parts = safe_call(split_dataset, inventory, value.ratios, value.seed)
    return {'parts': parts, 'groups': {k: len({w['group_id'] for w in v}) for k, v in parts.items()}}

@app.post('/api/export')
def export(value: Split):
    return safe_call(export_dataset, value.root, value.ratios, value.seed, value.fingerprint)

@app.get('/api/file')
def file(root: str, path: str):
    base = Path(root).expanduser().resolve()
    source = (base / path).resolve()
    if not source.is_relative_to(base) or source.suffix.lower() not in AUDIO | {'.pdf'} or not source.is_file():
        raise HTTPException(404, '文件不可预览。')
    relative = source.relative_to(base)
    if len(relative.parts) < 3 or relative.parts[1] not in ('audio', 'scores'):
        raise HTTPException(404, '只预览作品目录中的录音与 PDF。')
    return FileResponse(source)

from dataset_cloud import router as cloud_router
app.include_router(cloud_router)

# Page images work in embedded browsers without a native PDF plugin.
from fastapi.responses import Response
from fastapi import Query
import threading
pdf_lock = threading.Lock()


def pdf_document(root, path):
    import pymupdf
    source = Path(file(root, path).path)
    if source.suffix.lower() != '.pdf': raise HTTPException(400, '请选择 PDF 文件。')
    try:
        doc = pymupdf.open(source)
        if doc.needs_pass:
            doc.close()
            raise HTTPException(400, '此 PDF 已加密，请先解密后导入。')
        return doc
    except HTTPException: raise
    except Exception: raise HTTPException(400, '无法解析 PDF，文件可能损坏或不是有效乐谱文件。')


@app.get('/api/pdf/info')
def pdf_info(root: str, path: str):
    with pdf_lock, pdf_document(root, path) as doc:
        return {'pages': len(doc)}


@app.get('/api/pdf/page')
def pdf_page(root: str, path: str, page: int = Query(1, ge=1)):
    import pymupdf
    with pdf_lock, pdf_document(root, path) as doc:
        if page > len(doc): raise HTTPException(404, '页码超出范围。')
        try:
            sheet = doc[page - 1]
            scale = min(2.0, 2200 / max(sheet.rect.width, sheet.rect.height))
            data = sheet.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes('png')
            return Response(data, media_type='image/png', headers={'Cache-Control': 'no-store'})
        except Exception: raise HTTPException(400, '此页无法渲染，请下载原 PDF 查看。')

from dataset_omr import router as omr_router
app.include_router(omr_router)

from dataset_alignment import router as alignment_router
app.include_router(alignment_router)

@app.get("/alignment.js")
def alignment_script():
    return FileResponse(BASE / "dataset_ui/alignment.js",media_type="text/javascript")
