"""Harness-friendly command line entry point."""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .scan.artifacts import company_record, write_bundle, write_json
from .scan.crawler import Client, crawl, normalize
from .scan.discovery import discover
from .llm import REPUTATION_MODEL, chat_model
from .models import Config, SCHEMA_VERSION
from .scan.social import collect_profiles, discover_profiles
from .scan.technical import reports
from .scan.accessibility import summarize as accessibility_summary
from .scan.copy_scores import score_pages as copy_scores
from .dimensions import DIMENSIONS


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def parser(json_errors=False):
    class ArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            if json_errors:
                print(json.dumps({"status": "ERROR", "error": message}))
                raise SystemExit(2)
            super().error(message)

    p = ArgumentParser(prog="companyscan", description="Collect public website evidence without an LLM.")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("scan", "discover", "crawl", "technical", "social", "accessibility", "batch"):
        cmd = sub.add_parser(name)
        cmd.add_argument("target", help="Website URL/domain" if name != "batch" else "Input CSV path")
        cmd.add_argument("--json", action="store_true", help="Emit one JSON result on stdout")
        cmd.add_argument("--output", type=Path)
        cmd.add_argument("--max-pages", type=positive, default=50)
        cmd.add_argument("--max-depth", type=int, default=3)
        cmd.add_argument("--timeout", type=float, default=15)
        cmd.add_argument("--delay", type=float, default=0.25)
        cmd.add_argument("--max-bytes", type=positive, default=2_000_000)
        cmd.add_argument("--max-sitemaps", type=positive, default=20)
        cmd.add_argument("--max-urls", type=positive, default=10_000)
        cmd.add_argument("--allow-private", action="store_true", help="Allow trusted local/private test sites")
        cmd.add_argument("--collect-social", action="store_true", help="Attempt public HTML capture of discovered profiles")
        cmd.add_argument("--known-profile", action="append", default=[])
        cmd.add_argument("--company-name")
        cmd.add_argument("--icp", help="Ideal customer profile for llm_reputation buyer questions")
        cmd.add_argument("--location", help="City, State, Country for a local business (llm_reputation)")
        cmd.add_argument("--dimension", dest="dimensions", action="append", default=[], choices=list(DIMENSIONS),
                         help="Extra report dimension to collect (repeatable)")
        if name == "batch":
            cmd.add_argument("--domain-column", default="domain")
    rep = sub.add_parser("reputation", help="Ask an LLM about the company (needs pip install -e '.[llm]')")
    rep.add_argument("target", help="Website URL/domain")
    rep.add_argument("--json", action="store_true", help="Emit one JSON result on stdout")
    rep.add_argument("--output", type=Path)
    rep.add_argument("--model", default=REPUTATION_MODEL, help="LangChain provider:model, e.g. anthropic:claude-sonnet-5")
    rep.add_argument("--company-name")
    rep.add_argument("--icp", help="Ideal customer profile; buyer questions use it instead of the model's guess")
    rep.add_argument("--location", help="City, State, Country for a local business")
    rep.add_argument("--prompt", action="append", default=[], help="Buyer question to ask (repeatable); replaces generated ones")
    rep.add_argument("--prompts-file", type=Path, help="Buyer questions, one per line; # comments and blank lines ignored")
    rep.add_argument("--samples", type=positive, default=3, help="Times each question is asked")
    rep.add_argument("--num-prompts", type=positive, default=8, help="Buyer questions to generate when none are given")
    pdf = sub.add_parser("pdf", help="Render a bundle's analysis report.md as a designed PDF")
    pdf.add_argument("target", type=Path, help="Evidence bundle directory")
    pdf.add_argument("--json", action="store_true")
    return p


def directory_name(url):
    p = urlsplit(normalize(url))
    return p.netloc.replace(":", "_").replace("[", "").replace("]", "")


def run(args, target=None, output=None, progress=None):
    target = normalize(target or args.target)
    # Timestamped default so repeat crawls keep history; the manifest's created_at is the last-crawled date.
    output = output or args.output or Path("output") / f"{directory_name(target)}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output path must be an empty directory: {output}")
    config = Config(**{key: getattr(args, key) for key in Config.__dataclass_fields__})
    config.validate()
    client = Client(config)
    dimensions = list(dict.fromkeys(config.dimensions))
    steps = ["Discovering sitemaps", "Crawling pages", "Running technical checks",
             *(DIMENSIONS[name]["label"] for name in dimensions), "Writing bundle"]

    def stage(i):
        """Point client.progress at step i; progress(step, steps, label, done, total, unit) feeds the web UI."""
        def report(done=None, total=None, unit=""):
            if progress:
                progress(i + 1, len(steps), steps[i], done, total, unit)
        client.progress = report
        report()

    stage(0)
    discovery, robots = discover(client, target)
    # Discovery needs one HTML page to expose canonical links, feeds and profiles.
    if args.command == "discover":
        config.max_pages = 1
    stage(1)
    pages, skipped = crawl(client, target, robots, discovery["sitemap_urls"])
    discovery["html_signals"] = [{"url": p["url"], "canonical_url": p.get("canonical_url"), "feeds": p.get("feeds", []),
                                   "schema_types": p.get("json_ld", {}).get("types", [])} for p in pages]
    stage(2)
    profiles = discover_profiles(pages, args.known_profile)
    if config.collect_social:
        profiles = collect_profiles(client, profiles)
    technical = reports(client, discovery, robots, pages)
    technical["accessibility"] = accessibility_summary(pages, skipped)
    names = company_record(pages, args.company_name)["names"]
    brand = names[0]["value"] if names else urlsplit(target).hostname
    # Before write_bundle: adds page["copy_scores"] to each page file, plus the site summary.
    technical["copy-scores"] = copy_scores(pages, names[0]["value"] if names else None)
    for i, name in enumerate(dimensions, 3):
        stage(i)
        technical[name] = DIMENSIONS[name]["collect"](client, discovery, pages, brand)
    stage(len(steps) - 1)
    result = write_bundle(output, args.command, config, discovery, pages, skipped, technical, profiles, args.company_name)
    result["accessibility"] = {key: technical["accessibility"][key] for key in ("automated_status", "conformance_status", "pages_checked", "finding_count", "manual_review_required")}
    result["accessibility"]["report"] = str((output / "technical/accessibility.md").resolve())
    if args.command == "discover":
        result["discovery"] = discovery
    elif args.command == "technical":
        result["technical"] = technical
    elif args.command == "social":
        result["profiles"] = profiles
    elif args.command == "crawl":
        result["pages"] = [p["url"] for p in pages]
    return result


def reputation(args):
    from .dimensions.reputation import rank_reputation, write_bundle
    prompts = list(args.prompt)
    if args.prompts_file:
        lines = [line.strip() for line in args.prompts_file.read_text(encoding="utf-8").splitlines()]
        from_file = [line for line in lines if line and not line.startswith("#")]
        if not from_file:
            raise ValueError(f"No prompts in {args.prompts_file}")
        prompts += from_file
    output = args.output or Path("output") / f"{directory_name(args.target)}-reputation"
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output path must be an empty directory: {output}")
    try:
        result = rank_reputation(args.target, chat_model(args.model), args.company_name,
                                 prompts or None, args.samples, args.num_prompts, icp=args.icp, location=args.location)
    except Exception as exc:  # Provider/auth/network errors surface as the standard error shape.
        raise ValueError(f"LLM request failed: {exc}") from exc
    return write_bundle(output, result, args.model)


def batch(args):
    output = args.output or Path("output") / Path(args.target).stem
    # Validate before any network requests or per-row output.
    with Path(args.target).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if args.domain_column not in (reader.fieldnames or []):
            raise ValueError(f"CSV is missing column: {args.domain_column}")
        rows = list(reader)
    results = []
    for number, row in enumerate(rows, 2):
        target = (row.get(args.domain_column) or "").strip()
        try:
            if not target:
                raise ValueError("Empty domain")
            result = run(args, target, output / f"{number - 1:05d}-{directory_name(target)}")
            results.append({"row": number, "domain": target, **result})
        except (ValueError, OSError) as exc:
            results.append({"row": number, "domain": target, "status": "ERROR", "error": str(exc)})
    result = {"schema_version": SCHEMA_VERSION, "rows": results}
    index = output / "batch.json"
    if index.exists():
        raise ValueError(f"Batch index already exists: {index}")
    write_json(index, result)
    return {"batch": str(index.resolve()), **result}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parser("--json" in argv).parse_args(argv)
    try:
        if args.command == "pdf":
            from .report.pdf import render_pdf
            result = {"status": "COMPLETE", "pdf": str(render_pdf(args.target).resolve())}
            print(json.dumps(result) if args.json else result["pdf"])
            return 0
        if args.command == "reputation":
            result = reputation(args)
        else:
            Config(**{key: getattr(args, key) for key in Config.__dataclass_fields__}).validate()
            if args.command == "batch" and (args.output or Path("output") / Path(args.target).stem).joinpath("batch.json").exists():
                raise ValueError("Batch index already exists; use a new --output directory")
            result = batch(args) if args.command == "batch" else run(args)
    except (ValueError, OSError) as exc:
        if args.json:
            print(json.dumps({"status": "ERROR", "error": str(exc)}))
        else:
            print(f"companyscan: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result.get("manifest", result.get("batch")))
        if "accessibility" in result:
            a = result["accessibility"]
            print(f"Accessibility: {a['finding_count']} potential barriers on {a['pages_checked']} pages; WCAG conformance UNKNOWN. Manual review required.")
            print(a["report"])
    return 1 if result.get("status") == "PARTIAL" or any(r["status"] in {"ERROR", "PARTIAL"} for r in result.get("rows", [])) else 0
