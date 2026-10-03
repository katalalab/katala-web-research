#!/usr/bin/env python3
"""Direct raw-response oracles from Python; no network/archive/credentials."""
import json
from pathlib import Path
from unittest.mock import patch
from katala_web_research.http import HttpResponse,FetchError
from katala_web_research.reader import read_url
ROOT=Path(__file__).resolve().parents[2];cases=[]
def add(name,body=b'',headers=None,url='https://example.test/input',returned=None,status=200,error=None):
    requests=[]
    def fetch(target,**kwargs):
        requests.append({'url':target,'headers':kwargs.get('headers',{})})
        if error:raise type(error,(FetchError,),{})('synthetic') if error=='FetchError' else type(error,(Exception,),{})('synthetic')
        return HttpResponse(returned or url,status,headers or {},body)
    with patch('katala_web_research.reader.fetch_url',fetch),patch('katala_web_research.reader.utc_now_iso',lambda:'2026-01-01T00:00:00+00:00'):
        try: expected={'page':read_url(url,reader='direct').to_dict()}
        except Exception as exc: expected={'error_kind':type(exc).__name__}
    cases.append(dict(name=name,url=url,body=list(body),headers=headers or {},returned=returned or url,status=status,error=error,requests=requests,expected=expected))
for name,text in [('empty',''),('text',' \t日本語 © &amp;\nnext\x1c '),('html','<HTML><head><title> 日本語 &amp; title </title></head><body><h1>Heading</h1><div>body <b>bold</b></div><p>one<br>two</p><script>x < y</script><style>hidden</style><noscript>hide</noscript><svg><text>hide</text></svg></body></HTML>'),('no-title','<html><p>body</p></html>'),('multiple-title','<html><title>a</title><title>b</title><p>x&amp;amp;y</p></html>'),('comments','<html><!--comment--><p>visible</p></html>')]:
 for header in [{},{'content-type':'text/plain'},{'content-type':'TEXT/HTML; charset=utf-8'}]:add(name+'-'+str(len(cases)),text.encode(),header)
for charset in ['shift_jis','iso-8859-1','cp1252','utf-8','utf-16-le','ascii']:
 text='Café £' if charset in ['iso-8859-1','cp1252'] else ('ascii text' if charset=='ascii' else '日本語 text')
 add('header-'+charset,text.encode(charset),{'content-type':'text/plain; charset='+charset})
for charset,text in [('shift_jis','日本語'),('iso-8859-1','Café £'),('cp1252','€ café'),('utf-8','日本語')]:
 body=('<html><meta charset="'+charset+'"><title>'+text+'</title><p>'+text+'</p></html>').encode(charset)
 add('meta-'+charset,body,{'content-type':'text/html'})
 add('meta-suppressed-'+charset,body,{'content-type':'text/html; charset=utf-8'})
add('meta-unknown',b'<html><meta charset="unknown-fixture"><p>x</p></html>',{'content-type':'text/html'})
for pad in [4000,4096,499,500]:add('offset-'+str(pad),b'x'*pad+b'<html><meta charset=iso-8859-1><p>Caf\xe9</p></html>',{'content-type':'text/plain'})
add('header-uppercase',b'<html><title>Caf\xe9</title></html>',{'content-type':'text/html; CHARSET=iso-8859-1'})
add('redirect',b'<html><p>redirect</p></html>',{'content-type':'text/html'},returned='https://example.test/final')
add('missing-content-type',b' raw \xff bytes ')
add('non-html-binary',bytes([0,1,127,255]),{'content-type':'application/pdf'})
for url in ['','file:///tmp/example','https:/missing','example.test','//example.test','HTTP://example.test/x',' \x1chttps://example.test/x']:
 add('url-'+str(len(cases)),b'normal',url=url)
for error in ['FetchError','TimeoutError','ValueError']:add('error-'+error,error=error)
(ROOT/'rust/tests/fixtures/reader-golden.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n')
print('direct reader raw-response cases:',len(cases))
