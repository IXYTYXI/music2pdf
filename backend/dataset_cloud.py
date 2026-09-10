"""R2 UI bridge: credentials stay in process memory; remote objects are read-only."""
import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit, unquote
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr
import cloud_credentials
from r2_import import R2Dataset, boto3, Config

router = APIRouter(prefix='/api/cloud')
BASE = Path(__file__).resolve().parent
lock = threading.Lock()
sessions = {}


def parse_link(link):
    p = urlsplit(link.strip())
    if p.scheme != 'https' or not re.fullmatch(r'[a-z0-9]+(?:\.(?:eu|fedramp))?\.r2\.cloudflarestorage\.com', p.hostname or '') or p.username or p.password or p.port not in (None, 443) or p.query or p.fragment:
        raise ValueError('请填写 R2 S3 链接：https://账户.r2.cloudflarestorage.com/桶名/前缀，不支持控制台或单文件分享链接。')
    parts = unquote(p.path).strip('/').split('/', 1)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', parts[0]):
        raise ValueError('链接需要包含有效桶名。')
    prefix = parts[1].strip('/') if len(parts) > 1 else ''
    if any(x in ('.', '..') for x in prefix.split('/')) or '\\' in prefix:
        raise ValueError('目录前缀无效。')
    return {'endpoint': f'https://{p.hostname}', 'bucket': parts[0], 'prefix': prefix}


class Connection(BaseModel):
    link: str
    access: SecretStr = SecretStr('')
    secret: SecretStr = SecretStr('')
    remember: bool = False
    use_saved: bool = False

class Pull(BaseModel):
    session: str
    works: list[str] = Field(min_length=1, max_length=100)

class Session(BaseModel):
    session: str

@router.get('/config')
def config():
    saved = cloud_credentials.profile()
    if saved: return {'link': saved['link'], 'saved': True}
    path = BASE / 'data/r2-cache/.r2-import/inventory.json'
    source = json.loads(path.read_text())['source'] if path.exists() else None
    return {'link': source['endpoint'].rstrip('/') + '/' + source['bucket'] + '/' + source['prefix'] if source else ''}

@router.post('/connect')
def connect(value: Connection):
    import secrets
    try:
        source = parse_link(value.link)
        link = source['endpoint'] + '/' + source['bucket'] + '/' + source['prefix']
        access, secret = cloud_credentials.load(link) if value.use_saved else (value.access.get_secret_value().strip(), value.secret.get_secret_value().strip())
        if not access or not secret:
            raise ValueError('请输入 Access Key ID 和 Secret Access Key。')
        client = boto3.client('s3', endpoint_url=source['endpoint'], aws_access_key_id=access, aws_secret_access_key=secret, region_name='auto', config=Config(connect_timeout=10,read_timeout=30,retries={'max_attempts':2},request_checksum_calculation='when_required',response_checksum_validation='when_required'))
        store = R2Dataset(client, source['bucket'], source['prefix'])
        catalog = store.inventory()
        token = secrets.token_urlsafe(32)
        root = BASE / 'data/cloud-cache' / hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()[:20]
        with lock:
            if len(sessions) >= 8: raise ValueError('连接数量已达上限，请先断开旧连接。')
            if value.remember: cloud_credentials.save(link, access, secret)
            sessions[token] = (store, catalog, root)
        return {'session': token, 'catalog': catalog, 'root': str(root), 'saved': value.remember or value.use_saved}
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    except Exception:
        raise HTTPException(400,'R2 连接失败，请检查链接、凭据和桶读取权限。')

@router.post('/pull')
def pull(value: Pull):
    if not lock.acquire(blocking=False): raise HTTPException(409,'正在缓存，请稍后再试。')
    try:
        entry = sessions.get(value.session)
        if not entry: raise HTTPException(401,'连接已失效，请重新连接。')
        store, _, root = entry
        catalog = store.inventory()
        return store.pull(root, catalog, value.works)
    except HTTPException: raise
    except ValueError as exc: raise HTTPException(400,str(exc))
    except Exception: raise HTTPException(400,'缓存失败，请检查连接后重试。')
    finally: lock.release()

@router.post('/disconnect')
def disconnect(value: Session):
    with lock:
        entry = sessions.pop(value.session, None)
        if entry: entry[0].client.close()
    return {'disconnected': True}

@router.post('/forget')
def forget():
    try:
        with lock:
            cloud_credentials.forget()
            for store, _, _ in sessions.values(): store.client.close()
            sessions.clear()
        return {'forgotten': True}
    except ValueError as exc: raise HTTPException(400, str(exc))
