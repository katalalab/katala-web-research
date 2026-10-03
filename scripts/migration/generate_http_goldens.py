#!/usr/bin/env python3
"""Pure synthetic Python HTTP contract fixtures; no network or credential reads."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from urllib.request import getproxies_environment,proxy_bypass_environment
from katala_web_research.http import HttpResponse,redact_url

root=Path(__file__).resolve().parents[2]
cases=[]
for charset,body in [('utf-8','日本語 ©'.encode()+b'\xff'),('latin1',bytes(range(256))),('ascii',bytes(range(256))),('cp1252',bytes(range(256))),('utf-8-sig',b'\xef\xbb\xbf'+ '日本語'.encode()),('utf-16','日本語'.encode('utf-16')),('utf-16',b'\xfe\xff'+'日本語'.encode('utf-16-be')),('utf-16-le','日本語'.encode('utf-16')),('utf-16-be',b'\xfe\xff'+'日本語'.encode('utf-16-be')),('shift_jis','日本語'.encode('shift_jis')),('unknown-fixture','日本語'.encode())]:
    content_type='text/xml; charset='+charset
    cases.append({'content_type':content_type,'bytes':list(body),'expected':HttpResponse('fixture',200,{'content-type':content_type},body).text})
for content_type in ['text/xml; Charset=latin1','text/xml; charset="utf-8"','text/xml; charset=','text/xml']:
    body=b'\xef\xbb\xbf'+ '日本語'.encode()
    cases.append({'content_type':content_type,'bytes':list(body),'expected':HttpResponse('fixture',200,{'content-type':content_type},body).text})
proxies=[]
for values in [{},{'HTTP_PROXY':'upper','http_proxy':'lower'},{'HTTP_PROXY':'upper','http_proxy':''},{'HTTP_PROXY':'upper','REQUEST_METHOD':'GET'},{'HTTP_PROXY':'upper','http_proxy':'lower','REQUEST_METHOD':'GET'},{'HTTPS_PROXY':'secure','ALL_PROXY':'unused'},{'NO_PROXY':'upper','no_proxy':''},{'no_proxy':'.example.test,127.0.0.1:80,[::1],10.0.0.0/8'}]:
    old=os.environ.copy()
    try:
        os.environ.clear();os.environ.update(values)
        result=getproxies_environment()
        probes=[{'host':host,'port':port,'expected':proxy_bypass_environment(host+(':'+str(port) if port else ''),result)} for host,port in [('example.test',None),('sub.example.test',None),('evilexample.test',None),('127.0.0.1',80),('127.0.0.1',81),('[::1]',None),('10.1.2.3',None)]]
        proxies.append({'values':values,'http':result.get('http'),'https':result.get('https'),'no_proxy':result.get('no'),'bypass':probes})
    finally:os.environ.clear();os.environ.update(old)
redactions=[]
for value in ['https://user:fixture@example.test/path?API_KEY=marker&x=1#private-fragment','https://example.test/?access_token=marker&token=&q=a+b&x=*&y=~','http://example.test/?auth=marker&key=marker&apikey=marker&subscription_token=marker','https://example.test/?q=%E6%96%87%E6%9B%B8&q=second','https://example.test/path']:
    p=urlsplit(redact_url(value))
    redactions.append({'input':value,'expected':urlunsplit((p.scheme,p.netloc,p.path,p.query,''))})
(root/'rust/tests/fixtures/http-golden.json').write_text(json.dumps({'baseline':'e66e449cc210bd80ecb25a00391091e72abd9c2b','decode':cases,'proxies':proxies,'redact':redactions},ensure_ascii=False,indent=2,sort_keys=True)+'\n')
