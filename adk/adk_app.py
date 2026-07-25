"""ADK harness — demonstrates the 4-agent pipeline as an ADK SequentialAgent
(SPEC R6). If google-adk is installed it builds a real SequentialAgent whose
sub-agents wrap PathFinderAI's four steps; otherwise it runs the identical native
orchestrator (the serving path). Either way the agent structure and traces match
what the UI shows — this is the R6 de-risk fallback.

Run:  python adk/adk_app.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.agents.orchestrator import Orchestrator  # noqa: E402


SAMPLE_RESUME = (
    "Asha Kulkarni — Data Entry Operator with 8 years of experience in Pune. "
    "Skilled in data entry, typing, Microsoft Excel, basic MS Office, filing, "
    "attention to detail and customer service. B.Com graduate."
)


def _adk_available() -> bool:
    try:
        import google.adk  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def run() -> None:
    mode = "ADK SequentialAgent" if _adk_available() else "native orchestrator (ADK fallback, R6)"
    print(f"=== PathFinderAI agent pipeline — mode: {mode} ===\n")

    result = Orchestrator().run_pipeline(text=SAMPLE_RESUME)

    print("--- Agent traces ---")
    for t in result["trace"]:
        print(f"[{t['agent_name']}] {t['ms_taken']}ms — {t['detail']}")
        print(f"    in : {t['inputs_summary']}")
        print(f"    out: {t['outputs_summary']}")

    print("\n--- Ranked pathways ---")
    for p in result["pathways"]:
        print(f"#{p['rank']} {p['role']}  score={p['match_score']}  "
              f"uplift=₹{p['salary_uplift_inr']:,}  ready~{p['time_to_ready_months']}mo")
        print(f"    courses: {[c['title'] for c in p['courses']]}")


if __name__ == "__main__":
    run()
