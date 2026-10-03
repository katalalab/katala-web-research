#!/usr/bin/env python3
"""Synthetic OpenAlex HTTP/op transcripts; no live API, executable or vault use."""
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
from katala_web_research.providers import OpenAlexSearch,_openalex_work_id
from katala_web_research.http import HttpResponse,FetchError
ROOT=Path(__file__).resolve().parents[2];cases=[];identifiers=[]
def item(n):
    return {'id':f'https://openalex.org/W{n}','doi':f'https://doi.org/10.1/fixture{n}','display_name':f'alpha 日本語 work {n}','publication_year':2026,'publication_date':'2026-01-02','type':'article','cited_by_count':n,'is_retracted':False,'abstract_inverted_index':{'alpha':[0,3],'日本語':[1],'evidence':[2]},'primary_location':{'landing_page_url':f'https://arxiv.org/abs/fixture{n}','pdf_url':f'https://fixture.test/paper{n}.pdf','is_oa':True,'license':'cc-by','version':'publishedVersion','source':{'id':'https://openalex.org/S1','display_name':'Fixture journal','type':'journal'}},'best_oa_location':{'landing_page_url':f'https://fixture.test/best{n}','pdf_url':f'https://fixture.test/best{n}.pdf','is_oa':False,'license':'cc0','version':'submittedVersion','source':{'id':'https://openalex.org/S2','display_name':'Fixture archive','type':'repository'}},'content_urls':{'pdf':f'https://content.openalex.org/works/W{n}.pdf'},'open_access':{'is_oa':True,'oa_status':'gold'}}
def page(start=0,count=3,cursor=None):return {'results':[item(start+i) for i in range(count)],'meta':{'next_cursor':cursor}}
def add(name,limit=10,env=None,bodies=None,op=True,op_stdout=' \u001cpublic-fixture-key\r\n',op_stderr='',op_code=0,op_error=None,query='alpha 日本語 + * ~'):
    env=env or {};bodies=bodies if bodies is not None else [page()];steps=[];process_steps=[]
    def which(program):
        assert program=='op';process_steps.append({'operation':'available','program':program,'found':op});return '/synthetic/op' if op else None
    def run(cmd,**kwargs):
        step={'operation':'run','request':{'program':cmd[0],'args':cmd[1:],'timeout_ms':int(kwargs['timeout']*1000),'output_limit':8*1024*1024},'return_code':op_code,'stdout':op_stdout if isinstance(op_stdout,str) else list(op_stdout),'stderr':op_stderr if isinstance(op_stderr,str) else list(op_stderr)};process_steps.append(step)
        if op_error:
            step['error_kind']=op_error
            if op_error=='TimeoutExpired':raise subprocess.TimeoutExpired(cmd,kwargs['timeout'])
            if op_error=='FileNotFoundError':raise FileNotFoundError('synthetic missing')
            raise AssertionError('unknown process error')
        stdout=op_stdout.decode('utf-8') if isinstance(op_stdout,bytes) else op_stdout
        stderr=op_stderr.decode('utf-8') if isinstance(op_stderr,bytes) else op_stderr
        return subprocess.CompletedProcess(cmd,op_code,stdout.replace('\r\n','\n').replace('\r','\n'),stderr.replace('\r\n','\n').replace('\r','\n'))
    def fetch(url,**kwargs):
        index=len(steps);assert index<len(bodies),'unscripted reference request';body=bodies[index];step={'request':{'url':url,'headers':kwargs.get('headers',{})}};steps.append(step)
        if isinstance(body,tuple):
            step['error_kind']=body[0]
            if body[0]=='FetchError':step['status']=body[1];raise FetchError(f'HTTP {body[1]} public-fixture-key')
            if body[0]=='TimeoutError':raise TimeoutError('public-fixture-key timeout')
            raise AssertionError('unknown HTTP error')
        text=body if isinstance(body,str) else json.dumps(body,ensure_ascii=False);step['text']=text;return HttpResponse(url,200,{'content-type':'application/json'},text.encode())
    with patch.dict(os.environ,env,clear=True),patch('katala_web_research.providers.shutil.which',side_effect=which),patch('katala_web_research.providers.subprocess.run',side_effect=run),patch('katala_web_research.providers.fetch_url',side_effect=fetch):
        try:expected={'results':[r.to_dict() for r in OpenAlexSearch().search(query,limit=limit)]}
        except Exception as e:expected={'error_kind':type(e).__name__}
    assert expected.get('error_kind') not in ['AssertionError','UnboundLocalError'],(name,'incomplete fixture')
    cases.append({'name':name,'query':query,'limit':limit,'env':env,'steps':steps,'process_steps':process_steps,'expected':expected})
for limit in [-1,0,1,5,101]:add('limit-'+str(limit),limit=limit,bodies=[page(0,100,'cursor + / = 日本語'),page(100,3)])
for name,payload in [('empty',{'results':[]}),('missing',{}),('null-results',{'results':None}),('false-results',{'results':False}),('root-null','null'),('root-array',[]),('non-json','public-fixture-key rate HTML'),('meta-array',{'results':[item(0)],'meta':[]}),('cursor-number',{'results':[item(0)],'meta':{'next_cursor':1}}),('cursor-true',{'results':[item(0)],'meta':{'next_cursor':True}})]:add(name,bodies=[payload,page(1,0)])
for status in [401,403,404,429,503]:add('status-'+str(status),env={'OPENALEX_API_KEY':'public-fixture-key'},bodies=[('FetchError',status)])
add('timeout',bodies=[('TimeoutError',)])
for name,last in [('empty',page(3,0)),('429',('FetchError',429)),('503',('FetchError',503)),('json','public-fixture-key rate HTML')]:add('later-'+name,limit=5,bodies=[page(0,3,'same-cursor'),last])
add('repeated-cursor-progress',limit=5,bodies=[page(0,2,'same-cursor'),page(2,2,'same-cursor'),page(4,2,'same-cursor')])
add('normal-credentials',env={'OPENALEX_API_KEY':' \u001c public-fixture-key \t','OPENALEX_MAILTO':' fixture@example.test '})
for name,args in [('ok',{}),('missing',{'op':False}),('nonzero',{'op_code':7}),('timeout',{'op_error':'TimeoutExpired'}),('empty',{'op_stdout':' \t'}),('disappeared',{'op_error':'FileNotFoundError'}),('invalid-stdout',{'op_stdout':b'\xff'}),('invalid-stderr-nonzero',{'op_stderr':b'\xff','op_code':7})]:add('op-'+name,env={'OPENALEX_API_KEY':'op://fixture/Research/key'},**args)
add('op-before-bad-filter',env={'OPENALEX_API_KEY':'op://fixture/Research/key','OPENALEX_FROM_DATE':'bad'})
add('op-not-trimmed-before-prefix',env={'OPENALEX_API_KEY':' op://fixture/Research/key '})
add('op-every-page',limit=5,env={'OPENALEX_API_KEY':'op://fixture/Research/key'},bodies=[page(0,3,'next'),page(3,3)])
add('zero-before-bad-config-and-op',limit=0,env={'OPENALEX_API_KEY':'op://fixture/Research/key','OPENALEX_FROM_DATE':'bad','OPENALEX_HAS_PDF':'bad'})
for lang in ['', 'all',' ALL ','en-US','pt_BR','日本','éÀ','a\u0345','İA','english']:add('language-'+lang,env={'OPENALEX_LANGUAGE':lang})
for year in ['2026','２０２６','²⁰²⁶',' 2025 ','bad']:add('year-'+year,env={'OPENALEX_YEAR':year})
add('all-filters',env={'OPENALEX_LANGUAGE':'en-US','OPENALEX_YEAR':'2026','OPENALEX_FROM_DATE':'2026-01-01','OPENALEX_TO_DATE':'2026-12-31','OPENALEX_HAS_PDF':'yes','OPENALEX_HAS_ABSTRACT':'OFF'})
for key in ['OPENALEX_FROM_DATE','OPENALEX_TO_DATE']:
    for value in ['2026-99-99','２０２６-０１-０２','²⁰²⁶-⁰¹-⁰²','----------','2026','2026-1-01']:add(key+'-'+value,env={key:value})
for key in ['OPENALEX_HAS_PDF','OPENALEX_HAS_ABSTRACT']:
    for value in ['', ' ON ','0','false','maybe']:add(key+'-'+value,env={key:value})
for name,index in [('mixed',{'β':[True,False,1,0],'alpha':[-1,3,1],'日本語':[2,2.0,'ignored',None]}),('non-list',{'alpha':4,'β':None}),('not-object',[]),('large',{'alpha':[-9223372036854775808,18446744073709551615]}),('truncate',{'💡'*450:[0],'alpha':[1]})]:add('abstract-'+name,bodies=[{'results':[dict(item(0),abstract_inverted_index=index)]}])
for name,overrides in [('best',{'primary_location':None}),('doi',{'primary_location':None,'best_oa_location':None}),('id',{'primary_location':None,'best_oa_location':None,'doi':None}),('year-date',{'publication_date':None}),('year-false',{'publication_date':None,'publication_year':False}),('year-float',{'publication_date':None,'publication_year':2026.0}),('nullable',{'publication_year':None,'publication_date':None,'cited_by_count':None,'type':None,'content_urls':None,'open_access':None,'best_oa_location':None})]:add('url-date-'+name,bodies=[{'results':[dict(item(0),**overrides)]}])
add('metadata-false-zero',bodies=[{'results':[dict(item(0),publication_year=0,cited_by_count=0,open_access={'is_oa':False,'oa_status':''},primary_location={'landing_page_url':'https://arxiv.org/abs/fixture0','is_oa':False,'license':'','version':None,'source':{'id':'','type':'repository'}})]}])
add('dedup-retraction',bodies=[{'results':[item(0),dict(item(0),display_name='duplicate'),dict(item(1),is_retracted=True),item(2)]}])
for name,overrides in [('duplicate',{'primary_location':item(0)['primary_location']}),('retracted',{'is_retracted':True}),('empty-url',{'primary_location':None,'best_oa_location':None,'doi':None,'id':''}),('surviving',{})]:add('bad-year-'+name,bodies=[{'results':[item(0),dict(item(1),publication_date='²⁰²⁶',**overrides)]}])
for name,best in [('string','unused-best'),('number',7),('bool',True),('array',['unused-best'])]:
    add('unused-best-short-circuit-'+name,bodies=[{'results':[dict(item(0),best_oa_location=best)]}])
    add('selected-best-type-error-'+name,bodies=[{'results':[dict(item(0),primary_location=None,best_oa_location=best)]}])
for seed in ['', ' \u001c ', 'W1',' W1 ','https://openalex.org/W1','https://api.openalex.org/works/W1','https://openalex.org/','https://openalex.org/W1#fragment','10.1/fixture','https://doi.org/10.1/fixture','http://doi.org/10.1/fixture','HTTPS://OPENALEX.ORG/W1','日本語']:
    try:expected={'id':_openalex_work_id(seed)}
    except Exception as e:expected={'error_kind':type(e).__name__}
    identifiers.append({'seed':seed,'expected':expected})
(ROOT/'rust/tests/fixtures/openalex-golden.json').write_text(json.dumps({'baseline':'e66e449cc210bd80ecb25a00391091e72abd9c2b','cases':cases,'identifiers':identifiers},ensure_ascii=False,indent=2,sort_keys=True)+'\n');print('OpenAlex oracles',len(cases),'identifier cases',len(identifiers))
