from __future__ import annotations

from arq import run_worker

from novel_agent.worker.settings import WorkerSettings


if __name__ == "__main__":
    run_worker(WorkerSettings)
