#!/usr/bin/env python3
"""Per-provider reference traces with patched HTTP and synthetic config only."""
import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch
from katala_web_research.http import FetchError,HttpResponse
from katala_web_research.providers import SearxngSearch,BraveSearch,JinaSearch

ROOT=Path(__file__).resolve().parents[2]
PROVIDERS={'searxng':SearxngSearch,'brave':BraveSearch,'jina':JinaSearch}
BASE={'searxng':{'KWR_SEARXNG_URL':'http://fixture.test///'},'brave':{'BRAVE_SEARCH_API_KEY':'public-fixture-key'},'jina':{'JINA_API_KEY':'public-fixture-key'}}
class FixedDate(date):
    @classmethod
    def today(cls):return cls(2026,1,1)
def payload(provider,items):
    if provider=='searxng':return {'results':items}
    if provider=='brave':return {'web':{'results':items}}
    return {'data':items}
def item(provider,n):
    value={'url':f'https://fixture{n}.test/item','title':f'alpha 日本語 {n}'}
    if provider=='searxng':value.update(content='alpha 内容 & text',publishedDate='2026-02-01')
    elif provider=='brave':value.update(description='alpha 内容 & text',age='2025-03-01')
    else:value.update(description='alpha 内容 & text',publishedTime='2026-02-01')
    return value
cases=[]
def add(provider,name,limit=10,env=None,bodies=None,query='alpha 日本語 + * ~'):
    values=dict(BASE[provider]);values.update(env or {})
    bodies=bodies if bodies is not None else [payload(provider,[item(provider,i) for i in range(20)])]
    steps=[]
    def fetch(url,**kwargs):
        index=len(steps)
        if index>=len(bodies):raise AssertionError('unscripted reference fetch')
        body=bodies[index]
        step={'request':{'url':url,'headers':kwargs.get('headers',{})}}
        if isinstance(body,tuple):
            step['error_kind']=body[0];steps.append(step)
            if body[0]=='FetchError':raise FetchError('public fixture error')
            if body[0]=='TimeoutError':raise TimeoutError('public fixture timeout')
            raise ValueError('unsupported synthetic error kind')
        text=body if isinstance(body,str) else json.dumps(body,ensure_ascii=False)
        step['text']=text;steps.append(step)
        return HttpResponse(url,200,{'content-type':'application/json; charset=utf-8'},text.encode())
    with patch.dict(os.environ,values,clear=True),patch('katala_web_research.source_quality.date',FixedDate),patch('katala_web_research.providers.fetch_url',side_effect=fetch):
        try:expected={'results':[r.to_dict() for r in PROVIDERS[provider]().search(query,limit=limit)]}
        except Exception as e:expected={'error_kind':type(e).__name__}
    if expected.get('error_kind')=='AssertionError':raise AssertionError((provider,name,'reference fixture incomplete'))
    cases.append({'provider':provider,'name':name,'query':query,'limit':limit,'year':2026,'env':values,'steps':steps,'expected':expected})
for provider in PROVIDERS:
    for limit in [-2,-1,0,1,5,21,41]:
        pages=[payload(provider,[item(provider,p*20+i) for i in range(20)]) for p in range(3)]
        add(provider,'limit-'+str(limit),limit,bodies=pages)
    add(provider,'empty',bodies=[payload(provider,[])])
    add(provider,'missing-fields',bodies=[{}])
    add(provider,'nullable-fields',bodies=[payload(provider,[{'url':'https://fixture.test/null','title':None},{'url':'https://fixture.test/blank','title':'','content':None,'description':None,'publishedDate':None,'age':None,'publishedTime':None,'published_at':None}])])
    duplicate=[item(provider,0),dict(item(provider,0),url='https://fixture0.test/item?dup=1'),dict(item(provider,2),**{'content':'retracted=true','description':'retracted=true'}),item(provider,3)]
    add(provider,'gates-and-dedup',bodies=[payload(provider,duplicate)])
    add(provider,'html-waf-no-body-reflection',bodies=['<html>public-fixture-key public fixture body</html>'])
    add(provider,'non-object',bodies=[[]])
    add(provider,'root-null',bodies=[None])
    add(provider,'fetch-failure',bodies=[('FetchError',)])
    add(provider,'timeout-failure',bodies=[('TimeoutError',)])
    key={'searxng':'KWR_SEARXNG_URL','brave':'BRAVE_SEARCH_API_KEY','jina':'JINA_API_KEY'}[provider]
    add(provider,'missing-config',env={key:''})
    add(provider,'missing-config-even-zero',limit=0,env={key:''})
    if provider!='jina':
        add(provider,'empty-second-page',limit=41,bodies=[payload(provider,[item(provider,i) for i in range(20)]),payload(provider,[])])
        add(provider,'later-fetch-failure',limit=41,bodies=[payload(provider,[item(provider,i) for i in range(20)]),('FetchError',)])
        add(provider,'later-json-failure',limit=41,bodies=[payload(provider,[item(provider,i) for i in range(20)]),'public-fixture-key not JSON'])
add('searxng','all-options',env={'KWR_SEARXNG_CATEGORIES':' general,it ','KWR_SEARXNG_ENGINES':'duckduckgo,wikipedia','KWR_SEARXNG_LANGUAGE':' ja-JP ','KWR_SEARXNG_TIME_RANGE':'month','KWR_SEARXNG_SAFESEARCH':'02'})
for key,value in [('KWR_SEARXNG_TIME_RANGE','forever'),('KWR_SEARXNG_SAFESEARCH','9'),('KWR_SEARXNG_SAFESEARCH','-1'),('KWR_SEARXNG_SAFESEARCH','bad')]:
    add('searxng','invalid-'+key+value,env={key:value})
    add('searxng','zero-ignores-'+key+value,limit=0,env={key:value})
add('searxng','auth-url-redacted-json-error',env={'KWR_SEARXNG_URL':'https://fixture-user:public-fixture-key@fixture.test/'},bodies=['not JSON'])
add('brave','all-options',env={'BRAVE_SEARCH_COUNTRY':' JP ','BRAVE_SEARCH_LANG':'ja','BRAVE_UI_LANG':'ja-JP','BRAVE_FRESHNESS':'past_week','BRAVE_SAFESEARCH':'MODERATE'})
for freshness in ['day','YEAR','pw','2025-99-99to2025-00-00']:
    add('brave','freshness-'+freshness,env={'BRAVE_FRESHNESS':freshness})
for key,value in [('BRAVE_FRESHNESS','bad'),('BRAVE_FRESHNESS','PW'),('BRAVE_SAFESEARCH','bad')]:
    add('brave','invalid-'+key+value,env={key:value})
    add('brave','zero-ignores-'+key+value,limit=0,env={key:value})
add('brave','ten-page-cap',limit=260,bodies=[payload('brave',[item('brave',p*20+i) for i in range(20)]) for p in range(10)])
add('jina','content-and-date-fallback',bodies=[payload('jina',[{'url':'https://fixture.test/jina','title':'alpha','description':'','content':'alpha 内容','publishedTime':'','published_at':'2025-03-01'}])])
(ROOT/'rust/tests/fixtures/json-provider-golden.json').write_text(json.dumps({'baseline':'e66e449cc210bd80ecb25a00391091e72abd9c2b','cases':cases},ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print('JSON provider cases',len(cases),'per provider',{p:sum(c['provider']==p for c in cases) for p in PROVIDERS})
