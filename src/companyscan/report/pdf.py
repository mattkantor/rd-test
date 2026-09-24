"""Designed PDF: newest report.md -> pandoc HTML styled by views/report/report.css -> headless Chrome print."""
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .analyze import latest

CSS = Path(__file__).resolve().parents[1] / "views" / "report" / "report.css"
CHROMES = [os.environ.get("CHROME", ""), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium", "google-chrome", "chromium", "chromium-browser"]
VERDICT = re.compile(r"(?<![\w-])(PASS|WARNING|FAIL|UNKNOWN|HIGH|MEDIUM|LOW)(?![\w-])")


def badges(html):
    """Wrap verdict/severity words in body text nodes so the stylesheet can colour them."""
    head, sep, body = html.partition("<body")
    body = re.sub(r">([^<]+)<", lambda m: ">" + VERDICT.sub(r'<span class="v v-\1">\1</span>', m.group(1)) + "<", body)
    return head + sep + body


def render_pdf(bundle):
    bundle = Path(bundle).resolve()  # Chrome needs an absolute file:// URI.
    md = latest(bundle, "report.md")
    if not md:
        raise ValueError(f"No analysis/report.md in {bundle}; generate the report first")
    chrome = next((c for c in CHROMES if c and (Path(c).is_file() or shutil.which(c))), None)
    if not shutil.which("pandoc") or not chrome:
        raise ValueError("PDF rendering needs pandoc and Chrome/Chromium (set CHROME=/path/to/chrome)")
    title = next((line[2:].strip() for line in md.read_text(encoding="utf-8").splitlines() if line.startswith("# ")), "Report")
    html, pdf = md.with_suffix(".html"), md.with_suffix(".pdf")
    try:
        subprocess.run(["pandoc", str(md), "-s", "--embed-resources", "--css", str(CSS),
                        "--metadata", f"pagetitle={title}", "-o", str(html)], check=True, capture_output=True, timeout=120)
        html.write_text(badges(html.read_text(encoding="utf-8")), encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"pandoc failed: {exc.stderr.decode('utf-8', 'replace')[-500:]}") from None
    except subprocess.TimeoutExpired:
        raise ValueError("pandoc timed out") from None
    print_pdf(chrome, html, pdf)
    return pdf


def print_pdf(chrome, html, pdf, timeout=180):
    # Headless Chrome on macOS can write the PDF and then never exit, so wait for a finished file, not the process.
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as profile:  # Separate profile so it doesn't attach to a running Chrome.
        proc = subprocess.Popen([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
                                 f"--print-to-pdf={pdf}", html.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline, size = time.monotonic() + timeout, -1
        try:
            while time.monotonic() < deadline:
                current = pdf.stat().st_size if pdf.exists() else -1
                if current > 0 and current == size:
                    return
                if proc.poll() is not None and current <= 0:
                    raise ValueError(f"Chrome exited ({proc.returncode}) without writing {pdf.name}")
                size = current
                time.sleep(1)
            raise ValueError("Chrome timed out printing the PDF")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
