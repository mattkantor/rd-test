import logging
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from companyscan import logs


def fail():
    try:
        raise KeyError("inner")
    except KeyError as exc:
        raise ValueError("outer") from exc


class LogsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hooks = sys.excepthook, threading.excepthook
        self.handlers = logging.getLogger().handlers[:]  # Whatever the test run configured (manage.py: silent).

    def tearDown(self):
        logs.reset()
        logging.getLogger().handlers[:] = self.handlers
        sys.excepthook, threading.excepthook = self.hooks
        self.tmp.cleanup()

    def env(self, **values):
        return patch.dict(os.environ, values)

    def test_writes_a_file_per_process_with_full_tracebacks(self):
        with self.env(COMPANYSCAN_LOG_DIR=self.tmp.name), patch.dict(os.environ, {"DATABASE_URL": ""}):
            logs.setup("cli")
            try:
                fail()
            except ValueError:
                logging.getLogger("companyscan.test").exception("crawl failed for %s", "https://acme.test/")
        text = (Path(self.tmp.name) / "cli.log").read_text()
        self.assertIn("ERROR [pid", text)
        self.assertIn("companyscan.test:", text)
        self.assertIn("crawl failed for https://acme.test/", text)
        self.assertIn('raise KeyError("inner")', text)  # The whole chain, not just the last frame.
        self.assertIn("The above exception was the direct cause", text)
        self.assertIn("ValueError: outer", text)

    def test_setup_twice_does_not_duplicate_lines(self):
        with self.env(COMPANYSCAN_LOG_DIR=self.tmp.name):
            logs.setup("cli")
            logs.setup("cli")
            logging.getLogger("companyscan.test").info("once")
        self.assertEqual((Path(self.tmp.name) / "cli.log").read_text().count("once"), 1)

    def test_off_writes_nothing(self):
        with self.env(COMPANYSCAN_LOG_DIR="off"):
            logs.setup("cli")
            logging.getLogger("companyscan.test").error("nowhere")
        self.assertEqual(os.listdir(self.tmp.name), [])
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.env(COMPANYSCAN_LOG_DIR="off"):
            logs.setup("cli")
            logging.getLogger("companyscan.test").warning("quiet please")
        self.assertEqual(err.getvalue(), "")  # Not Python's last-resort stderr handler either.

    def test_server_logs_to_stderr_not_a_file(self):
        with self.env(DATABASE_URL="postgres://db", COMPANYSCAN_LOG_DIR=""):
            logs.setup("web")
        ours = [h for h in logging.getLogger().handlers if getattr(h, logs.MARK, False)]
        self.assertEqual([type(h) for h in ours], [logging.StreamHandler])
        self.assertIs(ours[0].stream, sys.stderr)

    def test_uncaught_exceptions_are_logged_with_their_trace(self):
        with self.env(COMPANYSCAN_LOG_DIR=self.tmp.name):
            logs.setup("worker")
            try:
                fail()
            except ValueError:
                with patch.object(logs, "PREVIOUS", (lambda *a: None, lambda a: None)):
                    sys.excepthook(*sys.exc_info())
            thread = threading.Thread(target=fail, name="questions-1")
            with patch.object(logs, "PREVIOUS", (lambda *a: None, lambda a: None)):
                thread.start()
                thread.join()
        text = (Path(self.tmp.name) / "worker.log").read_text()
        self.assertIn("CRITICAL", text)
        self.assertIn("Uncaught exception in questions-1", text)
        self.assertEqual(text.count("ValueError: outer"), 2)

    def test_level_and_noisy_libraries(self):
        with self.env(COMPANYSCAN_LOG_DIR=self.tmp.name, COMPANYSCAN_LOG_LEVEL="DEBUG"):
            logs.setup("cli")
            logging.getLogger("companyscan.test").debug("detail")
            logging.getLogger("httpx").info("HTTP Request: POST ...")
        text = (Path(self.tmp.name) / "cli.log").read_text()
        self.assertIn("detail", text)
        self.assertNotIn("HTTP Request", text)


class CliLogsTest(unittest.TestCase):
    def test_cli_errors_are_logged_with_their_trace(self):
        import contextlib
        import io
        from companyscan.cli import main
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"COMPANYSCAN_LOG_DIR": tmp, "DATABASE_URL": ""}):
            hooks, handlers = (sys.excepthook, threading.excepthook), logging.getLogger().handlers[:]
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["fixpack", str(Path(tmp) / "nope"), "--json"]), 2)
            finally:
                logs.reset()
                logging.getLogger().handlers[:] = handlers
                sys.excepthook, threading.excepthook = hooks
            text = (Path(tmp) / "cli.log").read_text()
        self.assertEqual(out.getvalue().count("\n"), 1)  # stdout is still exactly one JSON line.
        self.assertIn("companyscan fixpack", text)
        self.assertIn("Traceback", text)
        self.assertIn("generate the report first", text)
