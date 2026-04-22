"""Local polling runner for no-public-webhook environments."""

from __future__ import annotations

import argparse
import time

from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.config import get_settings
from paper_analyzer.database import get_session_factory, init_database
from paper_analyzer.services.jobs import LocalPollingScanner


def run_local_runner(once: bool = False) -> None:
    settings = get_settings()
    init_database()
    session_factory = get_session_factory()
    while True:
        session = session_factory()
        try:
            scanner = LocalPollingScanner(session, settings, FeishuClient(settings))
            scanner.scan()
            if once:
                return
        finally:
            session.close()
        time.sleep(settings.local_poll_interval_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local polling scanner.")
    parser.add_argument("--once", action="store_true", help="Scan the table once and exit.")
    args = parser.parse_args()
    run_local_runner(once=args.once)


if __name__ == "__main__":
    main()
