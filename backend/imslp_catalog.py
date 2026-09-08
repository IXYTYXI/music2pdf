"""IMSLP official catalog and public work-page adapters (no JavaScript execution)."""
import re
import hashlib
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit, unquote
from bs4 import BeautifulSoup

AUDIO = {'.mp3', '.ogg', '.wav', '.flac', '.m4a', '.aac', '.aiff', '.aif'}
SCORES = {'.pdf', '.musicxml', '.mxl', '.mid', '.midi', '.mscz', '.mscx'}


def parse_catalog(payload, start):
    meta = payload.get('metadata', {})
    if meta.get('start') != start or not isinstance(meta.get('moreresultsavailable'), bool):
        raise ValueError('Unrecognized IMSLP catalog response; cursor unchanged')
    limit = meta.get('limit')
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError('Invalid catalog page size')
    works = []
    for key, row in payload.items():
        if key == 'metadata':
            continue
        info = row.get('intvals', {})
        pageid = str(info.get('pageid', ''))
        url = row.get('permlink', '').replace('\\/', '/').replace('\\"', '"')
        if urlsplit(url).hostname != 'imslp.org' or not urlsplit(url).path.startswith('/wiki/'):
            raise ValueError(f'Invalid catalog record {key}; cursor unchanged')
        pageid = pageid if pageid.isdigit() else 'url-' + hashlib.sha256(url.encode()).hexdigest()[:24]
        works.append({'id': pageid, 'url': url, 'title': info.get('worktitle') or row['id'],
                      'composer': info.get('composer', ''), 'catalog': info})
    more = meta['moreresultsavailable']
    if more and not works:
        raise ValueError('Empty catalog page claims more results')
    return works, start + limit, more


def table_fields(node):
    fields = {}
    if node:
        for row in node.select('tr'):
            head = row.find('th', recursive=False)
            cell = row.find('td', recursive=False)
            if head and cell:
                clean = BeautifulSoup(str(cell), 'html.parser')
                for hidden in clean.select('.noanon, script, .imslpd_purchase'):
                    hidden.decompose()
                fields[head.get_text(' ', strip=True)] = clean.get_text(' ', strip=True)
    return fields


def parse_work(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    information = soup.select_one('.wi_body')
    if not information:
        raise ValueError('Work information missing (challenge, login, or changed page); retry required')
    assets = {}
    for block in soup.find_all(id=re.compile(r'^IMSLP\d+$')):
        download = block.select_one('.we_file_download')
        if not download:
            continue
        primary = download.select_one('b a[href]')
        if not primary:
            continue
        extension = ''
        for link in download.select('a[href]'):
            suffix = PurePosixPath(unquote(urlsplit(link['href']).path)).suffix.lower()
            if suffix in AUDIO | SCORES:
                extension = suffix
                break
        if not extension:
            continue
        group = block.find_parent(class_='we')
        headings = []
        for heading in block.find_all_previous(['h2', 'h3', 'h4', 'h5']):
            headings.append(heading.get_text(' ', strip=True))
            if heading.name == 'h2':
                break
        asset_id = block['id'][5:]
        assets[asset_id] = {
            'id': asset_id, 'url': urljoin(url, primary['href']),
            'title': primary.get_text(' ', strip=True), 'extension': extension,
            'kind': 'audio' if extension in AUDIO else 'scores',
            'section': list(reversed(headings)), 'metadata': table_fields(group),
            'source_page': url, 'label_status': 'unverified_unaligned',
        }
    streaming = []
    commercial = soup.select_one('#tabNaxos')
    if commercial:
        seen = set()
        for link in commercial.select('a[href]'):
            target = urljoin(url, link['href'])
            if urlsplit(target).scheme in ('http', 'https') and target not in seen:
                seen.add(target)
                streaming.append({'url': target, 'title': link.get_text(' ', strip=True), 'access': 'streaming_reference_only'})
    return {'information': table_fields(information), 'assets': list(assets.values()), 'streaming': streaming}
