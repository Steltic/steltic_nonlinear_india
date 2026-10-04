"""NL-31: a DDM numerical stop (SOLVER_FAILURE) on a seismic-pattern combination with no phi_s pass/fail (SEIS class),
reached at lambda >= 1 after the NL-30 retries (dlam, dlam/2, dlam/4), is disclosed instead of blocking the COMPLETE
gate. Gravity / wind stops, stops below lambda 1 and un-retried stops still block (NL-24). Gold case: IN_Ex9 stem,
1.2DL+1.2LL-1.2EQ_Y[ea]+0.3EQ_Z, every attempt stopped at lambda 1.3377."""
import json

from nlrha import india_authority as IA

SEIS = dict(cls="SEIS", phi_s=None, status="n/a")
HRG = dict(cls="HR-G", phi_s=0.8, status="verified")
RETRIED = [dict(dlam=0.05, status="SOLVER_FAILURE", lambda_end=1.3377),
           dict(dlam=0.025, status="SOLVER_FAILURE", lambda_end=1.3377),
           dict(dlam=0.0125, status="SOLVER_FAILURE", lambda_end=1.3377)]


def _run(**kw):
    r = dict(label="1.2DL+1.2LL-1.2EQ_Y[ea]+0.3EQ_Z", imp="-Y", kind="seismic", status="SOLVER_FAILURE",
             termination="step_exhausted", lambda_end=1.3377, stop_tangent_ratio=0.67, phi=SEIS, retries=RETRIED)
    r.update(kw)
    return r


def test_disclosable_only_for_retried_seismic_no_phi_stop_at_or_above_one():
    assert IA.ddm_solver_stop_disclosable(_run())
    assert not IA.ddm_solver_stop_disclosable(_run(kind="gravity", phi=HRG))
    assert not IA.ddm_solver_stop_disclosable(_run(kind="wind"))
    assert not IA.ddm_solver_stop_disclosable(_run(phi=dict(SEIS, phi_s=0.9)))          # a phi check exists
    assert not IA.ddm_solver_stop_disclosable(_run(lambda_end=0.97))
    assert not IA.ddm_solver_stop_disclosable(_run(retries=RETRIED[:2]))                 # retries not spent
    assert not IA.ddm_solver_stop_disclosable(_run(retries=None))
    assert not IA.ddm_solver_stop_disclosable(_run(status="NO_LIMIT_POINT"))


def _write(tmp_path, runs):
    (tmp_path / "ddm_results.json").write_text(json.dumps(dict(runs=runs, gravity_gate=dict(ok=True), b12_check=dict(ok=True))))


def test_gate_discloses_instead_of_blocking(tmp_path):
    _write(tmp_path, [_run(), dict(label="1.5DL+1.5LL", kind="gravity", status="LIMIT_POINT", lambda_end=1.04, phi=HRG)])
    g = IA.artefact_gate(str(tmp_path))
    assert not any("SOLVER FAILURE" in x for x in g["reasons"])
    assert g["checks"]["ddm_solver_stops_disclosed"][0]["lambda_end"] == 1.3377
    rows = [r for r in IA.method_disclosures(str(tmp_path)) if r["id"] == "ddm_seismic_solver_stop"]
    assert rows and rows[0]["disclosed"] and rows[0]["runs"][0]["imp"] == "-Y" and len(rows[0]["runs"][0]["retries"]) == 3


def test_gate_still_blocks_gravity_and_unretried_stops(tmp_path):
    _write(tmp_path, [_run(kind="gravity", label="1.5DL+1.5LL", phi=HRG), _run(retries=None, label="0.9DL+1.5EQ_X")])
    r = IA.artefact_gate(str(tmp_path))["reasons"]
    assert len([x for x in r if "SOLVER FAILURE" in x]) == 2
    assert not [x for x in IA.method_disclosures(str(tmp_path)) if x["id"] == "ddm_seismic_solver_stop"]
