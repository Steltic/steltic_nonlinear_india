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


def test_rsa_combinations_get_the_static_is1893_pattern_and_india_prune():
    """NL-13: RSA-referenced EQ combinations carried only the 7.8.2 torsion moments -- the DDM 'EQ' sweeps had no lateral
    force. They now carry load_plan.story_forces EQ_X / EQ_Y x the factor; the India prune keeps one gravity case, the
    three IS 800 Table 4 lateral families per direction and sign, no notional / member-wind / 0.6 W / SLS / [col] rows."""
    IL = pytest.importorskip("india_loads", reason="needs the HR steel_engine on sys.path (STELTIC_ENGINE_DIR)")
    lp = json.load(open(FIX, encoding="utf-8"))
    cfg = {"jurisdiction": "india", "heights": [8000.0], "load_plan": lp}
    cases = loads.steltic_combos(cfg)
    eq = [c for c in cases if c[0] == "1.2DL+1.2LL+1.2EQ_X[ea]"][0]
    fx = sum(v[0] for v in eq[4].values())
    vb_x = sum(v[0] for v in IL._as_lateral(lp["story_forces"]["EQ_X"]).values()) * IL._story_force_scale(lp)
    assert fx == pytest.approx(1.2 * vb_x) and "7.6.3" in eq.meta["lateral_basis"]
    # the accidental-torsion moments (when the engine could compute esi) are kept alongside: fx added, mz untouched
    kept = loads.prune(cases)
    labels = [c[0] for c in kept]
    assert labels.count("1.5DL+1.5LL") == 1 and not any("N_" in l or "WM" in l or "0.6W" in l or l.startswith("SLS")
                                                           or "[col]" in l or "[eb]" in l for l in labels)
    assert all(sum(abs(v[0]) + abs(v[1]) for v in c[4].values()) > 0 for c in kept if "EQ" in c[0] or "W_" in c[0])
    assert len([l for l in labels if "EQ_X" in l]) == 6 and len([l for l in labels if "W_Y" in l]) == 6
    assert len(loads.prune(cases, torsion="both")) > len(kept)
