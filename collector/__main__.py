"""Command line interface.

    python -m collector collect   # fetch and classify
    python -m collector build     # generate the site and the feeds
    python -m collector run       # both
    python -m collector check     # validate the configuration, no network
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from . import adapters, config, feeds, pipeline, site
from .classify import Classifier
from .store import Store
from .util import parse_date

log = logging.getLogger("collector")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stderr,
    )


def _opt(args: argparse.Namespace, name: str, fallback):
    """Read a global flag.

    Global flags are declared on a shared parent parser with SUPPRESS defaults so
    they work either before or after the subcommand; absent ones simply are not
    set on the namespace, hence the fallback.
    """
    return getattr(args, name, fallback)


def _load(args) -> config.Config:
    return config.load(_opt(args, "root", "."), _opt(args, "config_dir", None))


def cmd_collect(args) -> int:
    cfg = _load(args)
    end = parse_date(args.date) if args.date else None
    result = pipeline.collect(cfg, days=args.days, end=end,
                              only=args.source or None, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


def cmd_build(args) -> int:
    cfg = _load(args)
    classifier = Classifier(cfg.classification)
    templates_dir = Path(_opt(args, "templates", "templates"))
    if not templates_dir.is_absolute():
        templates_dir = cfg.root / templates_dir

    def catalogue_builder(items, output_dir):
        return feeds.build_all(cfg, items, classifier, output_dir)

    result = site.build(cfg, classifier, templates_dir=templates_dir,
                        catalogue_builder=catalogue_builder)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


def cmd_run(args) -> int:
    code = cmd_collect(args)
    return code or cmd_build(args)


def cmd_check(args) -> int:
    cfg = _load(args)
    classifier = Classifier(cfg.classification)
    problems: list[str] = []
    for source in cfg.all_sources:
        try:
            adapters.get(source["adapter"])
        except KeyError as exc:
            problems.append(str(exc))
        if source.get("enabled", True) and source in cfg.sources:
            options = source.get("options") or {}
            if source["adapter"] == "rss" and not options.get("urls"):
                problems.append(f"{source['id']}: rss adapter with no 'urls'")
            if source["adapter"] == "boe_sumario" and not options.get("url_template"):
                problems.append(f"{source['id']}: missing 'url_template'")
            if source["adapter"] == "opendatasoft" and not options.get("dataset"):
                problems.append(f"{source['id']}: missing 'dataset'")
    store = Store(cfg.data_dir)
    days = store.available_days()
    print(json.dumps({
        "enabled_sources": [s["id"] for s in cfg.sources],
        "pending_sources": [s["id"] for s in cfg.sources_doc.get("pending_sources", [])],
        "topics": [t["id"] for t in classifier.topic_meta()],
        "min_score": classifier.min_score,
        "stored_days": len(days),
        "latest_day": days[0] if days else None,
        "base_url": cfg.base_url,
        "problems": problems,
    }, ensure_ascii=False, indent=1))
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI.

    `--root`, `--config-dir`, `--templates` and `-v` live on a shared parent
    parser attached to both the top level and every subcommand, so
    `collector -v collect` and `collector collect -v` both work.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS,
                        help="repository root")
    common.add_argument("--config-dir", default=argparse.SUPPRESS,
                        help="configuration directory")
    common.add_argument("--templates", default=argparse.SUPPRESS,
                        help="templates directory")
    common.add_argument("-v", "--verbose", action="store_true",
                        default=argparse.SUPPRESS, help="debug logging")

    parser = argparse.ArgumentParser(
        prog="collector", description=__doc__, parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_collect_options(target: argparse.ArgumentParser) -> None:
        target.add_argument("--days", type=int, default=None,
                            help="how many days back")
        target.add_argument("--date", default=None, help="end date (YYYY-MM-DD)")
        target.add_argument("--source", action="append",
                            help="limit to one source (repeatable)")
        target.add_argument("--dry-run", action="store_true",
                            help="do not write to data/")

    collect = sub.add_parser("collect", parents=[common],
                             help="fetch and classify provisions")
    add_collect_options(collect)
    collect.set_defaults(func=cmd_collect)

    build = sub.add_parser("build", parents=[common],
                           help="generate the site and the feeds")
    build.set_defaults(func=cmd_build)

    run = sub.add_parser("run", parents=[common], help="collect + build")
    add_collect_options(run)
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check", parents=[common],
                           help="validate the configuration")
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(_opt(args, "verbose", False))
    try:
        return args.func(args)
    except config.ConfigError as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
