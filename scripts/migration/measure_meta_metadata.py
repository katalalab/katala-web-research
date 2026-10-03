#!/usr/bin/env python3
"""Combined and source-targeted loopback cases allocate actual Meta output/metadata schema evidence."""
import hashlib
import json
import unittest
from pathlib import Path
import meta_differential as fixture

class SchemaFixture(fixture.MetaFixture):
    def test_measure(self):
        names="ddg,github,github_code,searxng,brave,jina,openalex,feed"
        self.compare(names,gh=False,expected_providers=names.split(","))
        self.compare(names,gh=False,plan={"brave":"error"},expected_providers=names.split(","))
    def test_remaining_source_metadata(self):
        for name in ["brave","searxng","feed"]:
            self.compare(name,gh=False,expected_providers=[name])
suite=unittest.TestSuite([SchemaFixture("test_measure"),SchemaFixture("test_remaining_source_metadata")])
result=unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful(),"schema fixture failed; no coverage artifact accepted"
value=fixture.MODEL_OBSERVATIONS
assert set(value["sources"])=={"ddg","github","github_code","searxng","brave","jina","openalex","feed"}, "rendered source metadata coverage incomplete"
payload={"target":"aarch64-apple-darwin","executor":"author","paired_cases":SchemaFixture.comparisons,"returned_native_rows":value["rows"],"required_search_result_fields":sorted(fixture.MODEL_FIELDS),"metadata_keys_observed_by_source":{k:sorted(v) for k,v in sorted(value["sources"].items())},"meta_engine_run_fields_observed":sorted(value["meta_run_fields"]),"scope_acceptance":"passed_measured_fields_and_python_replay","full_ready":False,"normalization":"no health/score/rank/output fields; expected Python uses each execution's measured clock and completion inputs"}
root=Path(__file__).resolve().parents[2]
h=hashlib.sha256()
for p in sorted([*root.glob("rust/src/**/*.rs"),root/"Cargo.toml",root/"Cargo.lock",root/"rust-toolchain.toml"],key=lambda p:p.relative_to(root).as_posix()):h.update(p.relative_to(root).as_posix().encode()+b"\0"+p.read_bytes()+b"\0")
payload["source_tree_sha256"]=h.hexdigest()
(root/"docs/migration/meta-metadata-coverage.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
print("Meta schema coverage:",payload["paired_cases"],"paired cases,",value["rows"],"native rows; full_ready=false")
