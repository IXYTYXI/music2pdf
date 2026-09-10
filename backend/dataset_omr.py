"""Local, queued optical music recognition and human-reviewed derivatives."""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from io import BytesIO
from xml.etree import ElementTree as ET
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
JOBS = BASE / 'data/omr'
router = APIRouter(prefix='/api/omr')
executor = ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()
active = set()


def engine():
    candidates = [os.environ.get('AUDIVERIS_BIN', ''), str(BASE/'data/tools/Audiveris.app/Contents/MacOS/Audiveris'), '/Applications/Audiveris.app/Contents/MacOS/Audiveris', shutil.which('audiveris') or '']
    return next((p for p in candidates if p and Path(p).is_file()), None)


def job_dir(job):
    if not len(job)==32 or any(c not in '0123456789abcdef' for c in job): raise HTTPException(404,'任务不存在。')
    folder=JOBS/job
    if not (folder/'state.json').is_file(): raise HTTPException(404,'任务不存在。')
    return folder


def write_state(folder, data):
    part=folder/'state.tmp';part.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');part.replace(folder/'state.json')


def summary(data):
    if len(data)>20*1024*1024: raise ValueError('乐谱文件超过20 MB限制。')
    if data.startswith(b'PK'):
        with zipfile.ZipFile(BytesIO(data)) as z:
            container=z.getinfo('META-INF/container.xml')
            if container.file_size>100000: raise ValueError('MXL 容器信息异常。')
            tree=ET.fromstring(z.read(container))
            names=[e.attrib.get('full-path') for e in tree.iter() if e.tag.split('}')[-1]=='rootfile']
            if not names: raise ValueError('MXL 中没有 MusicXML。')
            item=z.getinfo(names[0])
            if item.file_size>20*1024*1024: raise ValueError('解压后的谱文件过大。')
            data=z.read(item)
    # MusicXML's external DOCTYPE is common, but entity declarations are not needed.
    if b'<!ENTITY' in data.upper(): raise ValueError('不支持包含实体声明的 XML。')
    tree=ET.fromstring(data)
    if tree.tag not in ('score-partwise','score-timewise'): raise ValueError('文件不是 MusicXML 总谱。')
    notes=sum(1 for n in tree.iter('note') if n.find('pitch') is not None)
    if not notes: raise ValueError('结果没有可识别的有音高音符，请在识谱软件中检查。')
    return {'notes': notes, 'parts':len(list(tree.iter('score-part'))),'measures':len(list(tree.iter('measure')))}


def work(folder, executable, state):
    try:
        state['status']='running';state['message']='正在识别谱面与音符…';write_state(folder,state)
        command=[executable,'-batch','-transcribe','-export','-save','-swap','-output',str(folder/'output'), '--',str(folder/'input.pdf')]
        with (folder/'engine.log').open('wb') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        if result.returncode: raise ValueError('识谱程序未正常完成，请下载日志查看。')
        files=[]
        for p in sorted((folder/'output').rglob('*')):
            if p.suffix.lower() in ('.mxl','.xml','.musicxml'):
                try: info=summary(p.read_bytes())
                except Exception: continue
                files.append({'name':p.relative_to(folder).as_posix(),**info})
        if not files: raise ValueError('没有导出有效音符谱。可尝试跳过封面、调整页码，或打开 Audiveris 手工修正。')
        state.update(status='needs_review',results=files,message='识谱完成，待人工校对；尚未与录音对齐。')
    except subprocess.TimeoutExpired: state.update(status='failed',message='识谱超过30分钟，请选择较短页段重试。')
    except Exception as exc: state.update(status='failed',message=str(exc) if isinstance(exc,ValueError) else '识谱失败，请查看日志。')
    finally:
        write_state(folder,state)
        with lock: active.discard(state['id'])


class Start(BaseModel):
    root:str
    path:str
    start:int=Field(default=1,ge=1)
    end:int=Field(default=1,ge=1)

class Corrected(BaseModel):
    filename:str
    content:str=Field(max_length=28*1024*1024)
    reviewed:bool=False
    note:str=Field(default='',max_length=2000)

@router.get('/config')
def config(): return {'available': bool(engine()), 'engine':'Audiveris','max_pages':30}

@router.post('/jobs')
def start(value:Start):
    executable=engine()
    if not executable: raise HTTPException(503,'尚未安装 Audiveris，请配置 AUDIVERIS_BIN。')
    root=Path(value.root).expanduser().resolve();source=(root/value.path).resolve()
    if not source.is_relative_to(root) or source.suffix.lower()!='.pdf' or not source.is_file(): raise HTTPException(404,'PDF 不存在。')
    relative=source.relative_to(root)
    if len(relative.parts)<3 or relative.parts[1]!='scores': raise HTTPException(400,'请选择作品 scores 文件夹中的 PDF。')
    if value.end<value.start or value.end-value.start>=30: raise HTTPException(400,'每次可识别1–30页，请检查起止页码。')
    import pymupdf
    # Serialize access to PyMuPDF with the preview service's lock.
    from dataset_app import pdf_lock
    with lock:
        if len(active)>=3: raise HTTPException(409,'已有3个任务等待或执行，请稍后提交。')
        job=uuid.uuid4().hex;folder=JOBS/job;folder.mkdir(parents=True)
        try:
            with pdf_lock, pymupdf.open(source) as doc, pymupdf.open() as selected:
                if doc.needs_pass or value.end>len(doc): raise ValueError('PDF 已加密或页码超出范围。')
                selected.insert_pdf(doc,from_page=value.start-1,to_page=value.end-1);selected.save(folder/'input.pdf')
            with source.open('rb') as stream: checksum=hashlib.file_digest(stream,'sha256').hexdigest()
            state={'id':job,'root':str(root),'path':relative.as_posix(),'source_sha256':checksum,'pages':[value.start,value.end],'status':'queued','results':[],'reviewed':False,'training_ready':False,'message':'等待识谱。'}
            write_state(folder,state);active.add(job);executor.submit(work,folder,executable,state)
            return state
        except Exception as exc:
            shutil.rmtree(folder)
            raise HTTPException(400,str(exc) if isinstance(exc,ValueError) else '无法读取 PDF。')

@router.get('/jobs')
def history(root:str,path:str):
    result=[]
    for f in JOBS.glob('*/state.json'):
        try:
            state=json.loads(f.read_text())
            if state['root']==str(Path(root).expanduser().resolve()) and state['path']==path: result.append(status(state['id']))
        except (OSError,ValueError,KeyError): continue
    return {'jobs':sorted(result,key=lambda x:x['id'])}

@router.get('/jobs/{job}')
def status(job:str):
    state=json.loads((job_dir(job)/'state.json').read_text())
    if state['status'] in ('queued','running') and job not in active:
        state.update(status='interrupted',message='服务已重启，识谱中断，请重新提交。')
    state['can_open'] = bool(list((job_dir(job)/'output').rglob('*.omr')))
    return state

@router.get('/jobs/{job}/file')
def download(job:str,name:str):
    folder=job_dir(job);p=(folder/name).resolve()
    if not p.is_relative_to(folder.resolve()) or not p.is_file() or p.suffix.lower() not in ('.mxl','.xml','.musicxml','.omr','.log','.pdf'): raise HTTPException(404,'文件不存在。')
    return FileResponse(p,filename=p.name)

@router.post('/jobs/{job}/corrected')
def corrected(job:str,value:Corrected):
    folder=job_dir(job)
    with lock:
        state=status(job)
        if state['status'] not in ('needs_review','reviewed'): raise HTTPException(400,'请先完成识谱。')
        try:
            suffix=Path(value.filename).suffix.lower()
            if suffix not in ('.mxl','.musicxml','.xml'): raise ValueError('请导入 MXL 或 MusicXML。')
            data=base64.b64decode(value.content,validate=True);info=summary(data)
        except Exception as exc: raise HTTPException(400,str(exc) if isinstance(exc,ValueError) else '乐谱文件无效。')
        name='corrected-'+uuid.uuid4().hex+suffix
        (folder/name).write_bytes(data)
        state.update(corrected={'name':name,**info},reviewed=value.reviewed,status='reviewed' if value.reviewed else 'needs_review',note=value.note,message='校对稿已保存；仍待与录音对齐。')
        write_state(folder,state)
        return state

@router.post('/jobs/{job}/open')
def open_editor(job:str):
    folder=job_dir(job);files=list((folder/'output').rglob('*.omr'))
    executable=engine()
    if not executable or not files: raise HTTPException(400,'尚无 Audiveris 工程可打开，请先完成识谱。')
    subprocess.Popen([executable,str(files[0])],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    return {'opened':True}
