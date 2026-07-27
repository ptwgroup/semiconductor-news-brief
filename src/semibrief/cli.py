from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings
from .database import Database
from .mailer import send_brief
from .models import Brief
from .pipeline import Pipeline
from .util import parse_datetime


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="semibrief")
    result.add_argument("--config-dir", type=Path, default=None)
    subcommands = result.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--date", help="ISO-8601 instant; defaults to now")
    subcommands.add_parser("health")
    subcommands.add_parser("send-test")
    feedback = subcommands.add_parser("feedback")
    feedback.add_argument("fingerprint")
    feedback.add_argument(
        "preference",
        choices=["more_like_this", "less_like_this", "irrelevant"],
    )
    return result


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env(args.config_dir)
    try:
        if args.command == "run":
            now = parse_datetime(args.date) if args.date else datetime.now(UTC)
            output = Pipeline(settings).run(now, bool(args.dry_run))
            print(output)
        elif args.command == "health":
            database = Database(settings.database_path)
            database.initialize()
            print("healthy")
        elif args.command == "send-test":
            now = datetime.now(UTC)
            brief = Brief(
                subject="SemiBrief SMTP test",
                plain_text="SemiBrief SMTP test succeeded.",
                html="<p>SemiBrief SMTP test succeeded.</p>",
                articles=[],
                window_start=now,
                window_end=now,
                sources_monitored=0,
                articles_reviewed=0,
            )
            send_brief(brief)
            print("test email accepted by SMTP")
        elif args.command == "feedback":
            database = Database(settings.database_path)
            database.initialize()
            database.set_feedback(args.fingerprint, args.preference)
            print("feedback saved")
    except Exception as exc:
        logging.getLogger(__name__).error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
