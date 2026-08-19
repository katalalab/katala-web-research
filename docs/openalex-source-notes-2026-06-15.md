# OpenAlex Source Notes

date: 2026-06-15
source: SearXNG `searx/engines/openalex.py`
commit: `cf1410a`

Observed engine shape:
- Uses the official OpenAlex Works endpoint.
- Does not require an API key.
- Supports optional `mailto` for OpenAlex polite pool behavior.
- Uses `search`, `per-page`, `sort=relevance_score:desc`, and selected scholarly result fields.
- Reconstructs abstracts from `abstract_inverted_index` and maps bibliographic metadata into paper results.

Katala adaptation chosen now:
- OpenAlex provider no longer requires `OPENALEX_API_KEY`.
- `OPENALEX_API_KEY` remains supported when configured.
- Added optional `OPENALEX_MAILTO` pass-through.
- Added optional `OPENALEX_LANGUAGE`; values such as `en-US` are mapped to OpenAlex `filter=language:en`, matching SearXNG's engine behavior.
- Added optional `OPENALEX_YEAR`; four-digit values are mapped to OpenAlex `filter=publication_year:<year>` and are combined with the language filter when both are set.
- Added optional `OPENALEX_FROM_DATE` and `OPENALEX_TO_DATE`; `YYYY-MM-DD` values are mapped to official OpenAlex `from_publication_date` and `to_publication_date` convenience filters.
- Added optional `OPENALEX_HAS_PDF` and `OPENALEX_HAS_ABSTRACT`; boolean-like values map to official `has_content.pdf:true|false` and `has_abstract:true|false` filters.
- OpenAlex results retain `primary_location`, `best_oa_location`, `content_url`, DOI, citation, and access-status metadata when returned, including landing page and PDF URLs.
- OpenAlex provider uses official cursor paging (`cursor=*`, then `meta.next_cursor`) when Katala requests more than one 100-result page. This is bounded to the requested candidate count, not used for bulk dataset download.
- Provider status now reports OpenAlex as available by default because the official API is public.

Verification:
- `tests.test_providers.ProviderTests.test_openalex_provider_parses_work_results` covers no-key operation and location/content metadata retention.
- `tests.test_providers.ProviderTests.test_openalex_provider_adds_optional_key_and_mailto` covers optional parameter pass-through, including language, publication-year, publication-date range, PDF availability, and abstract availability filter mapping.
- `tests.test_providers.ProviderTests.test_openalex_provider_rejects_invalid_date_filter_before_fetch` covers local date validation.
- `tests.test_providers.ProviderTests.test_openalex_provider_rejects_invalid_boolean_filter_before_fetch` covers local boolean filter validation.
- `tests.test_providers.ProviderTests.test_openalex_provider_fetches_multiple_cursor_pages_for_large_limits` covers cursor paging.

Next candidates:
- Consider exposing OpenAlex `open_access.is_oa` or `best_oa_location.license` filters if downstream workflows need license-aware candidate pools.

## 2026-08-20: `content_url` is not a select field, and citation expansion

date: 2026-08-20
source: `https://api.openalex.org/works?per_page=1&select=content_url` (official API error listing the valid select fields)
local version: `katala-web-research` 0.1.0, `src/katala_web_research/providers.py`

Finding: the `select` list sent by the OpenAlex provider contained `content_url`. That field does
not exist; the API rejects the entire request with `HTTP 400 Invalid query parameters error`, so
every live OpenAlex search failed while the offline fixtures stayed green — the fixture supplied a
`content_url` key the API never returns. The real field is `content_urls`, an object of per-format
URLs (`pdf`, `grobid_xml`).

Decision:
- `select` now requests `content_urls`; result metadata keeps the single `content_url` key, sourced
  from `content_urls.pdf`. The fixture in `tests/test_providers.py` was corrected to the real shape.
- Added citation expansion: `kwr openalex expand <id|doi|url> [--direction referenced|citing|both]
  [--limit N]`. `referenced_works` is followed through `filter=openalex_id:W1|W2|...`, citing works
  through `filter=cites:<id>`. The per-direction count is clamped to `OPENALEX_EXPAND_MAX` (50) so
  one command cannot turn into a graph crawl.
- The API key can only travel as an `api_key=` query parameter, so `http.redact_url()` strips it from
  every error message before it can reach a log.

Verification (2026-08-20, rtx4090):
- `kwr search "query decomposition retrieval" --provider openalex --limit 2` returns results; before
  the fix it returned `HTTP 400 ... content_url is not a valid select field`.
- `kwr openalex expand https://doi.org/10.1038/s41592-019-0686-2 --limit 2` returns both directions.
- `tests/test_openalex_expand.py` covers bounds, direction isolation, seed forms, fail-closed
  behaviour on an unresolvable work, and that the key never reaches an error string.

Risk / rollback: the change is confined to the `select` list, one metadata mapping, and new
functions. Reverting the two `content_urls` edits restores the previous (broken) live behaviour.
Next refresh: re-check the valid select-field list when OpenAlex next changes the works schema.
