"""Read-only R2 dataset inventory and selective, verified local cache."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dataset import AUDIO, SCORES
from imslp_lock import run_lock


def atomic_json(path, data):
    part = path.with_suffix('.tmp')
    part.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    part.replace(path)


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): sha.update(block)
    return sha.hexdigest()


def safe_path(root, relative):
    parts = relative.split('/')
    if any(not p or p in ('.', '..') or re.search(r'[\\\x00-\x1f:]', p) or p.endswith((' ', '.')) for p in parts):
        raise ValueError('Unsupported object path')
    path = root.joinpath(*parts)
    for parent in (path, *path.parents):
        if parent == root: break
        if parent.is_symlink(): raise ValueError('Cache path contains a symlink')
    return path


class R2Dataset:
    def __init__(self, client, bucket, prefix='imslp'):
        self.client, self.bucket = client, bucket
        self.prefix = prefix.strip('/')
        self.base = self.prefix + '/' if self.prefix else ''
        endpoint = getattr(getattr(client, 'meta', None), 'endpoint_url', '')
        self.source = {'endpoint': endpoint, 'bucket': bucket, 'prefix': self.prefix}

    def inventory(self):
        works, skipped, token, seen = {}, [], None, set()
        while True:
            kwargs = {'Bucket': self.bucket, 'Prefix': self.base, 'MaxKeys': 1000}
            if token: kwargs['ContinuationToken'] = token
            page = self.client.list_objects_v2(**kwargs)
            for obj in page.get('Contents', []):
                key = obj['Key']
                if not key.startswith(self.base): raise ValueError('Object outside selected prefix')
                relative = key[len(self.base):]
                parts = relative.split('/')
                if relative.endswith('/') or not parts: continue
                try: safe_path(Path('/cache'), relative)
                except ValueError:
                    skipped.append({'key': key, 'reason': 'unsafe_path'});continue
                if parts[0].startswith(('.', '_')): continue
                kind = None
                if len(parts) == 2 and parts[1] == 'metadata.json': kind = 'metadata'
                elif len(parts) >= 3 and parts[1] in ('audio', 'scores'):
                    ext = Path(parts[-1]).suffix.lower()
                    if ext in (AUDIO if parts[1] == 'audio' else SCORES): kind = parts[1]
                if kind is None:
                    skipped.append({'key': key, 'reason': 'outside_work_audio_scores_layout'});continue
                if not obj.get('ETag') or obj.get('Size', 0) <= 0:
                    skipped.append({'key': key, 'reason': 'missing_etag_or_empty_file'});continue
                work = works.setdefault(parts[0], {'id': parts[0], 'audio': [], 'scores': [], 'metadata': []})
                work[kind].append({'key': key, 'path': relative, 'bytes': obj['Size'], 'etag': obj['ETag'], 'kind': kind})
            if not page.get('IsTruncated'): break
            token = page.get('NextContinuationToken')
            if not token or token in seen: raise ValueError('Invalid pagination token; listing incomplete')
            seen.add(token)
        result = []
        for work in sorted(works.values(), key=lambda w: w['id']):
            for kind in ('audio', 'scores', 'metadata'): work[kind].sort(key=lambda a: a['key'])
            work['eligible'] = bool(work['audio'] and work['scores'])
            result.append(work)
        return {'source': self.source, 'works': result, 'skipped': skipped,
                'eligible_count': sum(w['eligible'] for w in result)}

    def _fetch(self, obj, path, max_bytes):
        if obj['bytes'] > max_bytes: raise ValueError('Object exceeds size limit')
        response = self.client.get_object(Bucket=self.bucket, Key=obj['key'], IfMatch=obj['etag'])
        body, part = response['Body'], path.with_suffix(path.suffix + '.part')
        size, sha = 0, hashlib.sha256()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with part.open('wb') as stream:
                while chunk := body.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes: raise ValueError('Object exceeds size limit')
                    stream.write(chunk);sha.update(chunk)
            if size != obj['bytes'] or size != response.get('ContentLength', size):
                raise ValueError('Incomplete object download')
            checksum = response.get('Metadata', {}).get('sha256')
            if checksum and checksum != sha.hexdigest(): raise ValueError('Remote SHA-256 mismatch')
            if obj['kind'] == 'metadata': json.loads(part.read_text(encoding='utf-8'))
            part.replace(path)
            return {'etag': obj['etag'], 'sha256': sha.hexdigest(), 'bytes': size}
        finally:
            body.close();part.unlink(missing_ok=True)

    def pull(self, root, catalog, work_ids, max_mb=512):
        if catalog['source'] != self.source: raise ValueError('Inventory source mismatch')
        selected = set(work_ids)
        if selected - {w['id'] for w in catalog['works']}: raise ValueError('Selected work not in inventory')
        root = Path(root).expanduser().resolve();root.mkdir(parents=True, exist_ok=True)
        state_dir = safe_path(root, '.r2-import');state_dir.mkdir(exist_ok=True)
        state_file = safe_path(root, '.r2-import/state.json')
        result = {'root': str(root), 'downloaded': 0, 'cached': 0, 'failed': []}
        with run_lock(safe_path(root, '.r2-import/import.lock')):
            state = json.loads(state_file.read_text()) if state_file.exists() else {'source': self.source, 'objects': {}}
            if state['source'] != self.source: raise ValueError('Cache belongs to a different source; choose another root')
            for work in catalog['works']:
                if work['id'] not in selected: continue
                for obj in work['audio'] + work['scores'] + work['metadata']:
                    try:
                        path = safe_path(root, obj['path']);safe_path(root, obj['path'] + '.part')
                        previous = state['objects'].get(obj['key'])
                        if path.exists():
                            if not previous: raise ValueError('Local file is not managed by R2 cache; choose an empty root')
                            if previous['etag'] == obj['etag'] and path.stat().st_size == previous['bytes'] and digest(path) == previous['sha256']:
                                result['cached'] += 1;continue
                        state['objects'][obj['key']] = self._fetch(obj, path, max_mb * 1024 * 1024)
                        atomic_json(state_file, state);result['downloaded'] += 1
                    except (OSError, ValueError, BotoCoreError, ClientError) as exc:
                        reason = exc.response.get('Error', {}).get('Code', 'S3Error') if isinstance(exc, ClientError) else (str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
                        result['failed'].append({'key': obj['key'], 'reason': reason})
            atomic_json(safe_path(root, '.r2-import/last-result.json'), result)
        return result


def connect(endpoint):
    parts = urlsplit(endpoint)
    if parts.scheme != 'https' or not re.fullmatch(r'[a-z0-9]+(?:\.(?:eu|fedramp))?\.r2\.cloudflarestorage\.com', parts.hostname or '') or parts.username or parts.password or parts.port not in (None,443) or parts.path not in ('','/') or parts.query or parts.fragment:
        raise ValueError('Use the R2 S3 API endpoint for this account')
    access = os.environ.pop('R2_ACCESS_KEY_ID', None)
    secret = os.environ.pop('R2_SECRET_ACCESS_KEY', None)
    if not access or not secret: raise ValueError('R2 credentials unavailable; use the local secure-input launcher')
    return boto3.client('s3',endpoint_url=endpoint,aws_access_key_id=access.strip(),aws_secret_access_key=secret.strip(),region_name='auto',config=Config(connect_timeout=10,read_timeout=60,retries={'max_attempts':3,'mode':'standard'},request_checksum_calculation='when_required',response_checksum_validation='when_required'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['list','pull'])
    parser.add_argument('--endpoint',required=True)
    parser.add_argument('--bucket',default='music-scores')
    parser.add_argument('--prefix',default='imslp')
    parser.add_argument('--root',type=Path,default=Path('data/r2-cache'))
    parser.add_argument('--work',action='append',default=[],help='Work folder ID; repeat to select several')
    parser.add_argument('--limit',type=int,default=3,help='Default: first N works with both audio and scores')
    parser.add_argument('--max-mb',type=int,default=512)
    args=parser.parse_args()
    if args.limit<1 or args.max_mb<1: parser.error('limits must be positive')
    try:
        store=R2Dataset(connect(args.endpoint),args.bucket,args.prefix);catalog=store.inventory()
        args.root.mkdir(parents=True,exist_ok=True)
        state_dir=safe_path(args.root.resolve(),'.r2-import');state_dir.mkdir(exist_ok=True)
        atomic_json(safe_path(args.root.resolve(),'.r2-import/inventory.json'),catalog)
        if args.command=='list':
            print(json.dumps({'works':len(catalog['works']),'eligible':catalog['eligible_count'],'skipped':len(catalog['skipped']),'inventory':str(state_dir/'inventory.json')},ensure_ascii=False,indent=2));return 0
        ids=args.work or [w['id'] for w in catalog['works'] if w['eligible']][:args.limit]
        if not ids: raise ValueError('No works with both audio and scores found; check prefix and object layout')
        result=store.pull(args.root,catalog,ids,args.max_mb);print(json.dumps(result,ensure_ascii=False,indent=2));return 2 if result['failed'] else 0
    except (OSError,ValueError,BotoCoreError,ClientError) as exc:
        reason=exc.response.get('Error',{}).get('Code','S3Error') if isinstance(exc,ClientError) else (str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
        print(json.dumps({'error':reason},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
