import argparse
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from katala_web_research import cli
from katala_web_research.archive import Archive


class SQLiteLifecycleTests(unittest.TestCase):
    def assert_close_failure_note(self, error):
        notes = "\n".join(getattr(error, "__notes__", []))
        self.assertIn("RuntimeError: synthetic close failure", notes)
        self.assertIn("failed_close", notes)

    def assert_closed(self, conn):
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_doctor_closes_connection_after_success(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        with patch.object(cli.sqlite3, "connect", return_value=conn), patch.object(cli, "provider_status", return_value=[]):
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(cli.cmd_doctor(argparse.Namespace(check_searxng=False)), 0)
        self.assertIn("sqlite_fts5: ok", out.getvalue())
        self.assert_closed(conn)

    def test_doctor_closes_connection_when_probe_fails(self):
        class FailingConnection(sqlite3.Connection):
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("synthetic FTS failure")

        conn = sqlite3.connect(":memory:", factory=FailingConnection)
        self.addCleanup(conn.close)
        with patch.object(cli.sqlite3, "connect", return_value=conn), patch.object(cli, "provider_status", return_value=[]):
            with self.assertRaisesRegex(sqlite3.OperationalError, "synthetic FTS failure"):
                cli.cmd_doctor(argparse.Namespace(check_searxng=False))
        # Bypass the synthetic override to inspect the underlying real connection.
        with self.assertRaises(sqlite3.ProgrammingError):
            sqlite3.Connection.execute(conn, "SELECT 1")

    def test_repo_scan_closes_connection_when_metadata_read_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Archive(Path(tmp) / "fixture.sqlite")
            try:
                args = argparse.Namespace(archive=str(Path(tmp) / "fixture.sqlite"), no_incremental=False)
                with patch.object(cli, "Archive", return_value=archive), patch.object(archive, "repo_document_metadata", side_effect=RuntimeError("synthetic metadata failure")):
                    with self.assertRaisesRegex(RuntimeError, "synthetic metadata failure"):
                        cli.cmd_repos_scan(args)
                self.assert_closed(archive.conn)
            finally:
                archive.close()

    def test_archive_closes_connection_when_schema_initialization_fails(self):
        real_connect = sqlite3.connect
        opened = []

        def connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            opened.append(conn)
            return conn

        with tempfile.TemporaryDirectory() as tmp:
            try:
                with patch("katala_web_research.archive.sqlite3.connect", side_effect=connect), patch.object(Archive, "_init_schema", side_effect=RuntimeError("synthetic schema failure")):
                    with self.assertRaisesRegex(RuntimeError, "synthetic schema failure"):
                        Archive(Path(tmp) / "fixture.sqlite")
                self.assertEqual(len(opened), 1)
                self.assert_closed(opened[0])
            finally:
                for conn in opened:
                    conn.close()

    def test_doctor_keeps_probe_error_when_close_also_fails(self):
        class FailingConnection(sqlite3.Connection):
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("synthetic probe failure")

            def close(self):
                super().close()
                failed_close()

        def failed_close():
            raise RuntimeError("synthetic close failure")

        conn = sqlite3.connect(":memory:", factory=FailingConnection)
        try:
            with patch.object(cli.sqlite3, "connect", return_value=conn), patch.object(cli, "provider_status", return_value=[]):
                with self.assertRaisesRegex(sqlite3.OperationalError, "synthetic probe failure") as caught:
                    cli.cmd_doctor(argparse.Namespace(check_searxng=False))
            self.assert_close_failure_note(caught.exception)
        finally:
            sqlite3.Connection.close(conn)

    def test_doctor_propagates_close_failure_after_success(self):
        class FailingClose(sqlite3.Connection):
            def close(self):
                super().close()
                raise RuntimeError("synthetic close failure")

        conn = sqlite3.connect(":memory:", factory=FailingClose)
        try:
            with patch.object(cli.sqlite3, "connect", return_value=conn), patch.object(cli, "provider_status", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "synthetic close failure"):
                    cli.cmd_doctor(argparse.Namespace(check_searxng=False))
        finally:
            sqlite3.Connection.close(conn)

    def test_repo_scan_keeps_metadata_error_when_close_also_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Archive(Path(tmp) / "fixture.sqlite")
            def failed_close():
                archive.conn.close()
                raise RuntimeError("synthetic close failure")

            cause = OSError("synthetic underlying cause")
            primary = ValueError("synthetic metadata failure")
            primary.__cause__ = cause
            args = argparse.Namespace(archive=str(Path(tmp) / "fixture.sqlite"), no_incremental=False)
            with patch.object(cli, "Archive", return_value=archive), patch.object(archive, "repo_document_metadata", side_effect=primary), patch.object(archive, "close", side_effect=failed_close):
                with self.assertRaisesRegex(ValueError, "synthetic metadata failure") as caught:
                    cli.cmd_repos_scan(args)
            self.assertIs(caught.exception.__cause__, cause)
            self.assert_close_failure_note(caught.exception)
            self.assert_closed(archive.conn)

    def test_archive_keeps_schema_error_when_close_also_fails(self):
        class FailingClose(sqlite3.Connection):
            def close(self):
                super().close()
                failed_close()

        def failed_close():
            raise RuntimeError("synthetic close failure")

        conn = sqlite3.connect(":memory:", factory=FailingClose)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with patch("katala_web_research.archive.sqlite3.connect", return_value=conn), patch.object(Archive, "_init_schema", side_effect=ValueError("synthetic schema failure")):
                    with self.assertRaisesRegex(ValueError, "synthetic schema failure") as caught:
                        Archive(Path(tmp) / "fixture.sqlite")
                self.assert_close_failure_note(caught.exception)
        finally:
            sqlite3.Connection.close(conn)


if __name__ == "__main__":
    unittest.main()
