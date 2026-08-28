#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reasoning_curriculum import run_phase


if __name__ == "__main__":
    result = run_phase(
        phase_number=4,
        provider="local",
        model="fast",
        trace_path=ROOT / "runs" / "phase4_trace.json",
        html_path=ROOT / "visuals" / "PHASE4_VISUAL.html",
        progress_path=ROOT / "PROGRESS.html",
    )
    print(f"phase={result['phase']}")
    print(f"concept={result['concept']}")
    print(f"llm_call_count={result['summary']['llm_call_budget_used']}")
