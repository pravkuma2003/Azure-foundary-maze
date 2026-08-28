#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase7-monolithic-maze-agent"
RUNS_DIR = PROJECT_ROOT / "runs"
AGENT_NAME = "maze-monolithic-agent"


def run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=HOSTED_ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def write_report(report: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "cleanup_monolithic_agent.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def list_sessions() -> list[dict[str, Any]]:
    result = run(["azd", "ai", "agent", "sessions", "list", "--agent-name", AGENT_NAME, "--output", "json"])
    if result.returncode != 0:
        raise RuntimeError(f"session list failed: {result.stderr[-1000:]}")
    payload = json.loads(result.stdout or "{}")
    sessions = payload.get("data") or []
    return sessions if isinstance(sessions, list) else []


def delete_session(session_id: str) -> bool:
    result = run(
        [
            "azd",
            "ai",
            "agent",
            "sessions",
            "delete",
            session_id,
            "--agent-name",
            AGENT_NAME,
            "--no-prompt",
            "--output",
            "none",
        ],
        timeout=600,
    )
    return result.returncode == 0


def delete_agent() -> tuple[bool, str]:
    result = run(["azd", "ai", "agent", "delete", AGENT_NAME, "--no-prompt", "--output", "none"], timeout=600)
    return result.returncode == 0, result.stderr[-1000:]


def agent_exists() -> bool:
    result = run(["azd", "ai", "agent", "show", AGENT_NAME, "--output", "json"], timeout=300)
    return result.returncode == 0


def main() -> int:
    sessions = list_sessions()
    deleted = 0
    failed = 0
    statuses: dict[str, int] = {}
    for session in sessions:
        status = str(session.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        session_id = str(session.get("agent_session_id") or "")
        if not session_id:
            failed += 1
            continue
        if delete_session(session_id):
            deleted += 1
        else:
            failed += 1

    agent_deleted = False
    delete_error = ""
    if failed == 0:
        agent_deleted, delete_error = delete_agent()

    exists_after = agent_exists() if not agent_deleted else False
    report = {
        "agent": AGENT_NAME,
        "sessions_found": len(sessions),
        "session_status_counts": statuses,
        "sessions_deleted": deleted,
        "sessions_failed": failed,
        "agent_deleted": agent_deleted,
        "agent_exists_after": exists_after,
        "delete_error_tail": delete_error,
    }
    write_report(report)
    print(json.dumps(report, indent=2))
    return 0 if agent_deleted and not exists_after and failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
