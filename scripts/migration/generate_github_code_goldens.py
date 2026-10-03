#!/usr/bin/env python3
"""Strict synthetic GitHub code request/response oracle, never a real token."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from katala_web_research.providers import GitHubCodeSearch
from katala_web_research.http import HttpResponse,FetchError
ROOT=Path(__file__).resolve().parents[2];cases=[]
def item(n):
    return {'html_url':f'https://github.com/fixture/repo/blob/main/src/file{n}.rs','path':f'src/日本語{n}.rs','name':f'file{n}.rs','repository':{'full_name':'fixture/repo','html_url':'https://github.com/fixture/repo','description':'alpha implementation','language':'Rust'},'text_matches':[{'object_type':'FileContent','property':'content','fragment':'alpha 日本語 &amp; text\nmore'},None,{'object_type':'FileContent','property':'content','fragment':'second alpha'}, {'object_type':'Repository','property':'content','fragment':'ignored'}]}
def add(name,limit=10,token='public-fixture-key',bodies=None,query='alpha 日本語 + * ~'):
    bodies=bodies if bodies is not None else [{'items':[item(i) for i in range(100)]}];steps=[]
    def fetch(url,**kwargs):
        index=len(steps)
        if index>=len(bodies):raise AssertionError('unscripted reference request')
        body=bodies[index];step={'request':{'url':url,'headers':kwargs.get('headers',{})}}
        if isinstance(body,tuple):
            step['error_kind']=body[0];steps.append(step)
            if body[0]=='FetchError':step['status']=body[1];raise FetchError(f'HTTP {body[1]} public fixture error')
            if body[0]=='TimeoutError':raise TimeoutError('public fixture timeout')
            raise AssertionError('unknown scripted error')
        text=body if isinstance(body,str) else json.dumps(body,ensure_ascii=False);step['text']=text;steps.append(step)
        return HttpResponse(url,200,{'content-type':'application/json; charset=utf-8'},text.encode())
    with patch.dict(os.environ,{'GITHUB_TOKEN':token},clear=True),patch('katala_web_research.providers.fetch_url',side_effect=fetch):
        try:expected={'results':[r.to_dict() for r in GitHubCodeSearch().search(query,limit=limit)]}
        except Exception as e:expected={'error_kind':type(e).__name__}
    assert expected.get('error_kind')!='AssertionError',(name,'fixture incomplete')
    cases.append({'name':name,'token':token,'query':query,'limit':limit,'steps':steps,'expected':expected})
for limit in [-1,0,1,5,101,1001]:add('limit-'+str(limit),limit,bodies=[{'items':[item(p*100+i) for i in range(100)]} for p in range(10)])
for token in ['', ' \u001c ', ' \u001cpublic-fixture-key \t']:add('token-'+str(len(token)),token=token)
for name,body in [('empty',{'items':[]}),('missing',{}),('null-items',{'items':None}),('root-list',[]),('root-null',None),('root-number',1),('non-json','public-fixture-key not JSON')]:add(name,bodies=[body])
for status in [401,403,422,503]:add('status-'+str(status),bodies=[('FetchError',status)])
add('timeout',bodies=[('TimeoutError',)])
for name,last in [('empty',{'items':[]}),('invalid-query',('FetchError',422)),('status-failure',('FetchError',503)),('json-failure','public-fixture-key not JSON')]:add('later-'+name,limit=101,bodies=[{'items':[item(i) for i in range(100)]},last])
add('fragment-limit',bodies=[{'items':[dict(item(0),text_matches=[{'object_type':'FileContent','property':'content','fragment':'alpha 日本語 '+('💡'*500)} for _ in range(5)])]}])
add('nullable-fields',bodies=[{'items':[dict(item(0),repository=None,path=None,name=None,text_matches=None),{'html_url':'https://fixture.test/code','name':'alpha.rs','repository':{'description':None,'language':None,'full_name':None,'html_url':None}}]}])
add('scalar-path-and-fragment',bodies=[{'items':[dict(item(0),path=123,text_matches=[{'object_type':'FileContent','property':'content','fragment':True}])]}])
add('dedup-and-retraction',bodies=[{'items':[item(0),dict(item(0),html_url=item(0)['html_url']+'?duplicate=1'),dict(item(2),text_matches=[{'object_type':'FileContent','property':'content','fragment':'retracted=true'}]),item(3)]}])
(ROOT/'rust/tests/fixtures/github-code-golden.json').write_text(json.dumps({'baseline':'e66e449cc210bd80ecb25a00391091e72abd9c2b','cases':cases},ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print('GitHub code oracles',len(cases))
