# Independent feed-slice review

Reviewed base 414d0ffce7b454d04dd733a317b968852493cc31 to head cce1ce2df0239f6da8b18d6f0eb9f45328123862. Python sources match retained e66e449 reference. Review only: implementation files not edited. Offline synthetic inputs on local macOS.

## Finding P2: Plain-text comparisons are stripped as HTML

Location: rust/src/text.rs:205 (html_text trims the characters immediately after `<` before validating tag syntax; clean routes normal content_text through this extractor when both angle brackets appear).

Input: JSONFeed version 1.1, item URL https://example.test/math, title Comparison, content_text `Conditions: x < y > z, then continue.`.

Run `feeds refresh --source file:///.../normal.feed.json --archive ... --json` on separate synthetic Python/Rust archives. Both exit 0 with empty stderr. The persisted feed_items.summary is `Conditions: x < y > z, then continue.` in Python but `Conditions: x z, then continue.` in Rust. This is a normal string field containing plain-text math; dropping the condition changes persisted evidence and subsequent FTS/search snippets. Preserve text when a start tag has whitespace immediately after `<`; add reference-derived feed/HTML and CLI differential regression.

Reproducer /tmp/kwr-review-cli.py, uses synthetic file feed and archives. Independently reproduced before repairs at cce1ce2.

## Evidence

- Existing differential harness: 13 tests, 212 CLI comparisons passed.
- Additional synthetic archive: 24 CLI comparisons passed for same item title across different URLs, same URL across sources, query/fragment URL dedupe, retraction gates, candidate multipliers, limits -2/-1/0/1/3/10 and cached highlights. feed_sources/feed_items/pages rows were exactly unchanged after searches. Reproducer /tmp/kwr-review-dedup.py.
- Library harness independently compared normal parser/text/URL/highlight inputs. Beyond the P2 above, minor edge mismatches were observed for local file URLs whose references escape above URI root, lone semicolon parameter references, and U+001C sentence separators. These are edge parity work; not blockers additional to the documented file-URI/HTML/special-input gate and not evidence that HTTP feeds are implemented.
- Original code/working tree remained clean at end of review; no real archive/credential/live provider/other host operation.

No other blocking normal-input finding was established in this scope. The P2 must be repaired/retested before approving this head; full migration remains incomplete as documented.

## Repair follow-up (uncommitted working tree)

Implementation owner added the minimum whitespace-after-`<` guard plus reference feed/HTML golden and CLI persistence regressions (3 files, 53 additions/3 deletions). Reviewer read that diff and reran the independent CLI reproducer against the rebuilt local binary: both implementations exit 0, empty stderr, and preserve the complete comparison summary. The P2 is resolved in this local repair. Commit/head and CI still need to identify the exact published result. Owner reports pinned offline gate success and 218 differential comparisons; reviewer independently reran the finding-specific CLI reproduction, not the entire repaired gate.
