"""Wave 1 / NL-2: DDM combination path prefers the India load_plan; refuses bare India jurisdiction.

The fixtures follow the current steltic_india load_plan contract (india_loads.validate_load_plan): a load_plan with
no IS 875-3 retrieval must say `no_wind` with a reason (S5/H2 wind gate), and the gold IN_Ex3 load_plan (IS 1893
RSA combinations, 7.8.2 [ea]/[eb] torsion rows, IS 18168 [col] Omega rows) must validate and expand."""
from __future__ import annotations
import json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_ENG = os.environ.get("STELTIC_ENGINE_DIR")
if _ENG and _ENG not in sys.path:
    sys.path.insert(0, _ENG)

from steltic_ddm import loads  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "IN_Ex3_gold", "load_plan.json")


def test_india_without_load_plan_raises():
    cfg = {"jurisdiction": "india", "heights": [120.0], "SX": 300.0, "SY": 300.0}
    with pytest.raises(RuntimeError) as ei:
        loads.steltic_combos(cfg)
    assert "load_plan" in str(ei.value).lower() or "India" in str(ei.value)


def _gravity_only_cfg():
    return {
        "jurisdiction": "india", "heights": [120.0], "SX": 300.0, "SY": 300.0,
        "load_plan": {
            "jurisdiction": "india",
            "no_wind": {"reason": "unit-test fixture: one gravity combination only", "cite": "test fixture"},
            "retrieval": [
                {"stem": "IS_875_Part_2_1987", "query": "imposed", "found": True, "cite": "T1"},
                {"stem": "IS_875_Part_3_2015", "query": "basic wind speed", "found": False, "cite": None},
                {"stem": "IS_1893_Part_1_2016", "query": "Z", "found": True, "cite": "T3"},
                {"stem": "IS_800_2007", "query": "combinations", "found": True, "cite": "T4"},
            ],
            "combinations": [
                {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0.0, "cite": "IS 800 T4"},
            ],
        },
    }


def test_load_plan_via_india_loads():
    pytest.importorskip("india_loads", reason="needs the HR steel_engine on sys.path (STELTIC_ENGINE_DIR)")
    cases = loads.steltic_combos(_gravity_only_cfg())
    assert len(cases) == 1 and cases[0][0] == "1.5DL+1.5LL"
    assert cases[0][1] == 1.5 and cases[0][2] == 1.5


def test_load_plan_missing_wind_decision_is_refused():
    IL = pytest.importorskip("india_loads", reason="needs the HR steel_engine on sys.path (STELTIC_ENGINE_DIR)")
    cfg = _gravity_only_cfg()
    del cfg["load_plan"]["no_wind"]
    cfg["load_plan"]["retrieval"] = [r for r in cfg["load_plan"]["retrieval"] if "875_Part_3" not in r["stem"]]
    with pytest.raises(IL.LoadPlanError):
        loads.steltic_combos(cfg)


def test_gold_ex3_load_plan_expands():
    pytest.importorskip("india_loads", reason="needs the HR steel_engine on sys.path (STELTIC_ENGINE_DIR)")
    lp = json.load(open(FIX, encoding="utf-8"))
    cfg = {"jurisdiction": "india", "heights": [8000.0], "load_plan": lp}
    cases = loads.steltic_combos(cfg)
    labels = [c[0] for c in cases]
    assert "1.5DL+1.5LL" in labels
    assert any("EQ_X" in l and "[ea]" in l for l in labels) and any("EQ_Y" in l for l in labels)
    assert any("[col]" in l for l in labels)                         # IS 18168 5.5 Omega rows present
    kept = loads.prune(cases)
    assert any("EQ_X" in c[0] for c in kept) and any("W_" in c[0] or "DL" in c[0] for c in kept)
