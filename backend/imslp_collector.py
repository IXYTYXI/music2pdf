"""Automatic IMSLP discovery and collection into the Music2PDF dataset layout."""
import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from imslp_catalog import parse_catalog, parse_work
from imslp_http import HTTP, AccessBlocked

API = 'https://imslp.org/imslpscripts/API.ISCR.php?account=worklist/disclaimer=accepted/sort=id/type=2/start={}/retformat=json'


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class Collector:
    def __init__(self, root, http):
        self.root = Path(root).expanduser().resolve()
        self.http = http
        self.root.mkdir(parents=True, exist_ok=True)
        state = self.safe('.imslp')
        state.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.safe('.imslp/queue.sqlite3'), timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS works (
                id TEXT PRIMARY KEY, catalog TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                parsed TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS assets (
                work_id TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', path TEXT, sha256 TEXT, bytes INTEGER,
                error TEXT, PRIMARY KEY(work_id,id));
        ''')

    def safe(self, relative):
        path = self.root / relative
        if not path.is_relative_to(self.root) or '..' in path.parts:
            raise ValueError('Path outside dataset')
        current = path
        while current != self.root:
            if current.is_symlink():
                raise ValueError('Collector output cannot contain symlinks')
            current = current.parent
        return path

    def close(self):
        self.db.close()

    def state(self, key, default):
        row = self.db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def discover(self, pages=1, refresh=False):
        if refresh:
            with self.db:
                self.db.execute("DELETE FROM state WHERE key IN ('cursor','exhausted')")
        count = 0
        for _ in range(pages):
            if self.state('exhausted', False):
                break
            cursor = self.state('cursor', 0)
            works, next_cursor, more = parse_catalog(self.http.json(API.format(cursor)), cursor)
            with self.db:
                for work in works:
                    self.db.execute('INSERT INTO works(id,catalog) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET catalog=excluded.catalog', (work['id'], packed(work)))
                for key, value in [('cursor', next_cursor), ('exhausted', not more)]:
                    self.db.execute('INSERT OR REPLACE INTO state VALUES(?,?)', (key, packed(value)))
            count += len(works)
            print(packed({'event': 'catalog_page', 'start': cursor, 'records': len(works), 'more': more}), flush=True)
        return count

    def _manifest(self, work_id, catalog, parsed):
        folder = self.safe('imslp-' + work_id)
        folder.mkdir(exist_ok=True)
        target = self.safe(f'imslp-{work_id}/metadata.json')
        tmp = self.safe(f'imslp-{work_id}/metadata.json.tmp')
        assets = [dict(row) for row in self.db.execute('SELECT id,state,path,sha256,bytes,error FROM assets WHERE work_id=?', (work_id,))]
        tmp.write_text(json.dumps({'source': 'IMSLP', 'catalog': catalog, **parsed,
                                   'downloads': assets, 'training_ready': False,
                                   'label_status': 'unverified_unaligned'}, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(target)

    def collect(self, max_works=10, composer='', instrument='', require_both=False,
                retry=False, refresh=False, metadata_only=False, max_files=20):
        processed = downloaded = 0
        for row in self.db.execute('SELECT * FROM works ORDER BY rowid'):
            if processed >= max_works:
                break
            catalog = json.loads(row['catalog'])
            if composer.casefold() not in catalog['composer'].casefold():
                continue
            if row['state'] in ('failed', 'blocked') and not (retry or refresh):
                continue
            parsed = json.loads(row['parsed']) if row['parsed'] else None
            needs_parse = parsed is None or refresh
            work_id = row['id']
            if needs_parse:
                processed += 1
                try:
                    parsed = parse_work(self.http.text(catalog['url']), catalog['url'])
                    with self.db:
                        self.db.execute("UPDATE works SET parsed=?,state='parsed',error=NULL WHERE id=?", (packed(parsed), work_id))
                        for asset in parsed['assets']:
                            self.db.execute('INSERT INTO assets(work_id,id,data) VALUES(?,?,?) ON CONFLICT(work_id,id) DO UPDATE SET data=excluded.data', (work_id, asset['id'], packed(asset)))
                except (ValueError, RuntimeError, OSError) as exc:
                    state = 'blocked' if isinstance(exc, AccessBlocked) else 'failed'
                    with self.db:
                        self.db.execute('UPDATE works SET state=?,error=? WHERE id=?', (state, str(exc), work_id))
                    print(packed({'event': 'work_error', 'work_id': work_id, 'state': state, 'error': str(exc)}), flush=True)
                    continue
            self._manifest(work_id, catalog, parsed)
            if instrument.casefold() not in parsed['information'].get('Instrumentation', '').casefold():
                continue
            kinds = {asset['kind'] for asset in parsed['assets']}
            if require_both and not {'audio', 'scores'} <= kinds:
                continue
            if metadata_only:
                continue
            pending = []
            active_ids = {a['id'] for a in parsed['assets']}
            for asset in self.db.execute('SELECT * FROM assets WHERE work_id=? ORDER BY rowid', (work_id,)):
                if asset['id'] not in active_ids:
                    continue
                if asset['state'] == 'downloaded':
                    path = self.safe(asset['path'])
                    if path.is_file() and path.stat().st_size == asset['bytes'] and file_hash(path) == asset['sha256']:
                        continue
                elif asset['state'] in ('blocked', 'failed') and not retry:
                    continue
                pending.append(asset)
            if not pending:
                continue
            if not needs_parse:
                processed += 1
            for row_asset in pending:
                if downloaded >= max_files:
                    break
                downloaded += 1
                asset = json.loads(row_asset['data'])
                relative = f"imslp-{work_id}/{asset['kind']}/IMSLP{asset['id']}{asset['extension']}"
                target = self.safe(relative)
                self.safe(relative + '.part')
                try:
                    result = self.http.download(asset, target)
                    # Identical versions in one work share the first stored file.
                    previous = self.db.execute("SELECT path FROM assets WHERE work_id=? AND state='downloaded' AND sha256=? AND id<>?", (work_id, result['sha256'], asset['id'])).fetchone()
                    if previous and previous['path'] != relative:
                        old = self.safe(previous['path'])
                        if old.is_file() and file_hash(old) == result['sha256']:
                            target.unlink(missing_ok=True)
                            relative = previous['path']
                    with self.db:
                        self.db.execute("UPDATE assets SET state='downloaded',path=?,sha256=?,bytes=?,error=NULL WHERE work_id=? AND id=?", (relative, result['sha256'], result['bytes'], work_id, asset['id']))
                    state = 'downloaded'
                except (ValueError, RuntimeError, OSError) as exc:
                    state = 'blocked' if isinstance(exc, AccessBlocked) else 'failed'
                    with self.db:
                        self.db.execute('UPDATE assets SET state=?,error=? WHERE work_id=? AND id=?', (state, str(exc), work_id, asset['id']))
                self._manifest(work_id, catalog, parsed)
                print(packed({'event': 'asset', 'work_id': work_id, 'asset_id': asset['id'], 'state': state}), flush=True)
            if downloaded >= max_files:
                break
        return self.status()

    def status(self):
        return {'root': str(self.root), 'cursor': self.state('cursor', 0),
                'catalog_exhausted': self.state('exhausted', False),
                'works': {r[0]: r[1] for r in self.db.execute('SELECT state,count(*) FROM works GROUP BY state')},
                'assets': {r[0]: r[1] for r in self.db.execute('SELECT state,count(*) FROM assets GROUP BY state')}}


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be >= 1')
    return number


def main():
    parser = argparse.ArgumentParser(description='自动发现 IMSLP 作品并采集到本地音乐数据工作台；不需要作品链接。')
    parser.add_argument('command', choices=['run', 'discover', 'collect', 'status'])
    parser.add_argument('--root', default='data/imslp')
    parser.add_argument('--pages', type=positive, default=1, help='每次最多获取的目录页数，每页 1000 部作品')
    parser.add_argument('--max-works', type=positive, default=10)
    parser.add_argument('--max-files', type=positive, default=20, help='每次最多尝试的文件数')
    parser.add_argument('--composer', default='', help='作曲家名称子串，使用网站原文')
    parser.add_argument('--instrument', default='', help='作品 Instrumentation 子串，如 piano')
    parser.add_argument('--require-both', action='store_true')
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--retry', action='store_true', help='重试之前受限或失败的项目')
    parser.add_argument('--refresh', action='store_true', help='重新遍历目录/解析作品，保留下载记录')
    parser.add_argument('--delay', type=positive, default=2)
    parser.add_argument('--max-mb', type=positive, default=200)
    parser.add_argument('--cookies', type=Path, help='本机 Netscape cookies 文件，可选；不会写入采集输出')
    parser.add_argument('--respect-robots', action='store_true', help='可选：按 robots.txt 的路径规则限制抓取')
    args = parser.parse_args()
    collector = None
    try:
        http = HTTP(args.delay, args.cookies, args.max_mb, respect_robots=args.respect_robots)
        collector = Collector(args.root, http)
        # A single writer protects queue cursor and atomic-file transitions across processes.
        lock_path = collector.safe('.imslp/collector.lock')
        from imslp_lock import run_lock
        with run_lock(lock_path):
            if args.command in ('run', 'discover'):
                collector.discover(args.pages, args.refresh)
            if args.command in ('run', 'collect'):
                collector.collect(args.max_works, args.composer, args.instrument, args.require_both,
                                  args.retry, args.refresh, args.metadata_only, args.max_files)
            status = collector.status()
            print(json.dumps(status, ensure_ascii=False, indent=2))
            incomplete = any(status[table].get(state, 0) for table in ('works', 'assets') for state in ('blocked', 'failed'))
            return 2 if incomplete and args.command != 'status' else 0
    except KeyboardInterrupt:
        print('采集已中断；再次运行相同命令继续。', file=sys.stderr)
        return 130
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(f'采集未完成：{exc}', file=sys.stderr)
        return 1
    finally:
        if collector:
            collector.close()


if __name__ == '__main__':
    raise SystemExit(main())
