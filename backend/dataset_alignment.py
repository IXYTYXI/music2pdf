"""Local score preparation and reviewable audio alignment endpoints."""
import hashlib,json,os,shutil,subprocess,threading,uuid,math,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field

BASE=Path(__file__).resolve().parent
DATA=BASE/'data/alignment'
router=APIRouter(prefix='/api/alignment')
lock=threading.Lock();active=set();pool=ThreadPoolExecutor(max_workers=1)

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,d):
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,allow_nan=False),encoding='utf-8');tmp.replace(p)

def muse():
    candidates=[os.environ.get('MUSESCORE_BIN',''),str(BASE/'data/tools/MuseScore 4.app/Contents/MacOS/mscore'),'/Applications/MuseScore 4.app/Contents/MacOS/mscore',shutil.which('mscore') or '']
    return next((p for p in candidates if p and Path(p).is_file()),None)

def location(kind,key):
    if len(key)!=32 or any(c not in '0123456789abcdef' for c in key):raise HTTPException(404,'记录不存在。')
    p=DATA/kind/key
    if not (p/'state.json').is_file():raise HTTPException(404,'记录不存在。')
    return p

def sources(root,work):
    from dataset import AUDIO
    root=Path(root).expanduser().resolve();folder=(root/work).resolve()
    if not folder.is_relative_to(root) or folder.parent!=root or not folder.is_dir() or work.startswith('.'):raise ValueError('作品目录无效。')
    scores=[];audios=[]
    for kind,exts in [('audio',AUDIO),('scores',{'.mxl','.musicxml','.xml','.mscz','.mscx'})]:
        for p in sorted((folder/kind).rglob('*')):
            if p.is_file() and p.suffix.lower() in exts and p.resolve().is_relative_to(folder):
                (audios if kind=='audio' else scores).append({'id':p.relative_to(root).as_posix(),'label':p.name,'path':str(p)})
    from dataset_omr import JOBS
    for state in JOBS.glob('*/state.json'):
        d=json.loads(state.read_text())
        if d.get('root')!=str(root) or Path(d.get('path','')).parts[:1]!=(work,):continue
        for f in d.get('results',[])+([d['corrected']] if d.get('corrected') else []):
            p=(state.parent/f['name']).resolve()
            if p.is_relative_to(state.parent.resolve()) and p.is_file():scores.append({'id':'omr:'+d['id']+':'+f['name'],'label':f"识谱页{d['pages']} · {Path(f['name']).name} · {'已提交人工校对' if d.get('reviewed') and f==d.get('corrected') else '待校对'}",'path':str(p)})
    return {'scores':scores,'audio':audios}

def selected(root,work,key,kind):
    values=sources(root,work)[kind]
    item=next((x for x in values if x['id']==key),None)
    if not item:raise ValueError('选定文件不属于当前作品或已被移除。')
    return Path(item['path'])

def convert(exe,source,target):
    env=os.environ.copy()
    if sys.platform.startswith('linux'):env['QT_QPA_PLATFORM']='offscreen'
    target.unlink(missing_ok=True)
    with (target.parent/'musescore.log').open('ab') as log:
        result=subprocess.run([exe,'-o',str(target),str(source)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    if result.returncode or not target.is_file() or not target.stat().st_size:raise ValueError(f'MuseScore转换失败（退出码 {result.returncode}），请在软件中核查该文件。')

class Selection(BaseModel):
    root:str
    work:str
class Prepare(Selection):
    score:str
    bpm:float|None=None
    repeats:bool=True
class Key(BaseModel):
    key:str
class Start(Selection):
    prepared:str
    audio:str
    bpm:float|None=None
    repeats:bool=True
    measure_start:int=Field(ge=1)
    measure_end:int=Field(ge=1)
    audio_start:float=Field(ge=0)
    audio_end:float=Field(gt=0)
class Row(BaseModel):
    id:int
    start:float
    end:float
    matched:bool=True
class Review(BaseModel):
    rows:list[Row]
    reviewed:bool=False

@router.get('/sources')
def list_sources(root:str,work:str):
    try:
        d=sources(root,work)
        for values in d.values():
            for item in values:item.pop('path')
        return {**d,'musescore_available':bool(muse())}
    except Exception as e:raise HTTPException(400,str(e) if isinstance(e,ValueError) else '无法读取文件列表。')

@router.post('/prepare')
def prepare(v:Prepare):
    from score_timeline import read_timeline
    try:
        source=selected(v.root,v.work,v.score,'scores');sha=digest(source)
        key=hashlib.sha256(('v2:'+str(source)+sha).encode()).hexdigest()[:32]
        folder=DATA/'scores'/key;folder.mkdir(parents=True,exist_ok=True);score=folder/'score.musicxml'
        exe=muse()
        with lock:
            if not score.exists():
                if source.suffix.lower() in ('.mscz','.mscx'):
                    if not exe:raise ValueError('MSCZ需要安装MuseScore或设置MUSESCORE_BIN。')
                    convert(exe,source,score)
                else:
                    from dataset_omr import summary
                    summary(source.read_bytes())
                    # music21 detects MXL from bytes only through its archive extension.
                    if source.suffix.lower()=='.mxl':
                        import zipfile
                        from xml.etree import ElementTree as ET
                        with zipfile.ZipFile(source) as archive:
                            container=ET.fromstring(archive.read('META-INF/container.xml'))
                            name=next(e.attrib['full-path'] for e in container.iter() if e.tag.split('}')[-1]=='rootfile')
                            score.write_bytes(archive.read(name))
                    else:shutil.copyfile(source,score)
            state={'id':key,'root':str(Path(v.root).expanduser().resolve()),'work':v.work,'original_path':str(source),'original_sha256':sha}
            save(folder/'state.json',state)
            timeline=read_timeline(score,v.bpm,v.repeats)
            if exe:convert(exe,score,folder/'score.pdf')
        return {'id':key,'timeline':timeline,'pdf':(folder/'score.pdf').exists(),'musescore_available':bool(exe)}
    except Exception as e:raise HTTPException(400,str(e) if isinstance(e,ValueError) else '乐谱读取或转换失败，请检查乐谱结构与速度设置。')

@router.post('/open')
def open_score(v:Key):
    exe=muse()
    if not exe:raise HTTPException(503,'MuseScore未安装。')
    folder=location('scores',v.key)
    subprocess.Popen([exe,str(folder/'score.musicxml')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    return {'opened':True}

@router.get('/scores/{key}/file')
def score_file(key:str,name:str):
    if name not in ('score.musicxml','score.pdf'):raise HTTPException(404,'文件不存在。')
    p=location('scores',key)/name
    if not p.is_file():raise HTTPException(404,'文件未生成。')
    return FileResponse(p,filename=name)

@router.get('/scores/{key}/page')
def score_page(key:str,page:int=1):
    import pymupdf
    from dataset_app import pdf_lock
    path=location('scores',key)/'score.pdf'
    if not path.is_file():raise HTTPException(404,'谱面尚未生成。')
    with pdf_lock,pymupdf.open(path) as doc:
        if not 1<=page<=len(doc):raise HTTPException(404,'页码超出范围。')
        p=doc[page-1];scale=min(2,2200/max(p.rect.width,p.rect.height))
        return Response(p.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).tobytes('png'),media_type='image/png',headers={'X-PDF-Pages':str(len(doc))})

def execute(folder,state,v):
    try:
        prepared=location('scores',v.prepared)
        audio=selected(v.root,v.work,v.audio,'audio')
        state.update(status='running',message='正在提取音频特征并对齐…');save(folder/'state.json',state)
        shutil.copyfile(prepared/'score.musicxml',folder/'input.musicxml')
        save(folder/'worker-input.json',{'request':v.model_dump(),'audio_path':str(audio),'score_source':json.loads((prepared/'state.json').read_text())})
        with (folder/'worker.log').open('wb') as log:
            result=subprocess.run([sys.executable,str(BASE/'alignment_worker.py'),str(folder)],stdout=log,stderr=subprocess.STDOUT,timeout=900)
        if result.returncode or not (folder/'automatic.json').exists():
            raise ValueError('对齐计算失败：'+(folder/'worker.log').read_text(errors='replace')[-500:])
        proposal=json.loads((folder/'automatic.json').read_text())
        state.update(status='needs_review',message='已生成自动对齐候选，请试听并修正。',result=proposal)
    except subprocess.TimeoutExpired:state.update(status='failed',message='对齐超过15分钟，请缩小片段后重试。')
    except Exception as e:state.update(status='failed',message=str(e) if isinstance(e,ValueError) else '对齐失败，请检查音频格式和对应片段。')
    finally:
        save(folder/'state.json',state)
        with lock:active.discard(state['id'])

@router.post('/jobs')
def start(v:Start):
    try:
        folder=location('scores',v.prepared);s=json.loads((folder/'state.json').read_text())
        if s['root']!=str(Path(v.root).expanduser().resolve()) or s['work']!=v.work:raise ValueError('乐谱与当前作品不一致。')
        selected(v.root,v.work,v.audio,'audio')
        if not math.isfinite(v.audio_end) or not math.isfinite(v.audio_start) or v.audio_end<=v.audio_start:raise ValueError('音频起止时间无效。')
        with lock:
            if len(active)>=3:raise ValueError('已有3个任务，请稍后再试。')
            key=uuid.uuid4().hex;dest=DATA/'jobs'/key;dest.mkdir(parents=True)
            state={'id':key,'status':'queued','message':'等待对齐。','request':v.model_dump()};save(dest/'state.json',state);active.add(key);pool.submit(execute,dest,state,v)
        return state
    except ValueError as e:raise HTTPException(400,str(e))

@router.get('/jobs')
def history(root:str,work:str):
    result=[]
    for p in (DATA/'jobs').glob('*/state.json'):
        s=json.loads(p.read_text());r=s['request']
        if str(Path(r['root']).expanduser().resolve())==str(Path(root).expanduser().resolve()) and r['work']==work:result.append(status(s['id']))
    return {'jobs':result}

@router.get('/jobs/{key}')
def status(key:str):
    folder=location('jobs',key);s=json.loads((folder/'state.json').read_text())
    if s['status'] in ('queued','running') and key not in active:s.update(status='interrupted',message='服务重启导致中断，请重新提交。')
    if (folder/'reviewed.json').exists():s['result']=json.loads((folder/'reviewed.json').read_text())
    return s

@router.post('/jobs/{key}/review')
def review(key:str,v:Review):
    from alignment_engine import validate_corrections
    folder=location('jobs',key)
    with lock:
        p=folder/'automatic.json'
        if not p.exists():raise HTTPException(400,'任务尚未生成结果。')
        d=json.loads(p.read_text());rows=[r.model_dump() for r in v.rows]
        try:validate_corrections(rows,d['rows'],d['audio_window'][1])
        except ValueError as e:raise HTTPException(400,str(e))
        merged=[{**old,**new} for old,new in zip(d['rows'],rows)]
        d.update(rows=merged,reviewed=v.reviewed,training_ready=False)
        save(folder/'reviewed.json',d)
        return d

@router.get('/jobs/{key}/export')
def export(key:str):
    folder=location('jobs',key);p=folder/'reviewed.json'
    if not p.exists():p=folder/'automatic.json'
    if not p.exists():raise HTTPException(404,'尚无对齐结果。')
    return FileResponse(p,filename='alignment-'+key+'.json')
