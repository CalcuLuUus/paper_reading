"""Background worker entrypoint."""

from __future__ import annotations

import argparse
import time

from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.clients.llm import OpenAICompatibleClient
from paper_analyzer.config import get_settings
from paper_analyzer.database import get_session_factory, init_database
from paper_analyzer.services.analysis import PaperAnalyzer
from paper_analyzer.services.jobs import JobProcessor, JobService


def run_worker(once: bool = False) -> None:
    settings = get_settings()
    init_database()
    session_factory = get_session_factory()
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
                if once:
                    return
                time.sleep(settings.worker_poll_interval_sec)
                continue
            processor.process(job)
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

