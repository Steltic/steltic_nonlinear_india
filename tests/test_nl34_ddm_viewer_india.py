"""NL-34: the DDM viewer on India (N-mm) jobs.

* a combination that ends without a limit point (lambda_u null) stopped the whole viewer at start-up
  (`r.lambda_u.toFixed` in the combination list) -- every India DDM viewer with a NO_LIMIT_POINT run was blank;
* India phi_s * lambda_u is information (check "INFO"), not a PASS / FAIL;
* lengths / forces are labelled mm / kN on N-mm models (were in / kip), and the India member schedule columns
  (P_comp_kN, M_major_kNm) are read;
* the transfer-gate displacement rows carry the model's length unit."""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from steltic_ddm import viewer3d as V  # noqa: E402


def test_template_is_null_safe_and_unit_aware():
    js = V.MODULE_JS
    assert "λu ${r.lambda_u.toFixed(2)}" not in js and "${run.lambda_u.toFixed(3)}</b>" not in js
    assert "LAM(run,3)" in js and "run.lambda_u===null ? []" in js
    for bad in ("} in`", "(in)`", " kip`", "k-ft`"):
        assert bad not in js, bad
    assert "U.len" in js and "U.force" in js and "check_info" in js


def test_india_units_and_schedule(tmp_path):
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "member_schedule.csv").write_text(
        "ele_tag,member,role,section,P_comp_kN,M_major_kNm,governing_combo\n7,col,lateral_col,WI400X180X8X5,63.1,812.4,1.5DL+1.5LL\n")
    sch = V._schedule(str(tmp_path))
    assert sch[7] == dict(combo="1.5DL+1.5LL", P=63, Mx=812)
    india = types.SimpleNamespace(cfg={"load_plan": {"jurisdiction": "India"}})
    usa = types.SimpleNamespace(cfg={"load_plan": {"jurisdiction": "USA"}})
    assert V._india_nmm(india) and not V._india_nmm(usa) and not V._india_nmm(types.SimpleNamespace(cfg=None))


def test_transfer_gate_rows_carry_the_unit():
    import inspect
    from steltic_ddm import transfer_gate as TG
    src = inspect.getsource(TG.run)
    assert 'ELF pattern (%s)" % du' in src and '"mm" if getattr(g, "_fibre_units"' in src
