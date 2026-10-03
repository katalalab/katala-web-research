# PR #21 unquoted href slash repair

Reviewed head: 2391115058e307d35818c8972f2a9d95db51eb96. Parent's independent reviewer checked source/fixtures/dependency/CI, found no blocking issue, and reported one P3 compatibility difference from a Python measurement plus native source reasoning; no reviewer native execution is claimed.

Input: `<a class=result__a href=https://example.test/>Title</a>`. Python HTMLParser consumes the terminal slash as part of the unquoted href and emits Title at https://example.test/. Native raw.ends_with('/') incorrectly marked the anchor self-closing and discarded the title/result.

The repair records the end of the last parsed attribute and treats a slash as a self-closing delimiter only when it remains outside the attributes. A quoted href followed by /> stays self-closing. The Python fixture generator adds both forms; parser/request/rank golden coverage becomes 14 + 84 = 98 cases. A localhost CLI regression explicitly checks the emitted title/URL, complete JSON parity, one request, empty stderr and unchanged preexisting synthetic page rows. Other provider implementations are not included in this repair.

Affected native golden/adapter tests and warnings-denied clippy pass; the provider fixture gate passes 24 CLI comparisons. Independent repaired-head diff review and normal CI are still required before integration. Malformed/partial HTML/exotic attributes, seven remaining network surfaces, positive enrichment and the complete acceptance matrix remain pending.
