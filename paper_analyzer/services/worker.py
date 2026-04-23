"""Background worker supervisor and child worker entrypoint."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

from paper_analyzer.clients.feishu import FeishuClient
from paper_analyzer.clients.llm import OpenAICompatibleClient
from paper_analyzer.config import get_settings
from paper_analyzer.database import get_session_factory, init_database
from paper_analyzer.services.analysis import PaperAnalyzer
from paper_analyzer.services.jobs import JobProcessor, JobService

MAX_WORKERS = 3
RESPAWN_BACKOFF_SEC = 1.0


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(message: str) -> None:
    print(f"[{_timestamp()}] {message}", flush=True)


def _validate_worker_count(worker_count: int) -> int:
    if worker_count < 1 or worker_count > MAX_WORKERS:
        raise ValueError(f"worker count must be between 1 and {MAX_WORKERS}")
    return worker_count


def _child_label(worker_id: int) -> str:
    return f"worker[{worker_id}] pid={os.getpid()}"


def run_single_worker(*, worker_id: int = 1, once: bool = False) -> None:
    settings = get_settings()
    init_database()
    session_factory = get_session_factory()
    label = _child_label(worker_id)
    _log(
        f"{label} started "
        f"(poll_interval={settings.worker_poll_interval_sec:.0f}s, run_mode={settings.run_mode})"
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
                _log(f"{label} idle: no queued jobs")
                if once:
                    return
                time.sleep(settings.worker_poll_interval_sec)
                continue
            _log(
                f"{label} picked job "
                f"id={job.id} record_id={job.record_id} source_hash={job.source_hash} "
                f"trigger_mode={job.trigger_mode} force_rerun={job.force_rerun}"
            )
            processor.process(job)
            session.refresh(job)
            if job.status == "completed":
                _log(f"{label} finished job id={job.id} status={job.status}")
            else:
                _log(
                    f"{label} finished job id={job.id} "
                    f"status={job.status} error={job.error or ''}"
                )
            if once:
                return
        finally:
            session.close()


def run_supervisor(*, worker_count: int, once: bool = False) -> None:
    settings = get_settings()
    init_database()
    worker_count = _validate_worker_count(worker_count)
    _log(
        f"supervisor started "
        f"(workers={worker_count}, max_workers={MAX_WORKERS}, run_mode={settings.run_mode})"
    )

    shutting_down = False
    children: dict[int, subprocess.Popen[str]] = {}

    def handle_shutdown(signum, _frame) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        _log(f"supervisor received signal {signum}, shutting down")

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    def spawn_child(worker_id: int, *, respawn: bool = False) -> None:
        cmd = [
            sys.executable,
            "-m",
            "paper_analyzer.services.worker",
            "--child-worker",
            "--worker-id",
            str(worker_id),
        ]
        if once:
            cmd.append("--once")
        process = subprocess.Popen(cmd, cwd=os.getcwd(), text=True)
        children[worker_id] = process
        action = "respawned child" if respawn else "spawned child"
        _log(f"supervisor {action} worker_id={worker_id} pid={process.pid}")

    for worker_id in range(1, worker_count + 1):
        spawn_child(worker_id)

    try:
        while children:
            for worker_id, process in list(children.items()):
                return_code = process.poll()
                if return_code is None:
                    continue
                children.pop(worker_id, None)
                _log(
                    f"supervisor observed child exit "
                    f"worker_id={worker_id} pid={process.pid} exit_code={return_code}"
                )
                if shutting_down:
                    continue
                if once:
                    continue
                time.sleep(RESPAWN_BACKOFF_SEC)
                spawn_child(worker_id, respawn=True)

            if shutting_down:
                break
            time.sleep(0.5)
    finally:
        shutting_down = True
        for worker_id, process in list(children.items()):
            if process.poll() is None:
                _log(f"supervisor terminating child worker_id={worker_id} pid={process.pid}")
                process.terminate()
        for worker_id, process in list(children.items()):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _log(f"supervisor killing unresponsive child worker_id={worker_id} pid={process.pid}")
                process.kill()
                process.wait(timeout=5)
        _log("supervisor shutdown complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Feishu paper analysis worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    parser.add_argument(
        "--workers",
        type=int,
        help=f"Number of worker child processes to run (1-{MAX_WORKERS}). Defaults to WORKER_CONCURRENCY or 3.",
    )
    parser.add_argument("--child-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-id", type=int, default=1, help=argparse.SUPPRESS)
    args = parser.parse_args()

    settings = get_settings()
    configured_workers = args.workers or settings.worker_concurrency
    configured_workers = _validate_worker_count(configured_workers)

    if args.child_worker:
        run_single_worker(worker_id=args.worker_id, once=args.once)
        return

    run_supervisor(worker_count=configured_workers, once=args.once)


if __name__ == "__main__":
    main()
