"""Wave 1: DDM combination path prefers India load_plan; refuses bare India jurisdiction."""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join("/workspace/steltic_india", "steel_engine"))

from steltic_ddm import loads  # noqa: E402


def test_india_without_load_plan_raises():
    cfg = {"jurisdiction": "india", "heights": [120.0], "SX": 300.0, "SY": 300.0}
    try:
        loads.steltic_combos(cfg)
        raised = False
    except RuntimeError as e:
        raised = True
        assert "load_plan" in str(e).lower() or "India" in str(e)
    assert raised


def test_load_plan_via_india_loads():
    import pytest
    pytest.importorskip("design_pipeline", reason="needs the HR steel_engine on sys.path (STELTIC_ENGINE_DIR)")
    cfg = {
        "jurisdiction": "india",
        "heights": [120.0],
        "SX": 300.0,
        "SY": 300.0,
        "load_plan": {
            "jurisdiction": "india",
            "retrieval": [
                {"stem": "IS_875_Part_2_1987", "query": "imposed", "found": True, "cite": "T1"},
                {"stem": "IS_1893_Part_1_2016", "query": "Z", "found": True, "cite": "T3"},
                {"stem": "IS_800_2007", "query": "combinations", "found": True, "cite": "T4"},
            ],
            "combinations": [
                {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0.0, "cite": "IS 800 T4"},
            ],
        },
    }
    cases = loads.steltic_combos(cfg)
    assert len(cases) == 1 and cases[0][0] == "1.5DL+1.5LL"
    assert cases[0][1] == 1.5 and cases[0][2] == 1.5
