import json
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from katala_web_research.http import FetchError, HttpResponse
from katala_web_research.reader import read_direct, read_with_jina


def _response(body: str) -> HttpResponse:
    return HttpResponse(
        url="https://r.jina.ai/",
        status=200,
        headers={"content-type": "text/plain; charset=utf-8"},
        body=body.encode("utf-8"),
    )


class ReaderTests(unittest.TestCase):
    def test_jina_target_url_is_encoded_as_opaque_path(self):
        target = "https://example.com/a b?q=x&z=1#frag"
        with patch("katala_web_research.reader.fetch_url", return_value=_response("# Example")) as fetch:
            read_with_jina(target)

        jina_url = fetch.call_args.args[0]
        parsed = urlparse(jina_url)
        self.assertEqual(parsed.netloc, "r.jina.ai")
        self.assertEqual(parsed.query, "")
        self.assertEqual(parsed.fragment, "")
        self.assertIn("https%3A%2F%2Fexample.com%2Fa%20b%3Fq%3Dx%26z%3D1%23frag", parsed.path)

    def test_jina_reader_allows_json_documents_with_code_field(self):
        content = json.dumps({"code": "sample", "message": "domain content", "data": [1, 2, 3]})
        with patch("katala_web_research.reader.fetch_url", return_value=_response(content)):
            snapshot = read_with_jina("https://example.com/api")

        self.assertEqual(snapshot.content, content)

    def test_jina_reader_rejects_known_error_payload(self):
        content = json.dumps(
            {
                "code": 422,
                "status": 42200,
                "name": "AssertionFailureError",
                "message": "invalid target",
            }
        )
        with patch("katala_web_research.reader.fetch_url", return_value=_response(content)):
            with self.assertRaises(FetchError):
                read_with_jina("https://example.com/bad")

    def test_read_direct_sniffs_meta_charset_when_header_lacks_it(self):
        body = ('<html><head><meta charset="shift_jis"><title>テスト</title></head><body>本文</body></html>').encode(
            "shift_jis"
        )
        response = HttpResponse(
            url="https://example.jp/",
            status=200,
            headers={"content-type": "text/html"},
            body=body,
        )
        with patch("katala_web_research.reader.fetch_url", return_value=response):
            snapshot = read_direct("https://example.jp/")

        self.assertIn("本文", snapshot.content)
        self.assertEqual(snapshot.title, "テスト")

    def test_read_direct_preserves_windows_japanese_charset(self):
        body = '<html><meta charset="cp932"><title>髙橋</title><body>本文</body></html>'.encode("cp932")
        response = HttpResponse(url="https://example.jp/", status=200, headers={"content-type": "text/html"}, body=body)
        with patch("katala_web_research.reader.fetch_url", return_value=response):
            snapshot = read_direct("https://example.jp/")
        self.assertEqual(snapshot.title, "髙橋")
        self.assertIn("本文", snapshot.content)

    def test_read_direct_ignores_transform_charsets(self):
        for charset in ("unicode_escape", "raw_unicode_escape", "hex", "base64"):
            with self.subTest(charset=charset):
                body = (f'<html><meta charset="{charset}"><body>' + r"literal \u0061 text" + "</body></html>").encode()
                response = HttpResponse(
                    url="https://example.com/", status=200, headers={"content-type": "text/html"}, body=body
                )
                with patch("katala_web_research.reader.fetch_url", return_value=response):
                    snapshot = read_direct("https://example.com/")
                self.assertIn(r"literal \u0061 text", snapshot.content)


if __name__ == "__main__":
    unittest.main()
