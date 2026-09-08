"""Explainable work-level candidate ranking, never automatic score alignment."""
import re
import unicodedata
from bs4 import BeautifulSoup

CATALOG = re.compile(r'\b(op(?:us)?|bwv|hwv|rv|kv|k|d|hob)\.?\s*(\d+[a-z]?)\b', re.I)
STOP = {'the', 'a', 'an', 'in', 'for', 'by', 'no', 'number', 'file', 'mp3', 'ogg', 'flac', 'wav'}


def clean(value):
    if isinstance(value, list):
        return ' '.join(clean(v) for v in value)
    return BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)


def normalized(value):
    value = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean(value))
    value = re.sub(r'([A-Za-z])(\d)|(\d)([A-Za-z])', lambda m: ' '.join(x for x in m.groups() if x), value)
    value = unicodedata.normalize('NFKD', value).casefold()
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in value if not unicodedata.combining(c))))


def tokens(value):
    return set(normalized(value).split()) - STOP


def catalogs(text):
    text = clean(text).replace('_', ' ')
    result = set()
    for match in CATALOG.finditer(text):
        prefix, number = match.groups()
        prefix = {'opus': 'op', 'kv': 'k'}.get(prefix.lower(), prefix.lower())
        subdivision = re.match(r'\s*(?:[,;]\s*)?(?:no\.?|nr\.?|/)\s*(\d+[a-z]?)\b', text[match.end():], re.I)
        if subdivision:
            result.add(prefix + ':' + number.lower() + '/' + subdivision[1].lower())
            continue
        result.add(prefix + ':' + number.lower())
        end = re.match(r'\s*[-–]\s*(\d+)\b', text[match.end():])
        if end and number.isdigit() and 0 < int(end[1]) - int(number) <= 100:
            result.update(f'{prefix}:{n}' for n in range(int(number), int(end[1]) + 1))
    return sorted(result)


def work_identity(metadata):
    catalog = metadata.get('catalog', {})
    info = metadata.get('information', {})
    title = clean(catalog.get('title') or info.get('Work Title'))
    titles = [title] if title else []
    for key, value in info.items():
        if re.sub('[^a-z]', '', key.lower()) in ('alternativetitle', 'worktitle'):
            if clean(value) and clean(value) not in titles:
                titles.append(clean(value))
    catalog_text = ' '.join(titles) + ' ' + clean(catalog.get('catalog', {}).get('icatno'))
    catalog_text += ' ' + ' '.join(clean(v) for k, v in info.items() if 'catalogue' in k.lower() or 'opus' in k.lower())
    return {'id': str(catalog.get('id', '')), 'composer': clean(catalog.get('composer') or info.get('Composer')),
            'titles': titles, 'catalog_numbers': catalogs(catalog_text),
            'instrumentation': clean(info.get('Instrumentation')), 'movement': clean(info.get('Movement')),
            'key': clean(info.get('Key')), 'duration': clean(info.get('Average Duration Avg. Duration'))}


def surname(composer):
    return composer.split(',')[0].strip() if ',' in composer else (composer.split()[-1] if composer.split() else '')


def build_queries(identity):
    name = surname(identity['composer'])
    queries = []
    if identity['titles']:
        queries.append(f"{name} {identity['titles'][0]}".strip())
    if identity['catalog_numbers']:
        queries.append(f"{name} {identity['catalog_numbers'][0].replace(':', ' ')}".strip())
    elif len(identity['titles']) > 1:
        queries.append(f"{name} {identity['titles'][1]}".strip())
    return list(dict.fromkeys(q for q in queries if q))[:2]


def instrumentation(value):
    text = normalized(value)
    if re.search(r'(4|four) hands?', text): return 'piano_four_hands'
    if 'piano' in text and ('solo' in text or text == 'piano'): return 'piano_solo'
    if 'orchestra' in text or 'orchestral' in text: return 'orchestra'
    for instrument in ('cello', 'violin', 'flute', 'guitar'):
        if instrument in text.split(): return instrument
    return ''


def numbered_works(value):
    return set(re.findall(r'\b(symphony|sonata|suite|concerto|quartet|trio|prelude|etude)\s+(?:no\s+|nr\s+|number\s+)?(\d+)\b', normalized(value)))


def tonality(value):
    value = clean(value).replace('♯', ' sharp ').replace('#', ' sharp ').replace('♭', ' flat ')
    match = re.search(r'\b([a-g])\s*(sharp|flat)?\s*(major|minor|dur|moll)\b', normalized(value))
    return (match[1], match[2] or '', {'dur': 'major', 'moll': 'minor'}.get(match[3], match[3])) if match else None


def rank_candidate(identity, candidate):
    title = clean(candidate.get('title'))
    context = ' '.join(clean(candidate.get(k)) for k in ('context_title', 'composer', 'performer', 'description'))
    all_text = title + ' ' + context
    evidence, conflicts, missing, warnings = [], [], [], []
    score = 0
    name = tokens(surname(identity['composer']))
    if name and name <= tokens(all_text):
        score += 20
        evidence.append({'field': 'composer', 'detail': 'Composer surname appears in source text; namesakes still need review'})
    else:
        missing.append('composer')
    title_tokens = tokens(title)
    coverage = max((len(tokens(t) & title_tokens) / max(1, len(tokens(t))) for t in identity['titles']), default=0)
    if coverage >= .6:
        score += round(40 * coverage)
        evidence.append({'field': 'track_title', 'detail': f'Track-title token coverage {coverage:.2f}'})
    else:
        missing.append('track_title')
    expected = set(identity['catalog_numbers'])
    # Only track-specific identifiers count; an album may contain unrelated works.
    observed = set(catalogs(title + ' ' + clean(candidate.get('catalog_number'))))
    if expected & observed:
        score += 25
        evidence.append({'field': 'catalog', 'detail': ', '.join(sorted(expected & observed))})
    elif expected:
        shared_prefixes = {x.split(':')[0] for x in expected} & {x.split(':')[0] for x in observed}
        shared_bases = {x.split('/')[0] for x in expected} & {x.split('/')[0] for x in observed}
        underspecified = shared_bases and any('/' not in x for x in expected | observed if x.split('/')[0] in shared_bases)
        if shared_prefixes and not underspecified:
            conflicts.append({'field': 'catalog', 'detail': f'Expected {sorted(expected)}, source track has {sorted(observed)}'})
        else:
            missing.append('catalog')
    expected_numbers = set().union(*(numbered_works(t) for t in identity['titles']))
    actual_numbers = numbered_works(title)
    for kind in {x[0] for x in expected_numbers} & {x[0] for x in actual_numbers}:
        if not ({n for k, n in expected_numbers if k == kind} & {n for k, n in actual_numbers if k == kind}):
            conflicts.append({'field': 'work_number', 'detail': f'Explicit {kind} numbers differ'})
    expected_key = tonality(identity.get('key'))
    actual_key = tonality(candidate.get('key') or title)
    if expected_key and actual_key:
        if expected_key != actual_key:
            conflicts.append({'field': 'key', 'detail': f'{expected_key} vs {actual_key}'})
        else:
            evidence.append({'field': 'key', 'detail': 'Explicit key agrees'})
    elif expected_key:
        missing.append('key')
    wanted = instrumentation(identity['instrumentation'])
    found = instrumentation(candidate.get('instrumentation') or title)
    if wanted and found:
        if wanted == found:
            score += 10
            evidence.append({'field': 'instrumentation', 'detail': wanted})
        else:
            conflicts.append({'field': 'instrumentation', 'detail': f'{wanted} vs {found}; inspect arrangement and score version'})
    elif identity['instrumentation']:
        missing.append('instrumentation')
    movement = identity.get('movement')
    if movement and candidate.get('movement'):
        if normalized(movement) != normalized(candidate['movement']):
            conflicts.append({'field': 'movement', 'detail': f"{movement} vs {candidate['movement']}"})
        else:
            score += 5
            evidence.append({'field': 'movement', 'detail': movement})
    else:
        missing.append('movement_alignment')
    synthetic = bool(re.search(r'\b(midi|synthesi[sz]ed|synthesi[sz]er|virtual orchestra)\b', normalized(all_text)))
    if synthetic:
        warnings.append('synthetic_performance')
    arrangement = bool(re.search(r'\b(arrangement|transcription|arranged|transcribed)\b', normalized(title)))
    if arrangement:
        warnings.append('arrangement_or_transcription')
    tier = 'conflict' if conflicts else 'strong_candidate' if score >= 70 and 'composer' not in missing and 'track_title' not in missing and not arrangement else 'review'
    return {'score': score, 'tier': tier, 'evidence': evidence, 'conflicts': conflicts,
            'missing': missing, 'warnings': warnings, 'synthetic_hint': synthetic,
            'requires_review': True, 'training_ready': False, 'label_status': 'unverified_unaligned'}
