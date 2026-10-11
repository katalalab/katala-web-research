import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from katala_web_research.mcp_server import TOOLS, handle_request


def _call(name, **arguments):
    return handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )


class ArchiveConfinementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name, "root")
        self.root.mkdir()
        self.outside = Path(self.tmp.name, "outside")
        self.outside.mkdir()
        patcher = patch.dict("os.environ", {"KWR_MCP_ARCHIVE_ROOT": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_refused(self, archive):
        response = _call("kwr.query", terms="x", archive=str(archive))
        self.assertIn("error", response, archive)
        self.assertIn("archive root", response["error"]["message"])

    def test_path_outside_root_is_refused_and_nothing_is_created(self):
        self.assert_refused(self.outside / "evil.sqlite")
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_parent_traversal_is_refused(self):
        self.assert_refused(self.root / ".." / "outside" / "evil.sqlite")
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_symlink_out_of_root_is_refused(self):
        link = self.root / "link"
        try:
            os.symlink(self.outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assert_refused(link / "evil.sqlite")
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_non_database_suffix_is_refused(self):
        self.assert_refused(self.root / "notes.txt")
        self.assert_refused(self.root / "authorized_keys")

    def test_every_tool_that_takes_archive_is_confined(self):
        names = [t["name"] for t in TOOLS if "archive" in t["inputSchema"]["properties"]]
        self.assertGreaterEqual(len(names), 5)
        for name in names:
            with self.subTest(tool=name):
                arguments = {"query": "x", "terms": "x", "archive": str(self.outside / "evil.sqlite"), "no_web": True}
                response = _call(name, **arguments)
                self.assertIn("error", response)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_database_inside_root_still_works(self):
        response = _call("kwr.query", terms="x", archive=str(self.root / "ok.sqlite"))
        self.assertNotIn("error", response, json.dumps(response)[:300])
        self.assertTrue((self.root / "ok.sqlite").exists())

    def test_default_archive_is_used_when_argument_is_omitted(self):
        with tempfile.TemporaryDirectory() as cwd:
            old = os.getcwd()
            os.chdir(cwd)
            try:
                with patch.dict("os.environ", {"KWR_MCP_ARCHIVE_ROOT": ""}):
                    response = _call("kwr.query", terms="x")
                    self.assertNotIn("error", response)
                    # the schema default echoed back by a client must also be accepted
                    echoed = _call("kwr.query", terms="x", archive=".katala-web-research/archive.sqlite")
                    self.assertNotIn("error", echoed)
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
