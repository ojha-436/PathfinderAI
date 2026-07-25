"""Initialise PathFinderAI: create DB tables and materialise the demand series.

Run once before serving:  python -m seed   (from the backend/ directory)

The demand series is generated deterministically from documented parameters in
app/data/skills.json and written to app/data/demand_series.json purely for
transparency/inspection — the app itself generates it in-memory each run, so the
two are always identical (reproducibility, SPEC G4).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import Base, engine  # noqa: E402
from app.engines import datasets as ds  # noqa: E402
from app.engines import forecast as fc  # noqa: E402


def materialise_demand_series() -> str:
    out = {
        "_meta": {
            "market": ds.MARKET,
            "history_months": ds.HISTORY_MONTHS,
            "generated_from": "app/data/skills.json (deterministic; see datasets.demand_series)",
            "month_labels": ds.MONTH_LABELS[: ds.HISTORY_MONTHS],
        },
        "series": {sid: list(ds.demand_series(sid)) for sid in ds.SKILL_BY_ID},
    }
    path = ds.DATA_DIR / "demand_series.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return str(path)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("• Creating database tables…")
    Base.metadata.create_all(bind=engine)

    print("• Materialising demand series…")
    path = materialise_demand_series()
    c = ds.counts()
    print(f"  wrote {path}")
    print(f"• Datasets: {c['skills']} skills · {c['roles']} roles · {c['courses']} courses ({ds.MARKET})")

    # Determinism smoke check on the anomaly skill.
    f1 = fc.forecast_demand("data_entry")
    f2 = fc.forecast_demand("data_entry")
    assert f1 == f2, "Forecast is not deterministic!"
    print(f"• Sample forecast — 'Data Entry': {round(f1['growth_rate_annual'] * 100, 1)}%/yr ({f1['trend_direction']})")
    rise = fc.forecast_demand("power_bi")
    print(f"• Sample forecast — 'Power BI'  : {round(rise['growth_rate_annual'] * 100, 1)}%/yr ({rise['trend_direction']})")
    print("✓ Initialisation complete. Serve with:  uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
