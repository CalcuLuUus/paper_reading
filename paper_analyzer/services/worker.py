"""Background worker entrypoint."""

from __future__ import annotations

import argparse
import time
from datetime import datetime

from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.clients.llm import OpenAICompatibleClient
from paper_analyzer.config import get_settings
from paper_analyzer.database import get_session_factory, init_database
from paper_analyzer.services.analysis import PaperAnalyzer
from paper_analyzer.services.jobs import JobProcessor, JobService


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_worker(once: bool = False) -> None:
    settings = get_settings()
    init_database()
    session_factory = get_session_factory()
    print(
        f"[{_timestamp()}] worker started "
        f"(poll_interval={settings.worker_poll_interval_sec:.0f}s, run_mode={settings.run_mode})",
        flush=True,
    )
    while True:
        session = session_factory()
        try:
            feishu_client = FeishuClient(settings)
            llm_client = OpenAICompatibleClient(settings)
            analyzer = PaperAnalyzer(settings, llm_client)
            job_service = JobService(session, settings, feishu_client)
            processor = JobProcessor(session, settings, feishu_client, analyzer)
            job = job_service.claim_next_job()
            if job is None:
                print(f"[{_timestamp()}] worker idle: no queued jobs", flush=True)
                if once:
                    return
                time.sleep(settings.worker_poll_interval_sec)
                continue
            print(
                f"[{_timestamp()}] worker picked job "
                f"id={job.id} record_id={job.record_id} source_hash={job.source_hash} "
                f"trigger_mode={job.trigger_mode} force_rerun={job.force_rerun}",
                flush=True,
            )
            processor.process(job)
            session.refresh(job)
            if job.status == "completed":
                print(
                    f"[{_timestamp()}] worker finished job "
                    f"id={job.id} status={job.status}",
                    flush=True,
                )
            else:
                print(
                    f"[{_timestamp()}] worker finished job "
                    f"id={job.id} status={job.status} error={job.error or ''}",
                    flush=True,
                )
            if once:
                return
        finally:
            session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Feishu paper analysis worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    args = parser.parse_args()
    run_worker(once=args.once)


if __name__ == "__main__":
    main()
