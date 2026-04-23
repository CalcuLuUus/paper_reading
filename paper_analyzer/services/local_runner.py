"""Local polling runner for no-public-webhook environments."""

from __future__ import annotations

import argparse
import time
from collections import Counter
from datetime import datetime

from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.config import get_settings
from paper_analyzer.database import get_session_factory, init_database
from paper_analyzer.services.jobs import LocalPollingScanner


def run_local_runner(once: bool = False) -> None:
    settings = get_settings()
    init_database()
    session_factory = get_session_factory()
    print(
        f"[{_timestamp()}] local polling scanner started "
        f"(interval={settings.local_poll_interval_sec:.0f}s, run_mode={settings.run_mode})",
        flush=True,
    )
    while True:
        session = session_factory()
        try:
            scanner = LocalPollingScanner(session, settings, FeishuClient(settings))
            results = scanner.scan()
            _print_scan_summary(results)
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

def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _print_scan_summary(results) -> None:
    counts = Counter(result.status for result in results)
    summary = (
        f"records={len(results)} "
        f"queued={counts.get('queued', 0)} "
        f"duplicate={counts.get('duplicate', 0)} "
        f"skipped={counts.get('skipped', 0)} "
        f"failed={counts.get('failed', 0)}"
    )
    print(f"[{_timestamp()}] local polling scan finished: {summary}", flush=True)


if __name__ == "__main__":
    main()
