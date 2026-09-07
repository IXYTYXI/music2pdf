"""Inventory and work-level splits; never infer note labels from a PDF."""
import hashlib
import json
import math
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

AUDIO = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.aiff', '.aif'}
SCORES = {'.pdf', '.musicxml', '.xml', '.mxl', '.mid', '.midi', '.mscz', '.mscx'}
SPLITS = ('train', 'validation', 'test')


def scan_dataset(root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('数据根目录不存在，请先创建目录或检查路径。')
    works, warnings = [], []
    for folder in sorted(root.iterdir(), key=lambda p: p.name):
        if folder.name.startswith('.') or folder.is_symlink() or not folder.is_dir():
            continue
        assets = {'audio': [], 'scores': []}
        for kind, extensions in [('audio', AUDIO), ('scores', SCORES)]:
            directory = folder / kind
            if not directory.is_dir() or directory.is_symlink():
                continue
            for path in sorted(directory.rglob('*')):
                if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root):
                    warnings.append(f'跳过符号链接：{path.relative_to(root)}')
                    continue
                if not path.is_file() or path.suffix.lower() not in extensions:
                    continue
                try:
                    before = path.stat()
                    if before.st_size == 0:
                        warnings.append(f'跳过空文件：{path.relative_to(root)}')
                        continue
                    digest = hashlib.sha256()
                    with path.open('rb') as stream:
                        while block := stream.read(1024 * 1024):
                            digest.update(block)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError('扫描期间文件有变化，请等待复制完成再扫描。')
                    assets[kind].append({'path': path.relative_to(root).as_posix(), 'bytes': after.st_size,
                                         'sha256': digest.hexdigest(), 'format': path.suffix.lower()[1:]})
                except OSError as exc:
                    raise ValueError(f'无法读取文件 {path.relative_to(root)}：{exc}') from exc
        eligible = bool(assets['audio'] and assets['scores'])
        works.append({'id': folder.name, **assets, 'eligible': eligible, 'training_ready': False,
                      'label_status': 'unverified_unaligned',
                      'reason': '待校验版本、识谱与对齐' if eligible else '缺少录音或乐谱'})
    # Identical content in differently named work folders must never cross a split.
    parents = {w['id']: w['id'] for w in works}
    def find(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key
    seen = {}
    for work in works:
        for asset in work['audio'] + work['scores']:
            previous = seen.setdefault(asset['sha256'], work['id'])
            a, b = find(previous), find(work['id'])
            if a != b:
                parents[max(a, b)] = min(a, b)
                warnings.append(f'跨作品存在相同文件，划分时绑定：{previous} / {work["id"]}')
    for work in works:
        work['group_id'] = find(work['id'])
    fingerprint = hashlib.sha256(json.dumps(works, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {'root': str(root), 'works': works, 'warnings': warnings, 'fingerprint': fingerprint,
            'eligible_count': sum(w['eligible'] for w in works),
            'group_count': len({w['group_id'] for w in works if w['eligible']}),
            'audio_count': sum(len(w['audio']) for w in works),
            'score_count': sum(len(w['scores']) for w in works)}


def split_dataset(scan, ratios, seed):
    if len(ratios) != 3 or any(not isinstance(x, int) or x <= 0 for x in ratios) or sum(ratios) != 100:
        raise ValueError('三组比例都必须是正整数，合计 100%。')
    if not isinstance(seed, int):
        raise ValueError('随机种子必须是整数。')
    groups = {}
    for work in scan['works']:
        if work['eligible']:
            groups.setdefault(work['group_id'], []).append(work)
    keys = sorted(groups)
    if len(keys) < 3:
        raise ValueError('至少需要 3 个独立作品组才能划分三套非空数据；不同录音版本不算独立作品。')
    random.Random(seed).shuffle(keys)
    raw = [len(keys) * r / 100 for r in ratios]
    counts = [math.floor(x) for x in raw]
    for i in sorted(range(3), key=lambda i: (-(raw[i] - counts[i]), i))[:len(keys) - sum(counts)]:
        counts[i] += 1
    for i in range(3):
        if counts[i] == 0:
            donor = max(range(3), key=lambda j: counts[j])
            counts[donor] -= 1
            counts[i] += 1
    result, cursor = {}, 0
    for name, count in zip(SPLITS, counts):
        result[name] = [work for key in keys[cursor:cursor + count] for work in groups[key]]
        cursor += count
    return result


def export_dataset(root, ratios, seed, fingerprint):
    scan = scan_dataset(root)
    if fingerprint != scan['fingerprint']:
        raise ValueError('文件已变化，请重新扫描并预览划分后再导出。')
    parts = split_dataset(scan, ratios, seed)
    base = Path(scan['root']) / '.music2pdf'
    if base.is_symlink() or (base / 'splits').is_symlink():
        raise ValueError('导出目录不能是符号链接。')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    directory = base / 'splits' / stamp
    directory.mkdir(parents=True, exist_ok=False)
    for name, works in parts.items():
        (directory / f'{name}.jsonl').write_text(''.join(json.dumps(w, ensure_ascii=False) + '\n' for w in works), encoding='utf-8')
    (directory / 'excluded.jsonl').write_text(''.join(json.dumps(w, ensure_ascii=False) + '\n' for w in scan['works'] if not w['eligible']), encoding='utf-8')
    report = {'schema_version': 1, 'algorithm': 'work-content-groups-v1', 'root': scan['root'],
              'seed': seed, 'ratios': ratios, 'fingerprint': fingerprint, 'directory': str(directory),
              'counts': {name: len(works) for name, works in parts.items()},
              'warnings': scan['warnings'], 'training_ready': False,
              'note': '每行是一部作品及其版本文件清单，不是对齐的音频-音符训练样本。相对路径以 root 为基准。'}
    (directory / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
