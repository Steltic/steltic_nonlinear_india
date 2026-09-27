"""NL-6: the India basis reads the HR package per direction -- V-bar_B (seismic_analysis.scale), R_x / R_y, Ta_x / Ta_y
-- and the ENGINE seismic weight W per floor (calc_package.seismic_calc), which is what the HR modal mass uses."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from nlrha import india_hazard as IH  # noqa: E402


def _pkg(tmp_path):
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "calc_package.json").write_text(json.dumps({
        "seismic_calc": {"system": "SMRF+SCBF", "R": 4.5, "Z": 0.24, "I": 1.0, "zone": "IV",
                         "W_by_floor_engine_kN": [1272.9, 1145.8]},
        "seismic_analysis": {"scale": {"X": {"VBbar_kN": 145.12}, "Y": {"VBbar_kN": 161.25}}}}))
    (tmp_path / "load_plan.json").write_text(json.dumps({"seismic_summary": {
        "W_by_floor_kN": [1270.0, 1140.0], "soil": "II", "zone": "IV", "R_x": 5.0, "R_y": 4.5,
        "Ta_x_s": 0.4043, "Ta_y_s": 0.093, "VB_x_kN": 140.0, "VB_y_kN": 150.0, "VB_kN": 150.0}}))
    return tmp_path


def test_inputs_per_direction_and_engine_W(tmp_path):
    ind = IH.inputs_from_package(_pkg(tmp_path))
    assert ind["W_by_floor_kN"] == [1272.9, 1145.8] and "engine" in ind["sources"]["W_by_floor_kN"]
    assert ind["W_kN"] == pytest.approx(2418.7)
    assert ind["W_check"]["used"] == "engine" and ind["W_check"]["rel_diff"] == pytest.approx(2418.7 / 2410.0 - 1)
    assert (ind["R_x"], ind["R_y"]) == (5.0, 4.5)
    assert (ind["VB_x_kN"], ind["VB_y_kN"]) == (145.12, 161.25)                   # V-bar_B, not the agent's ESM value
    assert IH.vb_direction_kN(ind, "X") == 145.12 and IH.vb_direction_kN(ind, "y") == 161.25
    assert ind["VB_kN"] == 161.25 and (ind["Ta_x"], ind["Ta_y"]) == (0.4043, 0.093)


def test_response_at_uses_the_direction_vb():
    from pushover import postprocess as PP
    run = {"rec": {"u": [0.0, 1.0, 2.0], "V": [0.0, 50.0, 60.0], "story_u": [[0.0], [1.0], [2.0]]}, "heights": [100.0]}
    r = PP.response_at(run, 1.0, "IS-DBE", V_design_kip=25.0)
    assert r["V_over_VB"] == pytest.approx(2.0) and r["VB_design_kN"] == pytest.approx(25.0 * 4.4482216152605)
