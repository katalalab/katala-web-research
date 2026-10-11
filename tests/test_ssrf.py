import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from katala_web_research import http as kwr_http
from katala_web_research.http import FetchError, fetch_url, public_addresses
from katala_web_research.reader import read_url

_real_getaddrinfo = socket.getaddrinfo
_real_create_connection = socket.create_connection


class _Handler(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self):
        type(self).hits.append(self.path)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", f"http://internal.test:{self.server.server_address[1]}/secret")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


def _addrinfo(address):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]


class PublicAddressTests(unittest.TestCase):
    def check(self, address):
        with patch("katala_web_research.http.socket.getaddrinfo", return_value=_addrinfo(address)):
            return public_addresses("x.test", 80)

    def test_public_address_is_allowed(self):
        self.assertEqual(self.check("93.184.216.34"), ["93.184.216.34"])

    def test_non_public_addresses_are_refused(self):
        for address in (
            "127.0.0.1",
            "10.0.0.5",
            "192.168.1.1",
            "169.254.169.254",
            "0.0.0.0",
            "::1",
            "fe80::1",
            "fd00::1",
            "::ffff:127.0.0.1",
            "64:ff9b::7f00:1",
            "2002:7f00:1::",
            "::7f00:1",
            "fec0::1",
            "224.0.0.1",
            "239.255.255.250",
            "ff02::1",
            "::ffff:224.0.0.1",
        ):
            with self.subTest(address=address), self.assertRaises(FetchError):
                self.check(address)

    def test_mixed_answer_is_refused(self):
        infos = _addrinfo("93.184.216.34") + _addrinfo("127.0.0.1")
        with patch("katala_web_research.http.socket.getaddrinfo", return_value=infos):
            with self.assertRaises(FetchError):
                public_addresses("x.test", 80)

    def test_numeric_host_forms_are_judged_by_resolved_address(self):
        for host in ("localhost", "2130706433", "0x7f.1", "[::1]".strip("[]")):
            with self.subTest(host=host), self.assertRaises(FetchError):
                public_addresses(host, 80)


class PublicFetchTests(unittest.TestCase):
    def setUp(self):
        _Handler.hits = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _resolve(self, host, port, *args, **kwargs):
        # pub.test is "public"; internal.test is loopback. Everything else resolves for real.
        if host == "pub.test":
            return _addrinfo("93.184.216.34")
        if host == "internal.test":
            return _addrinfo("127.0.0.1")
        return _real_getaddrinfo(host, port, *args, **kwargs)

    def _connect(self, address, *args, **kwargs):
        # Send the "public" address to the local test server so the happy path can be exercised offline.
        if address[0] == "93.184.216.34":
            address = ("127.0.0.1", self.port)
        return _real_create_connection(address, *args, **kwargs)

    def _patched(self):
        return (
            patch("katala_web_research.http.socket.getaddrinfo", self._resolve),
            patch("katala_web_research.http.socket.create_connection", self._connect),
        )

    def test_loopback_target_is_refused_and_never_contacted(self):
        with self.assertRaises(FetchError):
            fetch_url(f"http://127.0.0.1:{self.port}/secret", public_only=True)
        self.assertEqual(_Handler.hits, [])

    def test_public_target_is_fetched_with_pinned_connection(self):
        a, b = self._patched()
        with a, b:
            response = fetch_url(f"http://pub.test:{self.port}/page", public_only=True)
        self.assertEqual(response.body, b"ok")
        self.assertEqual(_Handler.hits, ["/page"])

    def test_redirect_to_internal_host_is_refused(self):
        a, b = self._patched()
        with a, b, self.assertRaises(FetchError):
            fetch_url(f"http://pub.test:{self.port}/redirect", public_only=True)
        self.assertEqual(_Handler.hits, ["/redirect"])

    def test_non_http_scheme_is_refused(self):
        for url in ("file:///etc/passwd", "ftp://example.com/x"):
            with self.subTest(url=url), self.assertRaises(Exception):
                fetch_url(url, public_only=True)

    def test_oversized_body_is_refused(self):
        a, b = self._patched()
        with a, b, patch.object(kwr_http, "MAX_PUBLIC_BODY_BYTES", 1), self.assertRaises(FetchError):
            fetch_url(f"http://pub.test:{self.port}/page", public_only=True)

    def test_default_fetch_still_reaches_private_hosts(self):
        # Provider calls (for example a private SearXNG) keep working: the guard is opt-in.
        response = fetch_url(f"http://127.0.0.1:{self.port}/page")
        self.assertEqual(response.body, b"ok")


class BoundedReadTests(unittest.TestCase):
    def test_redirect_body_drain_is_bounded(self):
        calls = []

        class Fp:
            def read(self, size=-1):
                calls.append(size)
                return b""

            def close(self):
                pass

        handler = kwr_http._PublicRedirectHandler()
        handler.parent = unittest.mock.Mock()
        req = kwr_http.Request("http://pub.test/")
        req.timeout = 5
        handler.http_error_302(req, Fp(), 302, "Found", {"location": "http://pub.test/next"})
        self.assertEqual(calls, [64 * 1024])

    def test_error_body_read_is_bounded(self):
        sizes = []

        class Fp:
            def read(self, size=-1):
                sizes.append(size)
                return b"x"

            def close(self):
                pass

        error = kwr_http.HTTPError("http://pub.test/", 500, "boom", {}, Fp())
        # Only 200 bytes of the error body are reported, so a hostile body is never drained.
        with patch("katala_web_research.http.urlopen", side_effect=error), self.assertRaises(FetchError):
            fetch_url("http://pub.test/")
        self.assertEqual(sizes, [200])


class ReadUrlTests(unittest.TestCase):
    def test_invalid_reader_is_rejected_before_any_dns_lookup(self):
        with patch("katala_web_research.http.socket.getaddrinfo") as lookup:
            with self.assertRaises(ValueError):
                read_url("https://example.com/", reader="bogus")
        lookup.assert_not_called()

    def test_private_url_is_never_sent_to_jina(self):
        with patch("katala_web_research.reader.fetch_url") as fetch:
            for reader in ("auto", "jina", "direct"):
                with self.subTest(reader=reader), self.assertRaises(FetchError):
                    read_url("http://169.254.169.254/latest/meta-data/", reader=reader)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
