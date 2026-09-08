"""Search and review external recording candidates for local IMSLP works."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from imslp_catalog import AUDIO
from imslp_collector import file_hash, positive
from imslp_lock import run_lock
from recording_match import work_identity, build_queries, rank_candidate


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def identity_hash(identity):
    return hashlib.sha256(packed({'identity': identity, 'match_version': 2}).encode()).hexdigest()


class RecordingCollector:
    def __init__(self, root, sources, http):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError('Dataset root must already exist')
        self.sources, self.http = sources, http
        self.state = self.safe('.recordings')
        self.state.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.safe('.recordings/queue.sqlite3'))
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS searches (
            work_id TEXT, provider TEXT, fingerprint TEXT, state TEXT, details TEXT,
            PRIMARY KEY(work_id, provider));
          CREATE TABLE IF NOT EXISTS candidates (
            work_id TEXT, id TEXT, data TEXT, match TEXT, state TEXT DEFAULT 'candidate',
            path TEXT, sha256 TEXT, bytes INTEGER, review_note TEXT, error TEXT,
            PRIMARY KEY(work_id,id));
        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(candidates)')}
        for name in ('stale', 'download_source', 'identity_fingerprint'):
            if name not in columns:
                self.db.execute(f'ALTER TABLE candidates ADD COLUMN {name} TEXT')
        self.db.execute("UPDATE candidates SET download_source=data WHERE state='downloaded' AND download_source IS NULL")
        self.db.commit()

    def close(self):
        self.db.close()

    def safe(self, relative):
        path = self.root / relative
        if not path.is_relative_to(self.root) or '..' in path.parts:
            raise ValueError('Path outside dataset')
        current = path
        while current != self.root:
            if current.is_symlink(): raise ValueError('Symlink output is not supported')
            current = current.parent
        return path

    def work_folder(self, work_id):
        if not re.fullmatch(r'imslp-[A-Za-z0-9-]+', work_id):
            raise ValueError('Use a local imslp-<id> work directory')
        folder = self.safe(work_id)
        if not folder.is_dir(): raise ValueError('Work directory does not exist')
        return folder

    def candidates(self, work_id):
        self.work_folder(work_id)
        output = []
        for row in self.db.execute('SELECT * FROM candidates WHERE work_id=? ORDER BY id', (work_id,)):
            output.append({**json.loads(row['data']), 'match': json.loads(row['match']),
                           'download_source': json.loads(row['download_source']) if row['download_source'] else None,
                           **{k: row[k] for k in ('state', 'path', 'sha256', 'bytes', 'review_note', 'error', 'stale')}})
        return sorted(output, key=lambda x: (bool(x['stale']), -x['match']['score'], x['id']))

    def export(self, work_id):
        self.work_folder(work_id)
        folder = self.safe(f'{work_id}/recordings')
        folder.mkdir(exist_ok=True)
        searches = []
        for row in self.db.execute('SELECT * FROM searches WHERE work_id=? ORDER BY provider', (work_id,)):
            searches.append({'provider': row['provider'], 'state': row['state'], **json.loads(row['details'])})
        data = {'schema_version': 1, 'work_id': work_id, 'updated_at': now(),
                'training_ready': False, 'label_status': 'unverified_unaligned',
                'searches': searches, 'candidates': self.candidates(work_id)}
        target = self.safe(f'{work_id}/recordings/metadata.json')
        if target.is_file():
            try:
                previous = json.loads(target.read_text(encoding='utf-8'))
                if isinstance(previous, dict) and {k: v for k, v in previous.items() if k != 'updated_at'} == {k: v for k, v in data.items() if k != 'updated_at'}:
                    return
            except (ValueError, OSError):
                pass
        tmp = self.safe(f'{work_id}/recordings/metadata.json.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(target)

    def search(self, max_works=10, work_id=None, composer='', limit=5, retry=False, refresh=False):
        if max_works < 1 or not 1 <= limit <= 20: raise ValueError('Positive work bound and 1..20 results required')
        folders = [self.work_folder(work_id)] if work_id else sorted(self.root.glob('imslp-*'))
        processed = 0
        for folder in folders:
            if processed >= max_works: break
            if folder.is_symlink() or not folder.is_dir(): continue
            work_id = folder.name
            metadata_path = self.safe(f'{work_id}/metadata.json')
            if not metadata_path.is_file(): continue
            identity = work_identity(json.loads(metadata_path.read_text(encoding='utf-8')))
            if composer.casefold() not in identity['composer'].casefold(): continue
            queries = build_queries(identity)
            if not queries: continue
            identity_fingerprint = identity_hash(identity)
            fingerprint = hashlib.sha256(packed({'identity': identity, 'queries': queries, 'limit': limit, 'version': 2}).encode()).hexdigest()
            with self.db:
                for row in self.db.execute('SELECT * FROM candidates WHERE work_id=?', (work_id,)).fetchall():
                    if row['identity_fingerprint'] != identity_fingerprint:
                        self.db.execute("UPDATE candidates SET match=?,stale='work_metadata_changed',identity_fingerprint=? WHERE work_id=? AND id=?",
                                        (packed(rank_candidate(identity, json.loads(row['data']))), identity_fingerprint, work_id, row['id']))
            active = []
            for provider in self.sources:
                row = self.db.execute('SELECT * FROM searches WHERE work_id=? AND provider=?', (work_id, provider)).fetchone()
                if refresh or not row or row['fingerprint'] != fingerprint or (retry and row['state'] == 'failed'):
                    active.append(provider)
            if not active:
                # Reconstruct sidecar if interrupted between DB commit and export.
                self.export(work_id)
                continue
            processed += 1
            for provider in active:
                found, errors, truncated = {}, [], False
                for query in queries:
                    try:
                        result = self.sources[provider].search(query, limit)
                        for candidate in result['candidates']:
                            found[candidate['id']] = candidate
                        truncated |= result['truncated']
                    except (ValueError, RuntimeError, OSError) as exc:
                        errors.append({'query': query, 'error': str(exc)})
                state = 'failed' if errors else 'done'
                detail = {'queries': queries, 'limit': limit, 'truncated': truncated,
                          'errors': errors, 'found': len(found), 'searched_at': now()}
                with self.db:
                    for row in self.db.execute('SELECT id,data FROM candidates WHERE work_id=?', (work_id,)).fetchall():
                        if json.loads(row['data']).get('provider') == provider and row['id'] not in found:
                            self.db.execute('UPDATE candidates SET stale=? WHERE work_id=? AND id=?',
                                            ('search_incomplete' if errors else 'not_returned_by_latest_search', work_id, row['id']))
                    for candidate in found.values():
                        self.db.execute('''INSERT INTO candidates(work_id,id,data,match,identity_fingerprint) VALUES(?,?,?,?,?)
                            ON CONFLICT(work_id,id) DO UPDATE SET data=excluded.data,match=excluded.match,
                            identity_fingerprint=excluded.identity_fingerprint,stale=NULL''',
                            (work_id, candidate['id'], packed(candidate), packed(rank_candidate(identity, candidate)), identity_fingerprint))
                    self.db.execute('INSERT OR REPLACE INTO searches VALUES(?,?,?,?,?)', (work_id, provider, fingerprint, state, packed(detail)))
                self.export(work_id)
                print(packed({'event': 'recording_search', 'work_id': work_id, 'provider': provider, 'state': state, 'found': len(found), 'truncated': truncated}), flush=True)
        return {**self.status(), 'processed_works': processed}

    def download(self, work_id, candidate_id, review_note):
        self.work_folder(work_id)
        if not review_note.strip(): raise ValueError('A review note describing the checked work/version is required')
        row = self.db.execute('SELECT * FROM candidates WHERE work_id=? AND id=?', (work_id, candidate_id)).fetchone()
        if row is None: raise ValueError('Candidate not found; search/list first')
        identity = work_identity(json.loads(self.safe(f'{work_id}/metadata.json').read_text(encoding='utf-8')))
        if row['identity_fingerprint'] != identity_hash(identity):
            with self.db:
                self.db.execute("UPDATE candidates SET stale='work_metadata_changed',match=? WHERE work_id=? AND id=?",
                                (packed(rank_candidate(identity, json.loads(row['data']))), work_id, candidate_id))
            self.export(work_id)
            raise ValueError('Work information changed; refresh search before selecting this candidate')
        if row['stale']: raise ValueError('Candidate is historical/stale; refresh search before selecting it')
        candidate = json.loads(row['data'])
        if candidate.get('access') != 'downloadable' or candidate.get('license', {}).get('download_allowed') is not True:
            raise ValueError('Candidate has restricted access or no recognized download license; reference retained')
        if candidate.get('extension') not in AUDIO: raise ValueError('Unsupported audio format')
        if row['state'] == 'downloaded':
            old = self.safe(row['path'])
            if old.is_file() and old.stat().st_size == row['bytes'] and file_hash(old) == row['sha256']:
                self.export(work_id)
                return next(x for x in self.candidates(work_id) if x['id'] == candidate_id)
        token = hashlib.sha256(candidate_id.encode()).hexdigest()[:24]
        relative = f"{work_id}/audio/external-{token}{candidate['extension']}"
        target = self.safe(relative)
        stage = self.safe(f".recordings/staging/{token}{candidate['extension']}")
        self.safe(str(stage.relative_to(self.root)) + '.part')
        if shutil.disk_usage(self.root).free < 2 * 1024**3: raise ValueError('Less than 2 GiB free; download deferred')
        try:
            result = self.http.download(candidate, stage)
            if not stage.is_file() or file_hash(stage) != result['sha256'] or stage.stat().st_size != result['bytes']:
                raise ValueError('Downloaded file failed local checksum verification')
            target.parent.mkdir(exist_ok=True)
            if target.exists() and file_hash(target) != result['sha256'] and row['path'] != relative:
                raise ValueError('Refusing to overwrite an unrelated existing audio file')
            stage.replace(target)
            with self.db:
                self.db.execute("UPDATE candidates SET state='downloaded',path=?,sha256=?,bytes=?,review_note=?,download_source=?,error=NULL WHERE work_id=? AND id=?",
                                (relative, result['sha256'], result['bytes'], review_note.strip(),
                                 packed({**candidate, 'match': json.loads(row['match']), 'acquired_at': now()}), work_id, candidate_id))
        except (ValueError, RuntimeError, OSError) as exc:
            with self.db:
                self.db.execute("UPDATE candidates SET state='failed',error=?,review_note=? WHERE work_id=? AND id=?", (str(exc), review_note.strip(), work_id, candidate_id))
            self.export(work_id)
            raise
        finally:
            stage.unlink(missing_ok=True)
        self.export(work_id)
        return next(x for x in self.candidates(work_id) if x['id'] == candidate_id)

    def status(self):
        return {'root': str(self.root), 'searches': dict(self.db.execute('SELECT state,count(*) FROM searches GROUP BY state')),
                'candidates': dict(self.db.execute('SELECT state,count(*) FROM candidates GROUP BY state'))}


def main():
    parser = argparse.ArgumentParser(description='为本地 IMSLP 乐谱搜索外部录音候选；选定后下载并保留匹配依据')
    parser.add_argument('command', choices=('search', 'list', 'download', 'status'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--work', help='本地作品文件夹名称，例如 imslp-12345')
    parser.add_argument('--composer', default='')
    parser.add_argument('--provider', choices=('archive', 'commons', 'all'), default='all')
    parser.add_argument('--max-works', type=positive, default=10)
    parser.add_argument('--limit', type=positive, default=5, help='每个查询每个平台最多返回的条目数，最大20')
    parser.add_argument('--retry', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--candidate', help='从 list 结果取得的候选 ID')
    parser.add_argument('--review-note', default='', help='下载前核对作品、乐章、编制和版本的说明')
    parser.add_argument('--max-mb', type=positive, default=200)
    parser.add_argument('--delay', type=positive, default=2)
    args = parser.parse_args()
    if args.limit > 20: parser.error('--limit must be <= 20')
    if args.command in ('list', 'download') and not args.work: parser.error('--work is required')
    if args.command == 'download' and not args.candidate: parser.error('--candidate is required')
    from recording_sources import SOURCES, RecordingHTTP
    collector = None
    try:
        http = RecordingHTTP(delay=args.delay, max_mb=args.max_mb)
        sources = {name: factory(http) for name, factory in SOURCES.items() if args.provider in ('all', name)}
        collector = RecordingCollector(args.root, sources, http)
        with run_lock(collector.safe('.recordings/collector.lock')):
            if args.command == 'search': result = collector.search(args.max_works, args.work, args.composer, args.limit, args.retry, args.refresh)
            elif args.command == 'list': result = collector.candidates(args.work)
            elif args.command == 'download': result = collector.download(args.work, args.candidate, args.review_note)
            else: result = collector.status()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if args.command == 'search' and result['searches'].get('failed', 0) else 0
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(packed({'status': 'incomplete', 'error': str(exc)}))
        return 2
    except KeyboardInterrupt:
        print('已保存进度，可再次运行相同命令继续。')
        return 130
    finally:
        if collector: collector.close()


if __name__ == '__main__': raise SystemExit(main())
