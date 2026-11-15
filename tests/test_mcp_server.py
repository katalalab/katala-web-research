import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from katala_web_research.archive import Archive
from katala_web_research.feeds import parse_feed_text
from katala_web_research.mcp_server import handle_request, main

FIXTURES = Path(__file__).parent / "fixtures"


class McpServerTests(unittest.TestCase):
    def setUp(self):
        # These tests keep archives in a temp dir; the operator-set root is how MCP is allowed to reach it.
        patcher = patch.dict("os.environ", {"KWR_MCP_ARCHIVE_ROOT": tempfile.gettempdir()})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_initialize(self):
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(response["result"]["serverInfo"]["name"], "katala-web-research")
        self.assertIn("tools", response["result"]["capabilities"])

    def test_tools_list(self):
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("kwr.plan", names)
        self.assertIn("kwr.eval", names)
        self.assertIn("kwr.search", names)
        self.assertIn("kwr.repos_query", names)
        self.assertIn("kwr.feeds_query", names)
        self.assertIn("kwr.investigate", names)

    def test_search_tool_lists_github_code_provider(self):
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        provider_schema = tools["kwr.search"]["inputSchema"]["properties"]["provider"]
        self.assertIn("github_code", provider_schema["enum"])

    def test_main_skips_malformed_body_then_processes_next_frame(self):
        # A malformed body must be skipped without desyncing the stream: the
        # well-formed frame that follows it still has to be processed.
        def frame(payload: bytes) -> bytes:
            return b"Content-Length: %d\r\n\r\n%s" % (len(payload), payload)

        good = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode("utf-8")
        stream_in = io.BytesIO(frame(b"{not valid json") + frame(good))
        stream_out = io.BytesIO()
        fake_stdin = types.SimpleNamespace(buffer=stream_in)
        fake_stdout = types.SimpleNamespace(buffer=stream_out)

        with patch("katala_web_research.mcp_server.sys.stdin", fake_stdin):
            with patch("katala_web_research.mcp_server.sys.stdout", fake_stdout):
                self.assertEqual(main(), 0)

        self.assertIn(b"serverInfo", stream_out.getvalue())

    def test_main_stops_when_frame_length_does_not_identify_a_boundary(self):
        good = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode()
        for length in (b"invalid", b"-1", b"9" * 4400):
            with self.subTest(length=length[:12]):
                body = b"Content-Length: " + length + b"\r\n\r\n"
                body += b"Content-Length: %d\r\n\r\n%s" % (len(good), good)
                stream_in, stream_out = io.BytesIO(body), io.BytesIO()
                with (
                    patch("katala_web_research.mcp_server.sys.stdin", types.SimpleNamespace(buffer=stream_in)),
                    patch("katala_web_research.mcp_server.sys.stdout", types.SimpleNamespace(buffer=stream_out)),
                ):
                    self.assertEqual(main(), 0)
                self.assertEqual(stream_out.getvalue(), b"")

    def test_main_skips_non_object_body_and_preserves_next_boundary(self):
        good = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode()
        for invalid in (b"[]", b'"bad"', b"null"):
            with self.subTest(body=invalid):
                body = b"Content-Length: %d\r\n\r\n%s" % (len(invalid), invalid)
                body += b"Content-Length: %d\r\n\r\n%s" % (len(good), good)
                stream_in, stream_out = io.BytesIO(body), io.BytesIO()
                with (
                    patch("katala_web_research.mcp_server.sys.stdin", types.SimpleNamespace(buffer=stream_in)),
                    patch("katala_web_research.mcp_server.sys.stdout", types.SimpleNamespace(buffer=stream_out)),
                ):
                    self.assertEqual(main(), 0)
                self.assertIn(b"serverInfo", stream_out.getvalue())

    def test_main_does_not_handle_a_truncated_frame_even_if_body_is_valid_json(self):
        good = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode()
        stream_in = io.BytesIO(b"Content-Length: %d\r\n\r\n%s" % (len(good) + 10, good))
        stream_out = io.BytesIO()
        with (
            patch("katala_web_research.mcp_server.sys.stdin", types.SimpleNamespace(buffer=stream_in)),
            patch("katala_web_research.mcp_server.sys.stdout", types.SimpleNamespace(buffer=stream_out)),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(stream_out.getvalue(), b"")

    def test_main_recovers_after_a_complete_json_body_exceeds_integer_digit_limit(self):
        previous = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(640)
            bad = b'{"id":' + b"9" * 1000 + b',"method":"initialize"}'
            good = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode()
            stream_in = io.BytesIO(
                b"Content-Length: %d\r\n\r\n%s" % (len(bad), bad) + b"Content-Length: %d\r\n\r\n%s" % (len(good), good)
            )
            stream_out = io.BytesIO()
            with (
                patch("katala_web_research.mcp_server.sys.stdin", types.SimpleNamespace(buffer=stream_in)),
                patch("katala_web_research.mcp_server.sys.stdout", types.SimpleNamespace(buffer=stream_out)),
            ):
                self.assertEqual(main(), 0)
            self.assertIn(b"serverInfo", stream_out.getvalue())
        finally:
            sys.set_int_max_str_digits(previous)

    def test_feeds_query_returns_archived_feed_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed_archive_path = Path(tmp) / "feed.sqlite"
            parsed = parse_feed_text(
                (FIXTURES / "sample.rss.xml").read_text(encoding="utf-8"),
                source_url="https://example.com/feed.xml",
                fetched_at="2026-05-28T00:00:00+00:00",
            )
            feed_archive = Archive(feed_archive_path)
            try:
                feed_archive.upsert_feed_source(parsed.source)
                feed_archive.upsert_feed_items(parsed.items)
            finally:
                feed_archive.close()

            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "kwr.feeds_query",
                        "arguments": {"terms": "RSSHub", "archive": str(feed_archive_path), "limit": 5},
                    },
                }
            )

        text = response["result"]["content"][0]["text"]
        self.assertIn("https://example.com/rsshub-adapter", text)

    def test_brief_feed_provider_uses_requested_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed_archive_path = Path(tmp) / "feed.sqlite"
            empty_archive_path = Path(tmp) / "empty.sqlite"
            parsed = parse_feed_text(
                (FIXTURES / "sample.rss.xml").read_text(encoding="utf-8"),
                source_url="https://example.com/feed.xml",
                fetched_at="2026-05-28T00:00:00+00:00",
            )
            feed_archive = Archive(feed_archive_path)
            try:
                feed_archive.upsert_feed_source(parsed.source)
                feed_archive.upsert_feed_items(parsed.items)
            finally:
                feed_archive.close()

            with patch.dict("os.environ", {"KWR_ARCHIVE": str(empty_archive_path)}):
                response = handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "kwr.brief",
                            "arguments": {
                                "query": "RSSHub adapter",
                                "provider": "feed",
                                "archive": str(feed_archive_path),
                                "web_limit": 5,
                                "repo_limit": 0,
                            },
                        },
                    }
                )

        text = response["result"]["content"][0]["text"]
        self.assertIn("RSSHub adapter research", text)

    def test_search_feed_provider_uses_requested_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed_archive_path = Path(tmp) / "feed.sqlite"
            empty_archive_path = Path(tmp) / "empty.sqlite"
            parsed = parse_feed_text(
                (FIXTURES / "sample.rss.xml").read_text(encoding="utf-8"),
                source_url="https://example.com/feed.xml",
                fetched_at="2026-05-28T00:00:00+00:00",
            )
            feed_archive = Archive(feed_archive_path)
            try:
                feed_archive.upsert_feed_source(parsed.source)
                feed_archive.upsert_feed_items(parsed.items)
            finally:
                feed_archive.close()

            with patch.dict("os.environ", {"KWR_ARCHIVE": str(empty_archive_path)}):
                response = handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "kwr.search",
                            "arguments": {
                                "query": "RSSHub adapter",
                                "provider": "feed",
                                "archive": str(feed_archive_path),
                                "limit": 5,
                            },
                        },
                    }
                )

        text = response["result"]["content"][0]["text"]
        self.assertIn("RSSHub adapter research", text)
        self.assertIn("https://example.com/rsshub-adapter", text)


if __name__ == "__main__":
    unittest.main()
