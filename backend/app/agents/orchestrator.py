"""The 4-agent decision pipeline (SPEC R6).

SkillsExtractor → MarketAnalyst → PathwayPlanner → ROIForecaster, plus a grounded
CourseGrounder step. Every agent logs an input/output/timing trace surfaced in the
UI. Runs on the pluggable providers, so it is real with local providers and
upgrades to Gemini/BQML/Vertex when credentialed. Fully deterministic.

`adk/adk_app.py` wraps these same four steps in an ADK SequentialAgent to
demonstrate real ADK usage; this native orchestrator is the serving path (R6
de-risk fallback), so the UI is identical either way.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.engines import datasets as ds
from app.engines import forecast as fc
from app.engines import providers, taxonomy

# Composite-score normalisation caps (documented, deterministic).
GROWTH_CAP = 0.20        # 20%/yr counts as full marks on the growth axis
UPLIFT_CAP = 600_000     # ₹6L/yr uplift counts as full marks on the payoff axis
READY_CAP = 12           # a ≤2-month runway ~ full marks on achievability
# Composite weights: coverage (how much you already have) · demand growth ·
# salary uplift · achievability (time-to-ready). Sum = 1.0.
W_OVERLAP, W_GROWTH, W_UPLIFT, W_READY = 0.35, 0.25, 0.20, 0.20


def _inr(n: int) -> str:
    """Indian-grouped rupee string, e.g. 550000 -> '5,50,000'."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    parts.insert(0, head)
    return ",".join(parts) + "," + tail


class Orchestrator:
    def __init__(self) -> None:
        self.skill_extractor = providers.get_skill_extractor()
        self.forecaster = providers.get_forecaster()
        self.course_grounder = providers.get_course_grounder()
        self.traces: List[Dict[str, Any]] = []

    def _trace(self, name: str, start: float, inputs: Any, outputs: Any, detail: str = "") -> None:
        self.traces.append({
            "agent_name": name,
            "ms_taken": int((time.time() - start) * 1000),
            "inputs_summary": inputs,
            "outputs_summary": outputs,
            "detail": detail,
        })

    def _current_salary(self, role_ids: List[str]) -> int:
        medians = [ds.SALARIES[rid]["median"] for rid in role_ids if rid in ds.SALARIES]
        if medians:
            return max(medians)
        return ds.SALARIES[ds.BASELINE_ROLE_ID]["median"]

    def run_pipeline(self, text: Optional[str] = None,
                     manual_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.traces = []

        # 1) SkillsExtractor -------------------------------------------------
        t0 = time.time()
        if manual_profile is not None:
            profile = taxonomy.extract_from_manual(manual_profile)
            src = "manual/edited profile"
        else:
            profile = self.skill_extractor.extract(text or "")
            src = f"resume text ({len(text or '')} chars)"
        self._trace(
            "SkillsExtractor", t0,
            {"source": src},
            {"skills": [profile["skill_labels"][s] for s in profile["skills"]],
             "roles": profile["roles"], "years": profile["years_experience"]},
            detail=f"Extractor: {self.skill_extractor.name}. Parsed profile to canonical skill IDs.",
        )

        # 2) MarketAnalyst — forecast each of the user's skills -------------
        t0 = time.time()
        forecasts: Dict[str, Dict[str, Any]] = {}
        for sid in profile["skills"]:
            forecasts[sid] = self.forecaster.forecast(sid)
        declining = [forecasts[s]["skill_label"] for s in forecasts if forecasts[s]["trend_direction"] == "down"]
        rising = [forecasts[s]["skill_label"] for s in forecasts if forecasts[s]["trend_direction"] == "up"]
        self._trace(
            "MarketAnalyst", t0,
            {"skills_to_forecast": len(profile["skills"])},
            {"rising": rising, "declining": declining},
            detail=f"Forecaster: {self.forecaster.name}. Holt/BQML demand forecast per skill.",
        )

        # 3) PathwayPlanner — candidate roles by weighted skill coverage ----
        t0 = time.time()
        have = set(profile["skills"])
        candidates: List[Dict[str, Any]] = []
        for role in ds.ROLES:
            if role.get("is_baseline"):
                continue
            role_skills: Dict[str, float] = role["skills"]
            matched = [sid for sid in role_skills if sid in have]
            coverage = sum(role_skills[sid] for sid in matched)  # 0..~1 (weights sum ~1)
            gap = [sid for sid in role_skills if sid not in have]
            candidates.append({
                "role": role, "matched": matched, "coverage": coverage, "gap": gap,
            })
        self._trace(
            "PathwayPlanner", t0,
            {"roles_considered": len(candidates), "user_skills": len(have)},
            {"top_by_coverage": [
                c["role"]["name"]
                for c in sorted(candidates, key=lambda c: -c["coverage"])[:5]]},
            detail="Mapped profile against the role–skill matrix (weighted coverage).",
        )

        # 4) ROIForecaster — quantify, rank, explain ------------------------
        t0 = time.time()
        current_salary = self._current_salary(profile["role_ids"])
        scored: List[Dict[str, Any]] = []
        for c in candidates:
            role = c["role"]
            role_skills: Dict[str, float] = role["skills"]

            # Overlap = blend of weighted coverage (importance you already cover)
            # and count fraction (breadth). Neither alone is fair; the blend is.
            coverage_weighted = min(max(c["coverage"], 0.0), 1.0)
            coverage_count = len(c["matched"]) / len(role_skills) if role_skills else 0.0
            overlap = 0.5 * coverage_weighted + 0.5 * coverage_count

            # Pathway demand growth = weight-avg forecast growth of its skills.
            total_w = sum(role_skills.values()) or 1.0
            role_growth = sum(role_skills[sid] * fc.skill_growth(sid) for sid in role_skills) / total_w

            target_salary = ds.SALARIES[role["salary_key"]]["median"]
            uplift = max(0, target_salary - current_salary)

            ttr = max(2, round(role["time_to_ready_base_months"] * (1 - 0.4 * overlap)))

            overlap_norm = overlap
            growth_norm = min(max(role_growth / GROWTH_CAP, 0.0), 1.0)
            uplift_norm = min(uplift / UPLIFT_CAP, 1.0)
            ready_norm = 1.0 - min(ttr, READY_CAP) / READY_CAP
            score = 100.0 * (W_OVERLAP * overlap_norm + W_GROWTH * growth_norm
                             + W_UPLIFT * uplift_norm + W_READY * ready_norm)

            overlap_pct = round(100 * overlap)

            matched_sorted = sorted(c["matched"], key=lambda s: -role_skills[s])
            gap_sorted = sorted(c["gap"], key=lambda s: -role_skills[s])
            transferable = [ds.SKILL_NAME[s] for s in matched_sorted]
            gap_names = [ds.SKILL_NAME[s] for s in gap_sorted]

            # Signal skill = the highest-weight rising skill that defines this path
            # (a gap skill to learn, else the top role skill). Its forecast drives
            # the drill-in chart + card sparkline.
            signal_id = next((s for s in gap_sorted if ds.SKILL_CATEGORY.get(s) == "rising"),
                             gap_sorted[0] if gap_sorted else (matched_sorted[0] if matched_sorted
                             else max(role_skills, key=role_skills.get)))
            signal_forecast = self.forecaster.forecast(signal_id)

            growth_pct = round(role_growth * 100, 1)
            if transferable:
                lead = f"You already cover {overlap_pct}% of what a {role['name']} needs ({', '.join(transferable[:3])})."
            else:
                lead = f"A {role['name']} is a fresh start from your current profile."
            explanation = (
                f"{lead} Demand for this pathway is trending "
                f"{'+' if growth_pct >= 0 else ''}{growth_pct}%/yr, with an estimated "
                f"₹{_inr(uplift)}/yr salary uplift and ~{ttr} months to job-ready at 6–8 hrs/week."
            )

            scored.append({
                "role": role["name"], "role_id": role["id"],
                "match_score": round(score, 1),
                "overlap_percentage": overlap_pct,
                "transferable_skills": transferable,
                "gap_skills": gap_names,
                "demand_growth_annual": round(role_growth, 4),
                "salary_current_inr": current_salary,
                "salary_target_inr": target_salary,
                "salary_uplift_inr": uplift,
                "time_to_ready_months": ttr,
                "explanation": explanation,
                "data_source": (
                    "Composite = 0.35×skill coverage + 0.25×demand growth (forecast) "
                    "+ 0.20×salary uplift (public India salary bands) + 0.20×achievability (time-to-ready)."
                ),
                "signal_skill": ds.SKILL_NAME.get(signal_id, signal_id),
                "signal_forecast": signal_forecast,
            })

        scored.sort(key=lambda p: (-p["match_score"], p["role_id"]))
        top = scored[:3]
        for i, p in enumerate(top):
            p["rank"] = i + 1
        self._trace(
            "ROIForecaster", t0,
            {"candidates": len(scored), "current_salary_inr": current_salary},
            {"pathways": [f"{p['role']} ({p['match_score']})" for p in top]},
            detail="Ranked by composite payoff score; salary uplift and time-to-ready quantified.",
        )

        # 5) CourseGrounder — grounded top-3 per pathway --------------------
        t0 = time.time()
        for p in top:
            p["courses"] = self.course_grounder.ground(p["role_id"], profile["skills"])
        self._trace(
            "CourseGrounder", t0,
            {"pathways": len(top)},
            {"courses_per_pathway": [len(p["courses"]) for p in top]},
            detail=f"Grounder: {self.course_grounder.name}. Top-3 real courses from the curated catalog (no fabrication).",
        )

        return {"profile": profile, "forecasts": forecasts, "pathways": top, "trace": self.traces}
