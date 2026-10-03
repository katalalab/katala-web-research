#!/usr/bin/env python3
"""Pure provider oracle fixtures; transport patched, never live provider access."""
import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch
from katala_web_research.http import HttpResponse
from katala_web_research.providers import DuckDuckGoSearch
from katala_web_research.provider_parsing import _DuckDuckGoHTMLParser

ROOT=Path(__file__).resolve().parents[2]
os.environ.pop('KWR_SOURCE_REGISTRY_OVERLAY',None)
class FixedDate(date):
    @classmethod
    def today(cls):return cls(2026,1,1)
samples=[
    ('normal',(ROOT/'tests/fixtures/sample.duckduckgo.html').read_text()),
    ('nested','<a class="result__a" href="https://example.test/one">One <b>bold</b> tail</a><div class="result__snippet">before <a href="https://example.test/link">middle</a> after</div>'),
    ('entities','<A CLASS="other result__a" HREF="https://example.test/?a=1&amp;b=2">日本語 &amp;amp; ©</A><DIV CLASS="result__snippet">x&nbsp;y &NotEqualTilde; &lt; z</DIV>'),
    ('unquoted',"<a class=result__a href=https://example.test/u>Unicode 文書</a><span class='result__snippet'>first <b>bold</b> last</span>"),
    ('empty','<html><body>no result</body></html>'),
    ('missing','<a class="result__a">No URL</a><a class="result__a" href="https://example.test/empty"></a><a class="result__a" href="https://example.test/yes">Yes</a>'),
    ('dedup','<a class="result__a" href="https://github.com/fixture/repo?q=1">alpha repo</a><div class="result__snippet">alpha first</div><a class="result__a" href="https://github.com/fixture/repo#two">alpha duplicate</a><a class="result__a" href="https://docs.python.org/3/">alpha docs</a>'),
    ('retracted','<a class="result__a" href="https://example.test/retracted">alpha</a><div class="result__snippet">retracted=true</div>'),
    ('raw','<a class="result__a" href="https://example.test/raw">alpha</a><div class="result__snippet">before<script>raw <a href="fake"> text &amp;</script>after</div>'),
    ('angle','<a class="result__a" href="https://example.test/math">Conditions: x < y > z</a>'),
    ('attrs','<a href="https://example.test/old" href="https://example.test/new?a=>b" class="result__a">duplicate attr</a><div class="result__snippet">sentence.</div>'),
    ('snippet-link','<a class="result__a" href="//example.test/a">One</a><a class="result__snippet">first <b>bold</b> after</a><a class="result__a" href="//example.test/b">Two</a>'),
]
parsers=[];searches=[]
for name,html in samples:
    parser=_DuckDuckGoHTMLParser();parser.feed(html);parser.close()
    parsers.append({'name':name,'html':html,'expected':[r.to_dict() for r in parser.results]})
    for limit in [0,1,2,10,-1,-2]:
        query='alpha 日本語 + * ~' if name=='entities' else 'alpha'
        response=HttpResponse('fixture',200,{'content-type':'text/html; charset=utf-8'},html.encode())
        with patch('katala_web_research.source_quality.date',FixedDate),patch('katala_web_research.providers.fetch_url',return_value=response) as fetch:
            results=DuckDuckGoSearch().search(query,limit=limit)
        request={'url':fetch.call_args.args[0],'headers':fetch.call_args.kwargs['headers']}
        searches.append({'name':name,'html':html,'query':query,'limit':limit,'year':2026,'request':request,'expected':[r.to_dict() for r in results]})
path=ROOT/'rust/tests/fixtures/provider-golden.json'
path.write_text(json.dumps({'baseline':'e66e449cc210bd80ecb25a00391091e72abd9c2b','parsers':parsers,'searches':searches},ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print('provider oracle cases:',len(parsers)+len(searches))
