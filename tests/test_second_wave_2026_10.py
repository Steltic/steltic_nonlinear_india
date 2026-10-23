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
