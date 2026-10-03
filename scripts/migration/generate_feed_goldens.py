#!/usr/bin/env python3
"""Regenerate synthetic feed goldens from the retained Python reference."""
import json
import os
from html import unescape
from datetime import date
from unittest.mock import patch
from katala_web_research.models import SearchResult
from katala_web_research.rank import rank_results
from pathlib import Path
from katala_web_research.feeds import parse_feed_text
from katala_web_research.text import SimpleHTMLTextExtractor
from katala_web_research.query_builder import build_search_query
from katala_web_research.archive_highlights import build_highlight
os.environ.pop('KWR_SOURCE_REGISTRY_OVERLAY',None)
ROOT = Path(__file__).resolve().parents[2]
path = ROOT / 'rust/tests/fixtures/feed-golden.json'
data = json.loads(path.read_text())
for case in data['feeds']:
    parsed = parse_feed_text(case['text'], source_url=case['source_url'], fetched_at=case['fetched_at'])
    case['expected'] = {'source': parsed.source.to_dict(), 'items': [item.to_dict() for item in parsed.items]}
for case in data['ranking']:
    class FixedDate(date):
        @classmethod
        def today(cls): return cls(case['year'],1,1)
    with patch('katala_web_research.source_quality.date',FixedDate):
        case['expected'] = [item.to_dict() for item in rank_results(case['query'],[SearchResult(**item) for item in case['input']])]
for case in data['html']:
    p = SimpleHTMLTextExtractor(); p.feed(case['input']); p.close()
    case['title'], case['content'] = p.title, p.content
for case in data.get('entities', []):
    case['expected'] = unescape(case['input'])
for case in data.get('queries', []):
    q = build_search_query(case['query'], categories=case['categories'], include_domains=case['includes'], exclude_domains=case['excludes'])
    case['expected'] = {'query': q.query, 'domains': q.category_domains, 'pdf': q.pdf_requested}
for case in data.get('highlights', []):
    case['expected'] = build_highlight(case['query'], case['content'])
path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
