"""Incremental local IMSLP -> S3/R2 sync. Credentials are read only from memory."""
import argparse
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from imslp_catalog import AUDIO, SCORES
from imslp_lock import run_lock


def atomic_json(path, value):
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def stamp(path):
    stat = path.stat()
    return f'{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}'


class SourceChanged(ValueError):
    """The collector published newer content; revisit it on the next pass."""


class Syncer:
    def __init__(self, root, client, bucket, prefix):
        self.root = Path(root).resolve()
        self.client, self.bucket, self.prefix = client, bucket, prefix.strip('/')
        self.state = self.root / '.imslp/r2'
        self.state.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.state / 'sync.sqlite3')
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS objects (destination TEXT, key TEXT, stamp TEXT, sha256 TEXT, bytes INTEGER, PRIMARY KEY(destination,key))')
        self.destination = bucket + '/' + self.prefix
        self.queue_stamp = None
        self.validated = set()
        self.deferred = []

    def close(self):
        self.db.close()

    def head(self, key):
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound'):
                return None
            raise

    def sync_file(self, path, key):
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('Unsafe source path')
        before = stamp(path)
        previous = self.db.execute('SELECT * FROM objects WHERE destination=? AND key=?', (self.destination, key)).fetchone()
        if previous and previous['stamp'] == before and key in self.validated:
            return False
        sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                sha.update(chunk)
                md5.update(chunk)
                size += len(chunk)
            if stamp(path) != before:
                raise SourceChanged('Source changed during hashing; retry next pass')
            checksum = sha.hexdigest()
            remote = self.head(key)
            matches = remote and remote['ContentLength'] == size and remote.get('Metadata', {}).get('sha256') == checksum
            uploaded = False
            if not matches:
                if remote and remote.get('Metadata', {}).get('collector') != 'music2pdf':
                    raise ValueError('Existing remote object is not owned by this synchronizer')
                stream.seek(0)
                self.client.put_object(Bucket=self.bucket, Key=key, Body=stream,
                    ContentLength=size, ContentMD5=base64.b64encode(md5.digest()).decode(),
                    ContentType=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                    Metadata={'sha256': checksum, 'collector': 'music2pdf'})
                uploaded = True
                remote = self.head(key)
            if not remote or remote['ContentLength'] != size or remote.get('Metadata', {}).get('sha256') != checksum:
                raise ValueError('Remote object failed size/SHA-256 metadata verification')
        if stamp(path) != before:
            raise SourceChanged('Source changed during upload; retry next pass')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?,?,?)', (self.destination, key, before, checksum, size))
        self.validated.add(key)
        if uploaded:
            print(json.dumps({'event': 'uploaded_verified', 'key': key, 'bytes': size}), flush=True)
        return uploaded

    def snapshot_queue(self):
        source = self.root / '.imslp/queue.sqlite3'
        if not source.is_file():
            return None
        current = tuple(stamp(p) if p.exists() else None for p in (source, Path(str(source) + '-wal')))
        target = self.state / 'queue.sqlite3'
        if current != self.queue_stamp or not target.exists():
            tmp = self.state / 'queue.sqlite3.tmp'
            src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            tmp.replace(target)
            self.queue_stamp = current
        return target

    def inventory(self):
        for folder in sorted(self.root.glob('imslp-*')):
            if not folder.is_dir() or folder.is_symlink():
                continue
            for path in sorted(folder.rglob('*')):
                if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
                    continue
                relative = path.relative_to(self.root)
                if path.name == 'metadata.json' or (path.suffix.lower() in AUDIO | SCORES and len(relative.parts) >= 3 and relative.parts[1] in ('audio', 'scores')):
                    yield path, self.prefix + '/' + relative.as_posix()
        raw = self.root / '.imslp/raw'
        if raw.is_dir() and not raw.is_symlink():
            for path in sorted(raw.iterdir()):
                if path.is_file() and not path.is_symlink() and path.suffix in ('.json', '.html'):
                    yield path, self.prefix + '/_source/raw/' + path.name

    def summary(self):
        count, size = self.db.execute('SELECT count(*),coalesce(sum(bytes),0) FROM objects WHERE destination=?', (self.destination,)).fetchone()
        return {'verified_objects': count, 'verified_bytes': size, 'bucket': self.bucket, 'prefix': self.prefix}

    def checkpoint(self, status, **extra):
        result = {**self.summary(), 'status': status, 'pid': os.getpid(), 'updated_at': datetime.now(timezone.utc).isoformat(), **extra}
        atomic_json(self.state / 'checkpoint.json', result)
        print(json.dumps(result), flush=True)
        return result

    def cycle(self):
        uploaded, errors = 0, []
        self.deferred = []
        paths = list(self.inventory())
        snapshot = self.snapshot_queue()
        if snapshot:
            paths.append((snapshot, self.prefix + '/_state/queue.sqlite3'))
        checkpoint = self.root / '.imslp/checkpoint.json'
        if checkpoint.is_file():
            paths.append((checkpoint, self.prefix + '/_state/collector-checkpoint.json'))
        for i, (path, key) in enumerate(paths):
            try:
                uploaded += self.sync_file(path, key)
            except SourceChanged as exc:
                self.deferred.append({'key': key, 'code': 'SourceChanged', 'reason': str(exc)})
            except ClientError as exc:
                code = exc.response.get('Error', {}).get('Code', 'S3Error')
                errors.append({'key': key, 'code': code})
                if code in ('AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch', '403', 'NoSuchBucket'):
                    self.checkpoint('blocked', failures=errors)
                    return False
            except (BotoCoreError, OSError, ValueError) as exc:
                error = {'key': key, 'code': type(exc).__name__}
                if isinstance(exc, ValueError): error['reason'] = str(exc)
                errors.append(error)
            if (i + 1) % 10 == 0:
                self.checkpoint('uploading', batch_verified=i + 1 - len(errors) - len(self.deferred),
                                batch_total=len(paths), failures=errors, deferred=self.deferred)
        self.checkpoint('retrying' if errors else 'watching', uploaded_this_pass=uploaded,
                        batch_total=len(paths), failures=errors, deferred=self.deferred)
        return not errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--prefix', default='imslp')
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    client = boto3.client('s3', endpoint_url=args.endpoint,
        aws_access_key_id=os.environ.pop('R2_ACCESS_KEY_ID').strip(),
        aws_secret_access_key=os.environ.pop('R2_SECRET_ACCESS_KEY').strip(), region_name='auto',
        config=Config(connect_timeout=10, read_timeout=120, retries={'max_attempts': 3, 'mode': 'standard'},
                      request_checksum_calculation='when_required', response_checksum_validation='when_required'))
    state = args.root / '.imslp/r2'
    state.mkdir(parents=True, exist_ok=True)
    with run_lock(state / 'sync.lock'):
        sync = Syncer(args.root, client, args.bucket, args.prefix)
        try:
            sync.checkpoint('starting')
            client.head_bucket(Bucket=args.bucket)
            # A small permanent dataset descriptor verifies write and actual readback.
            descriptor = state / 'dataset.json'
            atomic_json(descriptor, {'source': 'IMSLP', 'schema_version': 1,
                'layout': 'imslp-{work_id}/audio|scores; metadata.json per work',
                'training_ready': False, 'label_status': 'unverified_unaligned'})
            descriptor_key = args.prefix.strip('/') + '/dataset.json'
            sync.sync_file(descriptor, descriptor_key)
            response = client.get_object(Bucket=args.bucket, Key=descriptor_key)
            try:
                if response['Body'].read() != descriptor.read_bytes():
                    raise ValueError('Descriptor readback mismatch')
            finally:
                response['Body'].close()
            sync.checkpoint('uploading', write_and_readback='verified')
            failures = 0
            while True:
                ok = sync.cycle()
                failures = 0 if ok else failures + 1
                if not args.watch:
                    return 0 if ok and not sync.deferred else 2
                if failures >= 3:
                    sync.checkpoint('blocked', reason='Three unsuccessful passes; inspect prior failures and restart')
                    return 2
                time.sleep(30)
        except (ClientError, BotoCoreError, OSError, ValueError) as exc:
            code = exc.response.get('Error', {}).get('Code') if isinstance(exc, ClientError) else type(exc).__name__
            sync.checkpoint('blocked', error_code=code,
                            operation=exc.operation_name if isinstance(exc, ClientError) else None)
            return 2
        except KeyboardInterrupt:
            sync.checkpoint('paused')
            return 130
        finally:
            sync.close()


if __name__ == '__main__':
    raise SystemExit(main())
