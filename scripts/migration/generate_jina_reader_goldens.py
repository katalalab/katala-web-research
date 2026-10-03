#!/usr/bin/env python3
"""Python Jina/auto request/response/error/clock oracles, no I/O."""
import json
from pathlib import Path
from unittest.mock import patch
from katala_web_research import reader
from katala_web_research.http import HttpResponse,FetchError
ROOT=Path(__file__).resolve().parents[2];cases=[]
def add(name,content='# Heading\n日本語 body',mode='jina',url='https://example.test/a b?q=x&z=1#frag',error=None,headers=None,returned='https://r.jina.ai/final',fallback_error=None):
    steps=[];clocks=[]
    def fetch(target,**kwargs):
        is_jina=target.startswith('https://r.jina.ai/');kind=error if is_jina else fallback_error
        body=content if is_jina else '<html><title>direct title</title><p>direct evidence</p></html>'
        if kind=='FetchError':exc=FetchError('public-fixture-key error body')
        elif kind:exc=type(kind,(Exception,),{})('public-fixture-key')
        else:exc=None
        response=HttpResponse(returned if is_jina else 'https://example.test/direct-final',200,headers if headers is not None and is_jina else {'content-type':'text/plain; charset=utf-8'} if is_jina else {'content-type':'text/html'},body.encode())
        steps.append(dict(request={'url':target,'headers':kwargs.get('headers',{})},error_kind=kind,response=dict(url=response.url,status=response.status,headers=response.headers,body=list(response.body))))
        if exc:raise exc
        return response
    def clock():clocks.append(1);return '2026-01-01T00:00:00+00:00'
    with patch.object(reader,'fetch_url',fetch),patch.object(reader,'utc_now_iso',clock):
        try:expected={'page':reader.read_url(url,reader=mode).to_dict()}
        except Exception as exc:expected={'error_kind':type(exc).__name__}
    cases.append(dict(name=name,url=url,reader=mode,steps=steps,clock_calls=len(clocks),expected=expected))
for text in ['', ' \t\n\x1c ', '# Title\nbody', '\t# keep hash\nbody',' #  title # \r\nbody','##\n###\n日本語 first\u2028next', 'é'*161+'\nbody','前'*160+'more', 'line\vsecond','a\x1fb', 'line\u0085next',' &amp; <html> literal ']:add('markdown-'+str(len(cases)),text)
for url in ['https://example.test/-._~ +?#%/日本語','HTTP://example.test/',' \x1chttps://example.test/x','https://user:public-fixture-key@example.test/a?api_key=public-fixture-key','https://example.test/'+'x'*200]:
 for text in ['', '# title']:add('target-'+str(len(cases)),text,url=url)
for body in ['{broken','{"code":"sample","message":"domain content","data":[1,2]}','{"code":422,"name":"Error"}','{"name":"Error","message":null}','[1,2]','null','{"code":400,"name":"Error","message":null,"extra":NaN}','{"code":400,"name":"Error\\ud800","message":null}','{"code":400,"name":"\\u0045rror","message":null}','{"code":400,"name":"\\\\u0045rror","message":null}','{"code":400,"name":"Error","message":null,"code":3}']:
 for mode in ['jina','auto']:add('json-'+str(len(cases)),body,mode)
for code in [399,400,422,10**100,400.0,-400,'400',True,False,None,float('inf'),float('nan')]:
 for mode in ['jina','auto']:add('code-'+str(len(cases)),json.dumps({'code':code,'name':'AssertionFailureError','message':'public-fixture-key'}),mode)
for name in ['Error','prefixErrorSuffix','error','',None,400,[],{}]:add('identity-'+str(len(cases)),json.dumps({'status':400,'name':name,'readableMessage':None}))
for mode in ['jina','auto','direct','unknown']:
 for error in ['FetchError','TimeoutError','ValueError']:add('transport-'+str(len(cases)),mode=mode,error=error)
for url in ['', 'file:///tmp/owned','https:/invalid']:add('invalid-'+str(len(cases)),mode='auto',url=url)
add('fallback-error',mode='auto',error='FetchError',fallback_error='FetchError')
add('no-content-type',headers={})
(ROOT/'rust/tests/fixtures/jina-reader-golden.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n')
print('Jina/auto reference transcripts:',len(cases))
