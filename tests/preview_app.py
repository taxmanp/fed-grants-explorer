"""Offline visual QA harness: uv run streamlit run tests/preview_app.py.

Synthetic fixtures only. Run in a separate process; production app.py is unchanged.
"""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
import streamlit as st
import client


def fixture_awards(filters, max_results=100):
    rows = [
        {"Award ID": f"DEMO-{i}", "generated_internal_id": f"ASST_DEMO_{i}",
         "Recipient Name": name, "Recipient UEI": f"DEMOUEI0000{i}", "Award Amount": amount,
         "Awarding Agency": "National Endowment for the Arts", "Awarding Sub Agency": agency,
         "Start Date": "2021-10-01"}
        for i, (name, amount, agency) in enumerate([
            ("EXAMPLE ARTS ORGANIZATION", 12000000, "Arts Programs"),
            ("SERVICES, EXAMPLE DEPARTMENT OF", 2500000, "Community Programs"),
            ("EXAMPLE UNIVERSITY", -10000, None),
        ], 1)
    ]
    return client.AwardSearchResult(pd.DataFrame(rows), False,
        "Result limit reached; more awards may match.", 1, "2026-10-11T00:00:00+00:00")


def fixture_total(filters):
    p = filters["time_period"][0]
    start, end = int(p["start_date"][:4]) + 1, int(p["end_date"][:4])
    rows = [{"Fiscal year": y, "Net obligations": (y - start + 1) * 250000.0} for y in range(start, end + 1)]
    return client.PeriodObligations(pd.DataFrame(rows), "2026-10-11T00:00:00+00:00")


client.get_toptier_agencies = lambda: pd.DataFrame({"agency_name": ["National Endowment for the Arts"]})
client.search_awards = fixture_awards
client.get_period_obligations = fixture_total
st.warning("OFFLINE UI PREVIEW: synthetic test data, not live USAspending results.")
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
