#!/usr/bin/env python3
"""Synthetic gh/REST reference transcripts; no subprocess/network/credential use."""
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
from katala_web_research.providers import GitHubRepoSearch
from katala_web_research.http import HttpResponse, FetchError
ROOT=Path(__file__).resolve().parents[2];cases=[]
def gh_item(n):
    return {'fullName':f'fixture/repo{n}','url':f'https://github.com/fixture/repo{n}','description':'alpha 日本語 implementation','stargazersCount':n,'updatedAt':'2026-01-02T03:04:05Z','isFork':False}
def rest_item(n):
    return {'full_name':f'fixture/repo{n}','html_url':f'https://github.com/fixture/repo{n}','name':f'repo{n}','description':'alpha 日本語 implementation','stargazers_count':n,'updated_at':'2026-01-02T03:04:05Z','fork':False,'owner':{'login':'fixture'},'language':'Rust','topics':['alpha','日本語','retrieval'],'license':{'name':' MIT ','spdx_id':'MIT'},'clone_url':f'https://github.com/fixture/repo{n}.git','homepage':'https://fixture.test/project'}
def add(name,found=False,gh=None,return_code=0,error=None,stderr='',limit=10,token='',body=None,query='alpha 日本語 + * ~'):
    process_steps=[];http_steps=[]
    def which(program):
        assert program=='gh';process_steps.append({'operation':'available','program':program,'found':found});return '/synthetic/gh' if found else None
    def run(cmd,**kwargs):
        stdout=gh if isinstance(gh,(str,bytes)) else json.dumps(gh if gh is not None else [gh_item(i) for i in range(3)],ensure_ascii=False)
        child_stderr=stderr
        step={'operation':'run','request':{'program':cmd[0],'args':cmd[1:],'timeout_ms':int(kwargs['timeout']*1000),'output_limit':8*1024*1024},'return_code':return_code,'stdout':stdout if isinstance(stdout,str) else list(stdout),'stderr':child_stderr if isinstance(child_stderr,str) else list(child_stderr)}
        process_steps.append(step)
        if error:
            step['error_kind']=error
            if error=='TimeoutExpired':raise subprocess.TimeoutExpired(cmd,kwargs['timeout'])
            if error=='FileNotFoundError':raise FileNotFoundError('synthetic missing')
            if error=='PermissionError':raise PermissionError('synthetic denied')
            raise AssertionError('unknown error')
        if isinstance(stdout,bytes):stdout=stdout.decode('utf-8')
        if isinstance(child_stderr,bytes):child_stderr=child_stderr.decode('utf-8')
        return subprocess.CompletedProcess(cmd,return_code,stdout,child_stderr)
    def fetch(url,**kwargs):
        assert not http_steps,'unexpected retry';step={'request':{'url':url,'headers':kwargs.get('headers',{})}};http_steps.append(step)
        data=body if body is not None else {'items':[rest_item(i) for i in range(3)]}
        if isinstance(data,tuple):step['status']=data[0];raise FetchError(f'HTTP {data[0]} public-fixture-key')
        text=data if isinstance(data,str) else json.dumps(data,ensure_ascii=False);step['text']=text
        return HttpResponse(url,200,{'content-type':'application/json'},text.encode())
    with patch.dict(os.environ,{'GITHUB_TOKEN':token},clear=True),patch('katala_web_research.providers.shutil.which',side_effect=which),patch('katala_web_research.providers.subprocess.run',side_effect=run),patch('katala_web_research.providers.fetch_url',side_effect=fetch):
        try:expected={'results':[r.to_dict() for r in GitHubRepoSearch().search(query,limit=limit)]}
        except Exception as e:expected={'error_kind':type(e).__name__}
    assert expected.get('error_kind') not in ['AssertionError','UnboundLocalError'],(name,'incomplete fixture')
    cases.append({'name':name,'query':query,'limit':limit,'token':token,'process_steps':process_steps,'steps':http_steps,'expected':expected})
for limit in [-1,0,1,5,31,100]:
    add('rest-limit-'+str(limit),limit=limit)
    add('gh-limit-'+str(limit),found=True,limit=limit)
for name,args in [('nonzero',{'return_code':7}),('timeout',{'error':'TimeoutExpired'}),('empty',{'gh':[]}),('empty-output',{'gh':''}),('no-urls',{'gh':[{'fullName':'ignored'}]}),('missing-race',{'error':'FileNotFoundError'}),('permission',{'error':'PermissionError'}),('malformed',{'gh':'public-fixture-key not JSON'}),('root-null',{'gh':'null'}),('root-object-empty',{'gh':{}}),('root-object',{'gh':{'foo':1}}),('bad-stdout',{'gh':b'\xff'}),('bad-stderr-nonzero',{'stderr':b'\xff','return_code':7})]:add('gh-'+name,found=True,**args)
for token in ['', 'public-fixture-key',' public-fixture-key ']:add('rest-token-'+str(len(token)),token=token)
for status in [401,403,422,503]:add('rest-status-'+str(status),body=(status,))
for name,body in [('missing',{}),('empty',{'items':[]}),('null-items',{'items':None}),('root-null','null'),('root-list',[]),('malformed','public-fixture-key not JSON')]:add('rest-'+name,body=body)
add('gh-rank-holes',found=True,gh=[{'fullName':'missing'},gh_item(1),dict(gh_item(2),url=gh_item(1)['url']+'?duplicate=1'),gh_item(3)])
add('gh-retracted-no-rest',found=True,gh=[dict(gh_item(0),description='retracted=true')])
add('rest-retraction-dedup',body={'items':[rest_item(0),dict(rest_item(0),html_url=rest_item(0)['html_url']+'?duplicate=1'),dict(rest_item(1),description='retracted=true'),rest_item(2)]})
add('rest-nullable',body={'items':[dict(rest_item(0),license=None,topics=None,owner=None,description=None,updated_at=None,stargazers_count=None)]})
add('rest-topics-six-fork',body={'items':[dict(rest_item(0),topics=list('abcdefgh日本語'),fork=True)]})
add('rest-license-noassertion',body={'items':[dict(rest_item(0),license={'spdx_id':' NOASSERTION ','name':''})]})
add('rest-license-spdx',body={'items':[dict(rest_item(0),license={'spdx_id':' Apache-2.0 '})]})
add('rest-topics-string',body={'items':[dict(rest_item(0),topics='alpha日本語') ]})
add('rest-stars-zero',body={'items':[dict(rest_item(0),stargazers_count=0)]})
for name,rows in [('duplicate',[rest_item(0),dict(rest_item(0),updated_at='²⁰²⁶')]),('retracted',[rest_item(0),dict(rest_item(1),updated_at='²⁰²⁶',description='retracted=true')]),('empty-url',[rest_item(0),dict(rest_item(1),updated_at='²⁰²⁶',html_url='')]),('surviving',[rest_item(0),dict(rest_item(1),updated_at='²⁰²⁶')])]:add('rest-year-'+name,body={'items':rows})
path=ROOT/'rust/tests/fixtures/github-repo-golden.json';path.write_text(json.dumps({'baseline':'e66e449cc210bd80ecb25a00391091e72abd9c2b','cases':cases},ensure_ascii=False,indent=2,sort_keys=True)+'\n');print('GitHub repository oracles',len(cases))
