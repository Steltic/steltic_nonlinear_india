"""NL-14: gravity comes from the HR engine's own load states (static_model.apply_gravity_state) -- the NL gravity is
the seismic-weight state topped up to W per level, the DDM combines D / L / Lr / S with the combination factors, and
the gravity-transfer gate compares with the HR engine's member forces (member_combo_forces.json), restoring the
IS 875-2 3.2.1 column imposed-load reduction the HR design applied."""
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snl import hr_gravity as HG  # noqa: E402

REC = {"schema": HG.SCHEMA, "states": {
    "D": {"ele": [[10, 0.0, 0.5, "beamUniform", [0.0, -2.0, 0.0]], [10, 0.5, 1.0, "beamUniform", [0.0, -4.0, 0.0]]],
          "node": {"5": [0.0, 0.0, -100.0, 0.0, 0.0, 0.0]}, "total_N": 3100.0, "level_totals_N": {"1": 3100.0}},
    "L": {"ele": [[10, 0.0, 1.0, "beamUniform", [0.0, -1.0, 0.0]]], "node": {}, "total_N": 1000.0, "level_totals_N": {"1": 1000.0}},
    "EV": {"ele": [[10, 0.0, 1.0, "beamUniform", [0.0, -2.5, 0.0]]], "node": {"5": [0.0, 0.0, -100.0, 0, 0, 0]},
           "total_N": 2600.0, "level_totals_N": {"1": 2600.0}}}}


class Rec:
    def __init__(self):
        self.ele, self.node = [], []

    def eleLoad(self, *a):
        self.ele.append(a)

    def load(self, *a):
        self.node.append(a)


def test_combine_is_linear():
    c = HG.combine(REC, {"D": 1.5, "L": 1.5})
    w = [e for e in c["ele"] if e[0] == 10]
    assert [x[4][1] for x in w] == [-3.0, -6.0, -1.5]
    assert c["node"]["5"][2] == -150.0


def test_apply_maps_segments_by_span_fraction_and_scales_units():
    ops = Rec()
    loads = HG.combine(REC, {"D": 1.0})
    chains = {10: [(101, 0.0, 0.25), (102, 0.25, 0.5), (103, 0.5, 0.75), (104, 0.75, 1.0)]}
    info = HG.apply(ops, loads, chains)
    got = {a[1]: a[5] for a in ops.ele}
    assert got == {101: -2.0, 102: -2.0, 103: -4.0, 104: -4.0}                       # the load stays where it was
    assert info["n_nodal_loads"] == 1 and info["missing"] == 0.0
    ops = Rec()                                                                       # one element over the whole span
    HG.apply(ops, loads, {10: [(10, 0.0, 1.0)]}, force_scale=1 / 4448.2216152605, length_scale=1 / 25.4)
    assert ops.ele[0][5] == pytest.approx(-3.0 / 4448.2216152605 * 25.4)             # N/mm -> kip/in, average of 2 and 4
    assert ops.node[0][3] == pytest.approx(-100 / 4448.2216152605)
    info = HG.apply(Rec(), loads, {})                                                 # a parent not in the model
    assert info["missing"] > 0


def test_nl_gravity_uses_the_seismic_weight_state_and_tops_up_to_W(monkeypatch):
    import india_nl_job
    from pushover import package_reader as PR, india_model as IMD
    job = india_nl_job.make(outputs=False)
    pkg = PR.load(job)
    W = pkg.basis.india["W_by_floor_kN"]
    lv = IMD._levels(pkg)
    rec = {"schema": HG.SCHEMA, "states": {"EV": {"ele": [], "node": {}, "total_N": 0.0,
                                                  "level_totals_N": {str(k): 0.9 * Wi * 1e3 for (k, *_), Wi in zip(lv, W)}}}}
    monkeypatch.setattr(HG, "ensure", lambda root, *a, **k: rec)
    loads, table = IMD.is_gravity_loads(pkg)
    assert "_hr" in loads and table[0]["HR_EV_kN"] == pytest.approx(0.9 * W[0], rel=1e-3)
    assert table[0]["topup_kN"] == pytest.approx(0.1 * W[0], rel=1e-3)
    nodal_kN = -sum(v for k, v in loads.items() if not isinstance(k, str)) * 4.4482216152605
    assert nodal_kN == pytest.approx(0.1 * sum(W), rel=1e-3)
    monkeypatch.setattr(HG, "ensure", lambda root, *a, **k: None)                    # no HR engine: old idealisation
    loads, table = IMD.is_gravity_loads(pkg)
    assert "_hr" not in loads and -sum(loads.values()) * 4.4482216152605 == pytest.approx(sum(W), rel=1e-6)


def test_stale_record_is_not_used(tmp_path):
    (tmp_path / "cfg.py").write_text("cfg = {}\n")
    (tmp_path / "model_opensees.py").write_text("")
    d = dict(REC, inputs_sha256=HG._inputs_sha(str(tmp_path)))
    json.dump(d, open(tmp_path / HG.OUT_NAME, "w"))
    assert HG.load(tmp_path) is not None
    (tmp_path / "cfg.py").write_text("cfg = {'changed': 1}\n")
    assert HG.load(tmp_path) is None


@pytest.mark.skipif(not (os.environ.get("STELTIC_ENGINE_DIR") and os.path.exists(os.path.join(os.environ.get("STELTIC_ENGINE_DIR", ""), "engine3d.py"))),
                    reason="needs the HR steel_engine (STELTIC_ENGINE_DIR)")
def test_cfg_may_import_job_local_helpers(tmp_path):
    from steltic_ddm.ingest import load_cfg
    (tmp_path / "helper_build.py").write_text("X = 42\n")
    (tmp_path / "cfg.py").write_text("import helper_build as HB\ncfg = dict(x=HB.X)\n")
    assert load_cfg(str(tmp_path))["x"] == 42
    assert str(tmp_path) not in sys.path
