import hashlib
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from companyscan.report import analyze as analyze_mod, pdf as pdf_mod
from companyscan.report.analyze import analyze, latest, verify
from companyscan.report.pdf import badges, render_pdf


def make_bundle(root, files):
    root = Path(root)
    artifacts = []
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
        artifacts.append({"path": name, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    (root / "manifest.json").write_text(json.dumps({"artifacts": artifacts}))
    return root


def done(stdout="", stderr=""):
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr=stderr)


class VerifyTest(unittest.TestCase):
    def test_intact_modified_missing_and_escaping_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = make_bundle(tmp, {"a.json": "{}", "b.json": "[]", "c.json": "1"})
            self.assertEqual(verify(bundle), [])
            (bundle / "b.json").write_text("changed")
            (bundle / "c.json").unlink()
            manifest = json.loads((bundle / "manifest.json").read_text())
            manifest["artifacts"].append({"path": "../outside.json", "sha256": "0"})
            (bundle / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(verify(bundle), ["modified: b.json", "missing: c.json", "missing: ../outside.json"])


class LatestTest(unittest.TestCase):
    def test_newest_report_or_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(latest(tmp, "report.md"))
            old, new = Path(tmp, "analysis/2026-01/report.md"), Path(tmp, "analysis/2026-02/report.md")
            for path in (old, new):
                path.parent.mkdir(parents=True)
                path.write_text("# R")
            os.utime(old, (time.time() - 100, time.time() - 100))
            self.assertEqual(latest(tmp, "report.md"), new)


class StubReport:
    """Stands in for chat_model(...).with_structured_output(...): records the messages, returns a fixed reply."""
    def __init__(self, reply):
        self.reply, self.messages, self.method = reply, None, None

    def with_structured_output(self, schema, method=None):
        self.method = method
        return self

    def invoke(self, messages):
        self.messages = messages
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


GOOD = {"report_md": "# Report", "analysis": {"findings": [{"id": "F1", "verdict": "PASS", "title": "Clear"}]}}


class AnalyzeTest(unittest.TestCase):
    def run_analyze(self, bundle, reply=GOOD):
        stub = StubReport(reply)
        with patch.object(analyze_mod, "chat_model", return_value=stub) as chat:
            return analyze(bundle), stub, chat

    def test_writes_report_and_stamped_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = make_bundle(tmp, {"a.json": "{}"})
            report, stub, chat = self.run_analyze(bundle)
            self.assertEqual(report, (bundle / "analysis/report.md").resolve())
            self.assertEqual(report.read_text(), "# Report")
            analysis = json.loads((bundle / "analysis/analysis.json").read_text())
            self.assertEqual(analysis["source_manifest"]["sha256"], hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest())
            self.assertEqual(analysis["findings"][0]["id"], "F1")
            self.assertEqual(chat.call_args[0][0], analyze_mod.REPORT_MODEL)
            self.assertEqual(stub.method, "json_mode")
            system, user = stub.messages[0][1], stub.messages[1][1]
            self.assertIn("name: footprint-analyze", system)  # The skill and its rubrics are the instructions.
            self.assertIn("# references/analysis-rubric.md", system)
            self.assertNotIn("# references/security.md", system)  # Dimension rubric only when that file is present.
            self.assertIn("passed size/SHA-256 verification", user)

    def test_integrity_failure_is_told_to_the_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = make_bundle(tmp, {"a.json": "{}"})
            (bundle / "a.json").write_text("tampered")
            _, stub, _ = self.run_analyze(bundle)
            self.assertIn("integrity check FAILED", stub.messages[1][1])
            self.assertIn("modified: a.json", stub.messages[1][1])

    def test_rerun_keeps_the_earlier_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = make_bundle(tmp, {})
            first, _, _ = self.run_analyze(bundle)
            second, _, _ = self.run_analyze(bundle, {**GOOD, "report_md": "# Newer"})
            self.assertEqual(first.read_text(), "# Report")
            self.assertEqual(second.parent.parent, first.parent)  # analysis/<UTC stamp>/report.md
            self.assertEqual(latest(bundle.resolve(), "report.md"), second)

    def test_bad_replies_and_provider_errors_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = make_bundle(tmp, {})
            for reply, message in (({"report_md": " ", "analysis": {}}, "did not return"), (None, "did not return"),
                                   ({"report_md": "# R", "analysis": []}, "did not return"),
                                   (RuntimeError("auth expired"), "auth expired")):
                with self.assertRaisesRegex(ValueError, message):
                    self.run_analyze(bundle, reply)
            self.assertFalse((bundle / "analysis").exists())


class DigestTest(unittest.TestCase):
    def test_strips_shared_lines_and_fits_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            nav = "Home\nPricing\nContact"
            files = {f"pages/000{i}.json": json.dumps({"url": f"https://a.test/{i}", "title": f"Page {i}",
                                                       "visible_text": f"{nav}\nUnique copy {i}\n" + str(i) * 5000})
                     for i in range(1, 5)}
            bundle = make_bundle(tmp, {**files, "technical/schema.json": "y" * 50_000})
            text = analyze_mod.digest(bundle, budget=12_000)
            self.assertLess(len(text), 13_000)
            self.assertIn("Unique copy 3", text)
            self.assertNotIn("Pricing", text)  # On every page: navigation, not copy.
            self.assertIn("4 had visible_text trimmed", text)
            self.assertIn("[trimmed:", text)  # schema.json capped too.


class BadgesTest(unittest.TestCase):
    def test_wraps_whole_verdicts_in_body_text_only(self):
        html = '<html><head><title>PASS</title></head><body class="FAIL"><p>PASS and WARNING, not PASSWORD or PRE-FAIL</p></body>'
        out = badges(html)
        self.assertIn("<title>PASS</title>", out)
        self.assertIn('class="FAIL"', out)
        self.assertIn('<span class="v v-PASS">PASS</span> and <span class="v v-WARNING">WARNING</span>', out)
        self.assertIn("PASSWORD or PRE-FAIL", out)


class RenderPdfTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundle = Path(self.tmp.name)
        self.md = self.bundle / "analysis/report.md"
        self.md.parent.mkdir()
        self.md.write_text("intro\n# Acme Report\n\nStatus: FAIL\n")

    def tearDown(self):
        self.tmp.cleanup()

    def tools(self):
        return patch.multiple(pdf_mod, CHROMES=["/bin/chrome"]), patch.object(pdf_mod.shutil, "which", return_value="/bin/x")

    def test_missing_report_or_tools_raise(self):
        with self.assertRaisesRegex(ValueError, "No analysis/report.md"):
            render_pdf(self.bundle / "nothing")
        with patch.object(pdf_mod.shutil, "which", return_value=None), patch.multiple(pdf_mod, CHROMES=[""]):
            with self.assertRaisesRegex(ValueError, "needs pandoc"):
                render_pdf(self.bundle)

    def test_renders_with_title_and_badges(self):
        def fake_run(cmd, **kwargs):
            Path(cmd[cmd.index("-o") + 1]).write_text("<html><body><p>Status: FAIL</p></body></html>")
            return done()

        chrome, which = self.tools()
        with chrome, which, patch.object(pdf_mod.subprocess, "run", side_effect=fake_run) as run, \
                patch.object(pdf_mod, "print_pdf") as printer:
            relative = Path(os.path.relpath(self.bundle))  # CLI users pass relative bundle paths.
            self.assertEqual(render_pdf(relative), self.md.resolve().with_suffix(".pdf"))
        self.assertIn("pagetitle=Acme Report", run.call_args[0][0])
        md = self.md.resolve()
        printer.assert_called_once_with("/bin/chrome", md.with_suffix(".html"), md.with_suffix(".pdf"))
        self.assertIn('<span class="v v-FAIL">FAIL</span>', self.md.with_suffix(".html").read_text())

    def test_pandoc_failures_become_value_errors(self):
        errors = [(subprocess.CalledProcessError(1, ["/usr/bin/pandoc"], stderr=b"bad markdown"), "pandoc failed: bad markdown"),
                  (subprocess.TimeoutExpired(["/usr/bin/pandoc"], 120), "pandoc timed out")]
        for error, message in errors:
            chrome, which = self.tools()
            with chrome, which, patch.object(pdf_mod.subprocess, "run", side_effect=error):
                with self.assertRaisesRegex(ValueError, message):
                    render_pdf(self.bundle)


class FakeChrome:
    """Popen stand-in: optionally writes the PDF, and like macOS headless Chrome may never exit on its own."""

    def __init__(self, cmd, write=True, exits=False, **kwargs):
        self.cmd, self.killed, self.returncode = cmd, False, (1 if exits else None)
        if write:
            Path(next(a for a in cmd if a.startswith("--print-to-pdf=")).split("=", 1)[1]).write_bytes(b"%PDF")

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, -9

    def wait(self):
        return self.returncode


class PrintPdfTest(unittest.TestCase):
    def run_chrome(self, timeout=5, **behaviour):
        with tempfile.TemporaryDirectory() as tmp:
            html, pdf = Path(tmp, "r.html"), Path(tmp, "r.pdf")
            html.write_text("<p>x</p>")
            pdf.write_bytes(b"stale")  # An old PDF must never count as the new one.
            procs = []

            def popen(cmd, **kwargs):
                procs.append(FakeChrome(cmd, **behaviour))
                return procs[0]

            with patch.object(pdf_mod.subprocess, "Popen", side_effect=popen), patch.object(pdf_mod.time, "sleep"):
                try:
                    pdf_mod.print_pdf("/bin/chrome", html, pdf, timeout=timeout)
                    return pdf.read_bytes(), procs[0]
                except ValueError as exc:
                    return exc, procs[0]

    def test_finished_file_returns_and_kills_lingering_chrome(self):
        data, proc = self.run_chrome()
        self.assertEqual(data, b"%PDF")
        self.assertTrue(proc.killed)
        self.assertIn("--no-pdf-header-footer", proc.cmd)
        self.assertTrue(any(a.startswith("--user-data-dir=") for a in proc.cmd))

    def test_exit_without_pdf_and_timeout_raise(self):
        error, _ = self.run_chrome(write=False, exits=True)
        self.assertRegex(str(error), "exited .* without writing")
        error, proc = self.run_chrome(write=False, timeout=0)
        self.assertRegex(str(error), "timed out")
        self.assertTrue(proc.killed)

if __name__ == "__main__":
    unittest.main()
