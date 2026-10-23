"""2026-10 second wave (review E_NL item 15 leftovers, NL2 brief): the re-run record of a DDM re-run split into chunks,
the B-1.2 refresh of stored sweeps, and the presentation fixes (record pairs and analyses, the record-set disclosure,
phi_s x lambda_u as information, Vmax/W instead of Vmax/VB on sheds).

Pure tests run everywhere. Package tests use the published NL gold set (STELTIC_NL_GOLD, default
/home/claude/work/golds/nl_1004) and the PEB set (STELTIC_NL_PEB, default
/home/claude/work/golds/nl_peb/india_nl_gold_peb_2026-10-16), matched on the title part of the run id, and skip
without them."""
import copy
import glob
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# =============================================================================================== chunked re-run record
def test_rerun_record_keeps_every_chunk():
    from steltic_ddm.cli import _record_rerun
    first = dict(code="NL-30 / first-wave re-run", combos=["1.5DL+1.5LL"], date="2026-10-18T18:43:26")
    opts = dict(ddm_rerun=first)
    a = dict(code="NL-30 / re-run of named combinations", combos=["1.2DL+1.2LL+1.2W_X"], date="2026-10-23T16:00:00")
    b = dict(code="NL-30 / re-run of named combinations", combos=["1.2DL+1.2LL-1.2W_X"], date="2026-10-23T17:00:00")
    _record_rerun(opts, "ddm_rerun", a)
    _record_rerun(opts, "ddm_rerun", b)
    assert opts["ddm_rerun"] is b
    assert [r["combos"][0] for r in opts["ddm_rerun_history"]] == ["1.5DL+1.5LL", "1.2DL+1.2LL+1.2W_X", "1.2DL+1.2LL-1.2W_X"]
    _record_rerun(opts, "ddm_retry", dict(code="NL-30", combos=["x"]))
    assert opts["ddm_retry_history"] == [dict(code="NL-30", combos=["x"])]


def test_code_version_names_the_commit():
    from steltic_ddm.cli import code_version
    v = code_version()
    assert v is None or (len(v.split("+")[0]) >= 7 and all(c in "0123456789abcdef" for c in v.split("+")[0]))


# =============================================================================================== B-1.2 refresh (--b12-only)
def test_curve_prefix_match():
    from steltic_ddm.cli import curve_prefix_match
    stored = [(0.05, -2.1), (0.1, -4.2), (0.5, -21.0), (1.0, -42.0), (1.04, -47.4), (1.03, -49.0)]
    ok, n, dl, dd, bad = curve_prefix_match(stored[:4], stored)
    assert ok and n == 4 and dl == 0.0 and bad is None
    ok, n, dl, dd, bad = curve_prefix_match([(0.05, -2.1), (0.1, -4.2), (0.52, -21.0), (1.0, -42.0)], stored)
    assert not ok and bad == 2 and dl > 0.01
    assert not curve_prefix_match([(0.05, -2.1)], stored)[0]                      # one point proves nothing
    assert not curve_prefix_match(stored + [(1.0, -50.0)], stored)[0]             # longer than the stored curve


def test_sweep_stops_after_lambda_1_flag_exists():
    import inspect
    from steltic_ddm import solver
    assert "stop_after_lambda1" in inspect.signature(solver.sweep).parameters
    src = inspect.getsource(solver.sweep)
    assert "lambda1_captured" in src


def test_retry_has_b12_only_flag():
    import contextlib, io
    from steltic_ddm import cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        cli.main(["retry", "--help"])
    assert "--b12-only" in buf.getvalue()
