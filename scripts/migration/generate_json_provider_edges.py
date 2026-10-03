#!/usr/bin/env python3
"""Additional malformed/type/Unicode oracles, with named safety differences."""
import json
import runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
g=runpy.run_path(str(ROOT/'scripts/migration/generate_json_provider_goldens.py'))
add=g['add'];payload=g['payload'];item=g['item'];cases=g['cases'];start=len(cases)
POLICIES={
 'typed_fields':'Reject non-text truthy result fields/date values without echoing values; Python may fail later with another kind or emit an ill-typed publication field.',
 'typed_collections':'Reject Jina object-valued data as TypeError; Python slice lookup raises version-dependent KeyError/TypeError.',
 'strict_json_constants':'Reject NaN and Infinity instead of accepting Python nonstandard JSON numeric constants.',
 'strict_unicode':'Reject unpaired surrogate JSON strings instead of constructing strings which cannot be emitted as UTF-8.',
 'depth_limit':'serde_json bounded nesting rejects deep JSON before result-shape interpretation; global HTTP byte cap still applies.'
}
def edge(provider,name,*,native_kind=None,policy=None,**kwargs):
    add(provider,name,**kwargs);case=cases[-1]
    if native_kind and case['expected'] != {'error_kind':native_kind}:
        assert policy in POLICIES,(provider,name,policy)
        case['native_expected']={'error_kind':native_kind};case['intentional_policy']=policy
for p in ['searxng','brave','jina']:
    for name,body in [('root-array',[]),('root-true',True),('root-false',False),('root-zero',0),('root-number',23),('root-string','public-fixture-key'),('root-null',None),('root-empty-object',{})]:edge(p,name,bodies=[body])
    for name,value in [('null',None),('false',False),('true',True),('zero',0),('number',1),('empty-string',''),('string','public-fixture-key'),('empty-object',{}),('object',{'public-fixture-key':1}),('nested-list',[[]]),('null-item',[None]),('true-item',[True]),('number-item',[1]),('string-item',['public-fixture-key'])]:edge(p,'collection-'+name,bodies=[payload(p,value)],native_kind='TypeError' if p=='jina' and isinstance(value,dict) else None,policy='typed_collections' if p=='jina' and isinstance(value,dict) else None)
    fields=['title','url',{'searxng':'content','brave':'description','jina':'description'}[p],{'searxng':'publishedDate','brave':'age','jina':'publishedTime'}[p]]
    for field in fields:
        for name,value in [('null',None),('false',False),('zero',0),('true',True),('number',1),('empty-string',''),('empty-list',[]),('list',['public-fixture-key']),('empty-object',{}),('object',{'public-fixture-key':1})]:
            row=item(p,0);row[field]=value
            # Rust's typed schema can reject fields which Python postpones to
            # urllib/regex or emits directly. Record the exact reference outcome.
            invalid=not isinstance(value,(str,type(None))) and (bool(value) or (field==fields[-1] and p!='jina'))
            edge(p,'field-'+field+'-'+name,bodies=[payload(p,[row])],native_kind='TypeError' if invalid else None,policy='typed_fields' if invalid else None)
    for name,text in [('truncated','{"public-fixture-key":'),('trailing','{} public-fixture-key'),('empty',''),('bom','\ufeff{}'),('duplicate-keys','{"results":[null],"data":[null],"web":true,"results":[],"data":[],"web":{}}'),('escaped-controls','{"results":[],"data":[],"web":{},"unused":"\\u0000\\u001c"}')]:edge(p,'json-'+name,bodies=[text])
    for name,text in [('nan','{"results":[],"data":[],"web":{},"unused":NaN}'),('infinity','{"results":[],"data":[],"web":{},"unused":Infinity}'),('negative-infinity','{"results":[],"data":[],"web":{},"unused":-Infinity}')]:edge(p,'json-'+name,bodies=[text],native_kind='FetchError',policy='strict_json_constants')
    edge(p,'json-lone-surrogate',bodies=['{"results":[],"data":[],"web":{},"unused":"\\ud800"}'],native_kind='FetchError',policy='strict_unicode')
    edge(p,'json-depth-150',bodies=['{"results":'+ '['*150+'0'+']'*150+',"web":{"results":'+ '['*150+'0'+']'*150+'},"data":'+ '['*150+'0'+']'*150+'}'],native_kind='FetchError',policy='depth_limit')
    for query in ['alpha 東京 café 💡','alpha\u001c日本語','alpha\0text']:
        edge(p,'unicode-query-'+str(len(query)),query=query)
    row=item(p,0);row['title']='alpha 日本語 💡';row['url']='https://例え.test/日本語/💡';edge(p,'unicode-idn-result',bodies=[payload(p,[row])])
    for year in ['٢٠٢٦','２０２６','𝟚𝟘𝟚𝟞','²⁰²⁶']:
        row=item(p,0);row[fields[-1]]=year+'-01-01';edge(p,'unicode-published-'+year,bodies=[payload(p,[row])])
    key={'searxng':'KWR_SEARXNG_URL','brave':'BRAVE_SEARCH_API_KEY','jina':'JINA_API_KEY'}[p]
    edge(p,'empty-credential',env={key:''});edge(p,'whitespace-credential',env={key:'   '})
for digit in ['٢','０２','𝟚','²','١٢','０'*100+'２']:
    edge('searxng','unicode-safe-'+digit,env={'KWR_SEARXNG_SAFESEARCH':digit})
for year in ['٢٠٢٦','２０２６','²⁰²⁶']:
    edge('brave','unicode-freshness-'+year,env={'BRAVE_FRESHNESS':year+'-01-01to'+year+'-12-31'})
edge('searxng','slash-only-endpoint',env={'KWR_SEARXNG_URL':'///'})
# Year conversion is evaluated only after URL/dedup/retraction gates. These
# are ordinary string inputs, not typed_fields safety-policy exceptions.
for provider in ['searxng','brave','jina']:
    date_field={'searxng':'publishedDate','brave':'age','jina':'publishedTime'}[provider]
    snippet_field={'searxng':'content','brave':'description','jina':'description'}[provider]
    good=item(provider,0)
    bad=item(provider,1);bad[date_field]='²⁰²⁶-01-01'
    for gate in ['duplicate','retracted','empty-url']:
        discarded=dict(bad)
        if gate=='duplicate':discarded['url']=good['url']
        elif gate=='retracted':discarded[snippet_field]='retracted=true'
        else:discarded['url']=''
        edge(provider,'year-conversion-after-'+gate,bodies=[payload(provider,[good,discarded])])
    edge(provider,'year-conversion-surviving-error',bodies=[payload(provider,[good,bad])])
selected=cases[start:]
assert all(c.get('intentional_policy') in POLICIES for c in selected if 'native_expected' in c)
(ROOT/'rust/tests/fixtures/json-provider-edges.json').write_text(json.dumps({'baseline':'e66e449cc210bd80ecb25a00391091e72abd9c2b','oracle_python':'3.13 / Unicode 15.1','policies':POLICIES,'cases':selected},ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print('JSON edge cases',len(selected),'intentional differences',sum('native_expected' in c for c in selected),'by provider',{p:sum(c['provider']==p for c in selected) for p in ['searxng','brave','jina']})
