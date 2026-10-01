"""Logging for the CLI, the web app and the Huey worker. Locally each process appends to logs/<name>.log (rotating),
with full tracebacks, so a run can be scanned for bugs afterwards. On a server (DATABASE_URL set) it all goes to stderr
for the host to collect. Nothing is written to stdout, so `--json` output stays exactly one JSON object.

COMPANYSCAN_LOG_DIR: the folder (default ./logs), or "off" (tests). COMPANYSCAN_LOG_LEVEL: DEBUG, INFO (default)…"""
import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s [pid %(process)d %(threadName)s] %(name)s:%(lineno)d %(message)s"
MAX_BYTES, BACKUPS = 10 * 1024 * 1024, 5
# ponytail: runserver's autoreloader runs two processes on web.log; rotation can race between them at MAX_BYTES.
NOISY = ("httpx", "httpcore", "openai", "anthropic", "urllib3", "asyncio", "langchain", "langsmith", "huey.consumer.Scheduler")
MARK = "_companyscan"  # Set on our handlers, so setup() replaces them instead of stacking.
PREVIOUS = (sys.excepthook, threading.excepthook)  # The default hooks ours hand on to after logging.


def handler(name):
    """Where this process logs: logs/<name>.log locally, stderr on a server, nowhere when the folder is "off"."""
    where = os.environ.get("COMPANYSCAN_LOG_DIR", "")
    if where == "off":
        return None
    if os.environ.get("DATABASE_URL") and not where:
        return logging.StreamHandler(sys.stderr)
    folder = Path(where or "logs")
    folder.mkdir(parents=True, exist_ok=True)
    return logging.handlers.RotatingFileHandler(folder / f"{name}.log", maxBytes=MAX_BYTES, backupCount=BACKUPS,
                                                encoding="utf-8")


def setup(name, console=False):
    """Configure the root logger for this process (name: cli, web or worker). console: also show warnings on stderr,
    for the web and worker processes whose terminals are watched. Safe to call more than once."""
    reset()
    root = logging.getLogger()
    level = logging.getLevelName(os.environ.get("COMPANYSCAN_LOG_LEVEL", "INFO").upper())
    level = level if isinstance(level, int) else logging.INFO
    handlers = [h for h in (handler(name),) if h]
    if console and not isinstance(handlers[0] if handlers else None, logging.StreamHandler):
        handlers.append(logging.StreamHandler(sys.stderr))
        handlers[-1].setLevel(logging.WARNING)
    for h in handlers:
        h.setFormatter(logging.Formatter(FORMAT))
        setattr(h, MARK, True)
        root.addHandler(h)
    root.setLevel(level)
    for noisy in NOISY:  # Their per-request lines would bury ours; their warnings still come through.
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))
    sys.excepthook, threading.excepthook = crashed, thread_crashed
    logging.captureWarnings(True)


def reset():
    """Remove the handlers setup() added."""
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, MARK, False)]:
        root.removeHandler(h)
        h.close()


def crashed(kind, value, tb):
    if not issubclass(kind, KeyboardInterrupt):
        logging.getLogger("companyscan").critical("Uncaught exception", exc_info=(kind, value, tb))
    PREVIOUS[0](kind, value, tb)


def thread_crashed(args):
    if not issubclass(args.exc_type, SystemExit):
        name = args.thread.name if args.thread else "a thread"
        logging.getLogger("companyscan").critical(f"Uncaught exception in {name}",
                                                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    PREVIOUS[1](args)
