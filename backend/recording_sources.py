"""Bounded discovery through official Internet Archive and Commons JSON APIs."""
import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode, urlsplit, urljoin, unquote
from bs4 import BeautifulSoup
from imslp_catalog import AUDIO
from imslp_http import HTTP, AccessBlocked

MAX_ITEMS = 20
MAX_CANDIDATES = 100

class RecordingHTTP(HTTP):
    def __init__(self, delay=2, max_mb=200, respect_robots=False):
        super().__init__(delay=delay, max_mb=max_mb, respect_robots=respect_robots)
        self.session.headers['User-Agent'] = 'Music2PDFRecordingDiscovery/0.1 (official Archive and Wikimedia APIs; public audio research)'

    def validate_url(self, url):
        try:
            p = urlsplit(url)
            host = p.hostname or ''
            allowed = host == 'archive.org' or host.endswith('.archive.org') or host in ('commons.wikimedia.org', 'upload.wikimedia.org')
            if p.scheme != 'https' or not allowed or p.username is not None or p.password is not None or p.port is not None or '\\' in url or any(ord(c) < 33 for c in url):
                raise ValueError()
        except (ValueError, TypeError):
            raise AccessBlocked('Unapproved recording destination') from None

    def get(self, url):
        # Validate every redirect before requesting it; never upgrade an unsafe URL.
        for _ in range(8):
            response = self._raw(url, self.permitted(url))
            if response.is_redirect:
                location = response.headers.get('Location')
                response.close()
                if not location: raise ValueError('Missing redirect destination')
                url = urljoin(url, location)
                continue
            if response.status_code != 200:
                code = response.status_code
                response.close()
                if code in (401, 403): raise AccessBlocked('Recording requires permission or login')
                raise RuntimeError(f'HTTP {code}')
            return response
        raise ValueError('Too many recording redirects')

    def download(self, asset, path):
        if asset.get('access') != 'downloadable' or asset.get('license', {}).get('download_allowed') is not True:
            raise AccessBlocked('Recording has no explicit download permission')
        if asset.get('extension') not in AUDIO: raise ValueError('Unsupported recording format')
        with self.get(asset['url']) as response:
            if 'html' in response.headers.get('Content-Type', '').lower():
                raise AccessBlocked('Recording returned an interactive landing page')
            return self._save(response, path, asset['extension'])

def _text(value):
    if value is None: return ''
    if isinstance(value, list): return '; '.join(_text(v) for v in value)
    if not isinstance(value, (str, int, float)): raise ValueError('Invalid textual metadata')
    return BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True) if '<' in str(value) else str(value).strip()

def _license(url='', label='', raw=None, commons=False):
    url = url.strip() if isinstance(url, str) else ''
    label = _text(label)
    allowed = bool(re.fullmatch(r'https?://creativecommons\.org/(?:licenses/(?:by|by-sa|by-nd|by-nc|by-nc-sa|by-nc-nd)/(?:1\.0|2\.0|2\.5|3\.0|4\.0)(?:/[a-z]{2})?|publicdomain/(?:zero|mark)/1\.0)/?', url))
    allowed = allowed or (commons and not url and label.strip().casefold() == 'public domain')
    return {'url':url,'label':label,'raw':raw,'download_allowed':allowed}

def _limit(limit):
    if not isinstance(limit,int) or isinstance(limit,bool) or limit < 1: raise ValueError('Search limit must be positive')
    return min(limit,MAX_ITEMS)

def _candidate(provider, title, context, composer, performer, description, url, source, extension, license, restricted, raw):
    RecordingHTTP.validate_url(None,url)
    RecordingHTTP.validate_url(None,source)
    return {'id':provider + ':' + hashlib.sha256(url.encode()).hexdigest()[:24], 'provider':provider,'title':_text(title),'context_title':_text(context),'composer':_text(composer),'performer':_text(performer),'description':_text(description),'url':url,'source_url':source,'extension':extension,'license':license,'access':'restricted' if restricted else ('downloadable' if license['download_allowed'] else 'reference_only'),'raw':raw}

def _truth(value):
    # Metadata values can be repeated arrays. Unknown supplied flags fail closed.
    if isinstance(value, list):
        return any(_truth(part) for part in value)
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().casefold() not in ('', 'false', '0', 'no')
    if isinstance(value, (int, float)):
        return value != 0
    return True

class ArchiveSource:
    def __init__(self,http): self.http=http
    def search(self,query,limit):
        limit=_limit(limit)
        terms=re.findall(r'\w+',query,flags=re.UNICODE)
        if not terms: raise ValueError('Empty search query')
        q='mediatype:audio AND ' + ' AND '.join('"'+term+'"' for term in terms)
        payload=self.http.json('https://archive.org/advancedsearch.php?'+urlencode({'q':q,'fl[]':'identifier','rows':limit,'page':1,'output':'json'}))
        response=payload.get('response') if isinstance(payload,dict) else None
        if not isinstance(response,dict) or not isinstance(response.get('docs'),list) or not isinstance(response.get('numFound'),int) or response['numFound'] < 0: raise ValueError('Invalid Archive search response')
        docs=response['docs']
        if response['numFound'] > 0 and not docs:
            raise ValueError('Archive result count contradicts empty first page')
        candidates=[]; truncated=response['numFound']>min(len(docs),limit)
        for doc in docs[:limit]:
            if not isinstance(doc,dict) or not isinstance(doc.get('identifier'),str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',doc['identifier']): raise ValueError('Invalid Archive identifier')
            identifier=doc['identifier']
            data=self.http.json('https://archive.org/metadata/'+quote(identifier,safe=''))
            if not isinstance(data,dict) or 'error' in data or not isinstance(data.get('metadata'),dict) or not isinstance(data.get('files'),list): raise ValueError('Invalid Archive metadata response')
            meta=data['metadata']
            restricted=any(_truth(obj.get(k)) for obj in (data,meta) for k in ('is_dark','is_restricted','access-restricted-item','nodownload','is_lending_required','lending_enabled','is_borrowable')) or any(x in _text(meta.get('collection')).split('; ') for x in ('inlibrary','printdisabled','borrowable'))
            for file in data['files']:
                if not isinstance(file,dict) or not isinstance(file.get('name'),str): raise ValueError('Invalid Archive file metadata')
                name=file['name']; ext=PurePosixPath(name).suffix.lower()
                if ext not in AUDIO: continue
                if len(candidates)>=MAX_CANDIDATES: truncated=True; break
                lic=_license(file.get('licenseurl',meta.get('licenseurl','')),raw={'licenseurl':file.get('licenseurl',meta.get('licenseurl','')),'rights':meta.get('rights')})
                candidates.append(_candidate('archive',file.get('title') or name,meta.get('title',''),file.get('composer',meta.get('composer','')),file.get('performer',meta.get('performer','')),file.get('description',meta.get('description','')),'https://archive.org/download/'+quote(identifier,safe='')+'/'+quote(name,safe='/'),'https://archive.org/details/'+quote(identifier,safe=''),ext,lic,restricted or _truth(file.get('private')),{'item_metadata':meta,'file':file,'item_access':{k:data[k] for k in ('is_dark','is_restricted') if k in data}}))
            if len(candidates)>=MAX_CANDIDATES:
                truncated = truncated or doc is not docs[min(len(docs),limit)-1]
                break
        return {'candidates':candidates,'truncated':truncated or len(docs)>limit}

class CommonsSource:
    def __init__(self,http):self.http=http
    def search(self,query,limit):
        limit=_limit(limit)
        terms=re.findall(r'\w+',query,flags=re.UNICODE)
        if not terms: raise ValueError('Empty search query')
        params={'action':'query','format':'json','formatversion':2,'generator':'search','gsrsearch':' '.join('"'+t+'"' for t in terms)+' filetype:audio','gsrnamespace':6,'gsrlimit':limit,'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iilimit':1}
        payload=self.http.json('https://commons.wikimedia.org/w/api.php?'+urlencode(params))
        if not isinstance(payload,dict) or 'error' in payload: raise ValueError('Invalid Commons response')
        if 'query' not in payload:
            if payload.get('batchcomplete') is True and 'continue' not in payload:return {'candidates':[],'truncated':False}
            raise ValueError('Missing Commons query')
        query_data=payload['query']
        if not isinstance(query_data,dict) or not isinstance(query_data.get('pages'),list):raise ValueError('Invalid Commons pages')
        pages=query_data['pages']; candidates=[]
        for page in pages[:limit]:
            if not isinstance(page,dict) or page.get('ns')!=6 or not isinstance(page.get('title'),str) or not isinstance(page.get('imageinfo'),list) or len(page['imageinfo'])!=1:raise ValueError('Invalid Commons file page')
            info=page['imageinfo'][0]
            if not isinstance(info,dict) or not isinstance(info.get('url'),str) or not isinstance(info.get('mime'),str) or not isinstance(info.get('size'),int) or not isinstance(info.get('extmetadata'),dict):raise ValueError('Invalid Commons imageinfo')
            metadata=info['extmetadata']
            if any(not isinstance(v,dict) or 'value' not in v for v in metadata.values()):raise ValueError('Invalid Commons extended metadata')
            def value(key):return metadata.get(key,{}).get('value','')
            ext=PurePosixPath(unquote(urlsplit(info['url']).path)).suffix.lower()
            if ext not in AUDIO or not (info['mime'].startswith('audio/') or info['mime']=='application/ogg'):continue
            lic=_license(value('LicenseUrl'),value('LicenseShortName'),raw=metadata,commons=True)
            candidates.append(_candidate('commons',page['title'].removeprefix('File:'),'',value('Composer'),value('Performer'),value('ImageDescription'),info['url'],'https://commons.wikimedia.org/wiki/'+quote(page['title'].replace(' ','_'),safe=':'),ext,lic,False,{'page':page}))
        return {'candidates':candidates,'truncated':'continue' in payload or len(pages)>limit}

SOURCES={'archive':ArchiveSource,'commons':CommonsSource}
