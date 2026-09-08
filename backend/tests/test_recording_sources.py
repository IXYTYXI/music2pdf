import unittest
from urllib.parse import parse_qs, urlsplit
from recording_sources import RecordingHTTP, ArchiveSource, CommonsSource
from imslp_http import AccessBlocked

CC = 'https://creativecommons.org/licenses/by/4.0/'
class Fake:
    def __init__(self, *responses): self.responses, self.urls = list(responses), []
    def json(self, url): self.urls.append(url); return self.responses.pop(0)

def archive(files=None, **metadata):
    return {'metadata': {'title': 'Album', 'creator': 'An orchestra', 'licenseurl': CC, **metadata}, 'files': files if files is not None else [{'name': '01.mp3', 'title': 'Sonata'}]}
def commons(license_url=CC, label='CC BY 4.0'):
    return {'query': {'pages': [{'pageid': 1, 'ns': 6, 'title': 'File:Sonata.ogg', 'imageinfo': [{'url': 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Sonata.ogg', 'size': 20, 'mime': 'audio/ogg', 'extmetadata': {'LicenseUrl': {'value': license_url}, 'LicenseShortName': {'value': label}, 'Artist': {'value': 'Orchestra'}}}]}]}}

class SourceTests(unittest.TestCase):
    def test_hosts(self):
        http = RecordingHTTP()
        for url in ['https://archive.org/a', 'https://ia600001.us.archive.org/a', 'https://commons.wikimedia.org/a', 'https://upload.wikimedia.org/a']: http.validate_url(url)
        for url in ['http://archive.org/a','https://archive.org:443/a','https://archive.org.evil/a','https://evilarchive.org/a','https://x@archive.org/a','https://upload.wikimedia.org.evil/a']:
            with self.assertRaises(AccessBlocked): http.validate_url(url)
    def test_archive_title_composer_and_bounds(self):
        f = Fake({'response': {'numFound': 2, 'docs': [{'identifier': 'abc'}]}}, archive([{'name': f'{i}.mp3','title':'Track'} for i in range(150)]))
        result = ArchiveSource(f).search('Bach "Sonata"', 1)
        self.assertEqual(len(result['candidates']), 100)
        self.assertTrue(result['truncated'])
        row = result['candidates'][0]
        self.assertEqual((row['title'],row['context_title'],row['composer']), ('Track','Album',''))
        self.assertTrue(row['license']['download_allowed'])
        self.assertEqual(parse_qs(urlsplit(f.urls[0]).query)['rows'], ['1'])
    def test_archive_restrictions_and_licenses(self):
        for metadata in [{'access-restricted-item':'true'}, {'licenseurl':'https://example.com/creativecommons.org/licenses/by/4.0/'}, {'licenseurl':'Public domain recording'}, {'collection':['inlibrary']}]:
            f=Fake({'response':{'numFound':1,'docs':[{'identifier':'abc'}]}},archive(**metadata))
            row=ArchiveSource(f).search('x',1)['candidates'][0]
            self.assertNotEqual(row['access'],'downloadable')
    def test_commons(self):
        f=Fake(commons())
        row=CommonsSource(f).search('Sonata',10)['candidates'][0]
        self.assertEqual(row['title'],'Sonata.ogg')
        self.assertEqual(row['composer'],'')
        self.assertTrue(row['license']['download_allowed'])
        p=parse_qs(urlsplit(f.urls[0]).query)
        self.assertEqual(p['gsrnamespace'],['6'])
        self.assertIn('filetype:audio',p['gsrsearch'][0])
    def test_conservative_license(self):
        for url,label,allowed in [('', 'Public domain', True),('', 'This mentions public domain',False),('https://creativecommons.org/licenses/by/4.0/evil','CC',False)]:
            row=CommonsSource(Fake(commons(url,label))).search('x',1)['candidates'][0]
            self.assertEqual(row['license']['download_allowed'],allowed)
    def test_malformed(self):
        for source,payload in [(ArchiveSource,{}),(ArchiveSource,{'response':{'docs':[]}}),(CommonsSource,{}),(CommonsSource,{'query':{'pages':[{}]}})]:
            with self.assertRaises(ValueError):source(Fake(payload)).search('x',1)
    def test_empty_commons(self):
        self.assertEqual(CommonsSource(Fake({'batchcomplete':True})).search('x',1),{'candidates':[],'truncated':False})

class Response:
    def __init__(self, data=b'ID3audio', status=200, headers=None):
        self.data,self.status_code,self.headers=data,status,headers or {}
        self.is_redirect = status == 302
        self.closed=False
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def iter_content(self,n):yield self.data

class TransportTests(unittest.TestCase):
    def test_redirect_is_validated_before_request(self):
        http=RecordingHTTP()
        calls=[]
        response=Response(status=302,headers={'Location':'https://evil.example/file.mp3'})
        def raw(url,delay): calls.append(url);return response
        http._raw=raw
        with self.assertRaises(AccessBlocked):http.get('https://archive.org/download/test/file.mp3')
        self.assertEqual(len(calls),1)
        self.assertTrue(response.closed)
    def test_download_signature_and_rights(self):
        import tempfile
        from pathlib import Path
        http=RecordingHTTP()
        asset={'url':'https://archive.org/download/x/a.mp3','extension':'.mp3','access':'downloadable','license':{'download_allowed':True}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'a.mp3'
            http.get=lambda url:Response()
            self.assertEqual(http.download(asset,path)['bytes'],8)
            self.assertEqual(path.read_bytes(),b'ID3audio')
            path.unlink()
            http.get=lambda url:Response(b'<html>not audio')
            with self.assertRaises(ValueError):http.download(asset,path)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix('.mp3.part').exists())
            asset['access']='restricted'
            with self.assertRaises(AccessBlocked):http.download(asset,path)
    def test_metadata_errors_and_explicit_composer(self):
        source=ArchiveSource(Fake({'response':{'numFound':1,'docs':[{'identifier':'abc'}]}}, archive(composer='Bach')))
        self.assertEqual(source.search('x',1)['candidates'][0]['composer'],'Bach')
        with self.assertRaises(ValueError):
            ArchiveSource(Fake({'response':{'numFound':1,'docs':[{'identifier':'abc'}]}},[])).search('x',1)
        data=commons();data['query']['pages'][0]['imageinfo'][0]['extmetadata']['LicenseUrl']['value']='<b>'+CC+'</b>'
        self.assertFalse(CommonsSource(Fake(data)).search('x',1)['candidates'][0]['license']['download_allowed'])

class ArchiveRestrictionRegressionTests(unittest.TestCase):
    def test_restriction_flags_are_normalized(self):
        for flag in (['true'], ' true ', ['false', [' YES ']], {'unexpected': 'false'}):
            with self.subTest(flag=flag):
                http=Fake({'response':{'numFound':1,'docs':[{'identifier':'abc'}]}},archive(**{'access-restricted-item':flag}))
                row=ArchiveSource(http).search('x',1)['candidates'][0]
                self.assertEqual(row['access'],'restricted')
    def test_positive_count_with_empty_first_page_is_invalid(self):
        with self.assertRaises(ValueError):
            ArchiveSource(Fake({'response':{'numFound':1,'docs':[]}})).search('x',1)
