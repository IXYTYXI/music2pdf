"""Polite sequential transport. Access restrictions become explicit queue states."""
import hashlib
import json
import http.cookiejar
import time
import secrets
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote, parse_qs
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

USER_AGENT = 'Music2PDFCollector/0.1'


class AccessBlocked(RuntimeError):
    pass


class HTTP:
    def __init__(self, delay=2, cookies=None, max_mb=200, respect_robots=False):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT
        self.delay = max(2, delay)
        self.last = 0
        self.max_bytes = max_mb * 1024 * 1024
        self.robots = {}
        self.respect_robots = respect_robots
        if cookies:
            jar = http.cookiejar.MozillaCookieJar(str(cookies))
            jar.load(ignore_discard=True, ignore_expires=False)
            # Cookie domain rules are preserved; cookies are never printed or persisted.
            self.session.cookies.update(jar)

    def validate_url(self, url):
        parts = urlsplit(url)
        host = parts.hostname or ''
        allowed = any(host == d or host.endswith('.' + d) for d in ('imslp.org', 'imslp.eu', 'imslp.us', 'petruccimusiclibrary.ca', 'petruccilibrary.ca', 'petruccilibrary.us'))
        if parts.scheme != 'https' or not allowed or parts.username or parts.password or parts.port not in (None, 443):
            raise AccessBlocked('Destination is outside the configured HTTPS mirror allowlist')

    def _raw(self, url, delay, method="GET", data=None):
        for attempt in range(3):
            time.sleep(max(0, self.last + delay - time.monotonic()))
            self.last = time.monotonic()
            try:
                request = self.session.get if method == 'GET' else self.session.post
                kwargs = {} if method == 'GET' else {'data': data}
                response = request(url, timeout=(15, 60), allow_redirects=False, stream=True, **kwargs)
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError('Network request failed after 3 attempts') from None
                time.sleep(2 ** (attempt + 1))
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                retry = response.headers.get('Retry-After', '')
                response.close()
                if attempt == 2:
                    raise RuntimeError('Server busy after 3 attempts')
                try:
                    seconds = float(retry)
                except ValueError:
                    try:
                        seconds = (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError):
                        seconds = 2 ** (attempt + 1)
                if seconds > 60:
                    raise AccessBlocked('Server requested a long Retry-After; retry in a later run')
                time.sleep(max(0, seconds))
                continue
            return response

    def permitted(self, url):
        self.validate_url(url)
        if not self.respect_robots:
            return self.delay
        parts = urlsplit(url)
        origin = f'{parts.scheme}://{parts.netloc}'
        if origin not in self.robots:
            with self._raw(origin + '/robots.txt', self.delay) as response:
                parser = RobotFileParser()
                if response.status_code == 404:
                    parser.parse([])
                elif response.status_code == 200:
                    raw = self._read(response, 1024 * 1024).decode('utf-8', errors='replace')
                    if '<html' in raw.lower():
                        raise AccessBlocked('robots.txt returned HTML; access policy unavailable')
                    parser.parse(raw.splitlines())
                else:
                    raise AccessBlocked('Unable to verify robots.txt; retry later')
                self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(USER_AGENT, url):
            raise AccessBlocked('robots.txt disallows this path (--respect-robots enabled)')
        return max(self.delay, parser.crawl_delay(USER_AGENT) or parser.crawl_delay('*') or 0)

    def get(self, url):
        for _ in range(8):
            if urlsplit(url).scheme == 'http':
                url = urlsplit(url)._replace(scheme='https').geturl()
            delay = self.permitted(url)
            response = self._raw(url, delay)
            if response.is_redirect:
                location = response.headers.get('Location', '')
                response.close()
                # HTTP headers arrive as Latin-1, while IMSLP emits UTF-8 filenames.
                try:
                    location = location.encode('latin1').decode('utf-8')
                except UnicodeError:
                    pass
                url = urljoin(url, location)
                continue
            if response.status_code in (401, 403):
                response.close()
                raise AccessBlocked('Site requires login, permission, or interactive verification')
            if response.status_code != 200:
                code = response.status_code
                response.close()
                raise RuntimeError(f'HTTP {code}')
            if urlsplit(response.url).path == '/friendlyredirect.html':
                destination = urlsplit(response.url).fragment
                with response:
                    source = self._read(response, 64 * 1024).decode('utf-8', errors='replace')
                if not destination.startswith('/wiki/') or '/friendlyredirect2.html#' not in source or 'friendlyredirect' not in source:
                    raise AccessBlocked('Unrecognized JavaScript redirect page')
                target = urljoin(response.url, destination)
                self.validate_url(target)
                bridge = urljoin(response.url, '/friendlyredirect2.html')
                with self._raw(bridge, self.permitted(bridge), method='POST', data={'friendlyredirect': str(secrets.randbelow(1000000000))}) as step:
                    script = self._read(step, 64 * 1024).decode('utf-8', errors='replace')
                    if step.status_code != 200 or "redirectPassed=1;" not in script:
                        raise AccessBlocked('JavaScript redirect step changed')
                self.session.cookies.set('redirectPassed', '1', domain=urlsplit(bridge).hostname, path='/', secure=True)
                url = target
                continue
            return response
        raise RuntimeError('Too many redirects')

    @staticmethod
    def _read(response, limit):
        parts, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > limit:
                raise ValueError('Response exceeds size limit')
            parts.append(chunk)
        return b''.join(parts)

    def text(self, url):
        with self.get(url) as response:
            return self._read(response, 8 * 1024 * 1024).decode('utf-8', errors='replace')

    def json(self, url):
        return json.loads(self.text(url))

    def download(self, asset, path):
        url = asset['url']
        for _ in range(4):
            with self.get(url) as response:
                content_type = response.headers.get('Content-Type', '').lower()
                if 'html' in content_type:
                    page = BeautifulSoup(self._read(response, 2 * 1024 * 1024), 'html.parser')
                    # Follow the site's informational disclaimer for this exact file.
                    disclaimer = page.find('a', href='/wiki/Special:IMSLPDisclaimerAccept/' + asset.get('id', ''))
                    if disclaimer and disclaimer.get_text(' ', strip=True) == 'I understand':
                        url = urljoin(response.url, disclaimer['href'])
                        continue
                    # IMSLP's non-member page reveals this same URL after its advertised wait.
                    waiting = page.select_one('#sm_dl_wait[data-id]')
                    if waiting:
                        duration = re.search(r'"js-a4"\s*:\s*"(\d+)"', str(page))
                        if not duration or not 1 <= int(duration[1]) <= 60:
                            raise AccessBlocked('Unrecognized download waiting period')
                        target = urljoin(response.url, waiting['data-id'])
                        self.validate_url(target)
                        target_parts = urlsplit(target)
                        media_path = target_parts.path
                        if media_path == '/linkhandler.php':
                            media_path = parse_qs(target_parts.query).get('path', [''])[0]
                        if Path(unquote(media_path)).suffix.lower() != asset['extension']:
                            raise AccessBlocked('Waiting page has no matching media URL')
                        time.sleep(int(duration[1]))
                        url = target
                        continue
                    # Regional mirrors show a confirmation for the path in their handler URL.
                    parts = urlsplit(response.url)
                    if parts.path == '/linkhandler.php':
                        self.validate_url(response.url)
                        media_path = parse_qs(parts.query).get('path', [''])[0]
                        expected = '/' + media_path.lstrip('/')
                        expected = expected if expected.startswith('/files/') else '/files' + expected
                        confirmations = [a for a in page.select('a[href]')
                                         if a.get_text(' ', strip=True) == 'I understand, continue'
                                         and urlsplit(urljoin(response.url, a['href'])).netloc == parts.netloc
                                         and unquote(urlsplit(urljoin(response.url, a['href'])).path) == unquote(expected)
                                         and Path(unquote(expected)).suffix.lower() == asset['extension']]
                        if len(confirmations) == 1:
                            url = urljoin(response.url, confirmations[0]['href'])
                            continue
                    # Only follow an explicit download anchor; no arbitrary JavaScript execution.
                    links = [a for a in page.select('a[href]') if Path(unquote(urlsplit(a['href']).path)).suffix.lower() == asset['extension'] and ('download' in a.get_text(' ', strip=True).lower() or a.has_attr('download'))]
                    if len(links) != 1:
                        raise AccessBlocked('Download landing page requires browser interaction or membership')
                    url = urljoin(response.url, links[0]['href'])
                    continue
                return self._save(response, path, asset['extension'])
        raise AccessBlocked('No final downloadable file found')

    def _save(self, response, path, extension):
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + '.part')
        digest, size, prefix = hashlib.sha256(), 0, b''
        try:
            with part.open('wb') as stream:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValueError('File exceeds configured --max-mb limit')
                    if len(prefix) < 1024:
                        prefix += chunk[:1024 - len(prefix)]
                    digest.update(chunk)
                    stream.write(chunk)
            if not valid_signature(prefix, extension):
                raise ValueError('File signature mismatch; rejected HTML or invalid media')
            expected = response.headers.get('Content-Length')
            if expected and not response.headers.get('Content-Encoding') and size != int(expected):
                raise ValueError('Incomplete download')
            part.replace(path)
            return {'sha256': digest.hexdigest(), 'bytes': size}
        finally:
            part.unlink(missing_ok=True)


def valid_signature(data, ext):
    if not data or b'<html' in data[:1024].lower() or b'<!doctype html' in data[:1024].lower():
        return False
    if ext == '.pdf': return data.startswith(b'%PDF-')
    if ext in ('.mxl', '.mscz'): return data.startswith(b'PK\x03\x04')
    if ext in ('.musicxml', '.mscx'): return b'<score-partwise' in data or b'<score-timewise' in data or b'<museScore' in data
    if ext in ('.mid', '.midi'): return data.startswith(b'MThd')
    if ext == '.mp3': return data.startswith(b'ID3') or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224)
    if ext == '.ogg': return data.startswith(b'OggS')
    if ext == '.flac': return data.startswith(b'fLaC')
    if ext == '.wav': return data.startswith(b'RIFF') and data[8:12] == b'WAVE'
    if ext in ('.aif', '.aiff'): return data.startswith(b'FORM') and data[8:12] in (b'AIFF', b'AIFC')
    if ext == '.m4a': return data[4:8] == b'ftyp'
    if ext == '.aac': return len(data) > 1 and data[0] == 255 and data[1] & 246 == 240
    return False
