"""Provenance of the component parameters: verified / grounded / collected / unverified (India).

The bug these pin (US): `snl revise` looked the clauses up, recorded them, and then told the engineer to
re-run the analyses to "pick the citation up". Every report asked one boolean (`verified`), which Revise
deliberately does not set -- so the red UNVERIFIED banner came back unchanged, and re-running made it worse:
pushover/cli.py copies the input parameters over hinge_params_used.json, erasing the annotation.
India adds: the hinge backbones can never be verified (IS 800 / IS 1893 / IS 18168 tabulate none), a revise
record grounds the IS clauses, and `snl collect` puts the IS specification values in (state `collected`).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from snl import grounding as G            # noqa: E402

STATEMENT = "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information."
PRM = {"_README": "notes", "verified": False, "beam_flexure": {"a": 0.02, "b": 0.05},
       "column_flexure": {"a": 0.01}, "brace_axial": {"c": 0.4}}
EV = {"asked": "2026-09-26T16:08:30",
      "groups": {"beam_flexure": {"grounded": False, "status": "modelling assumption"}},
      "clauses": {"7.11.1.1": {"grounded": True, "citation": "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 28]"},
                  "12.8.1": {"grounded": True, "citation": "[IS 800:2007 cl. 12.8.1, p. 94]"}}}
COLLECTED = dict(PRM, spec_values_collected=True,
                 india_collect={"asked": "2026-09-26T09:00:00", "complete": True,
                                "groups": {"material": {"source": "IS 2062 (Part 1):2025 Table 3, p. 9"}}})


def _job(tmp, ev=EV, prm=PRM, fingerprint=True):
    job = tmp / "job"; (job / "pushover").mkdir(parents=True)
    (job / "pushover" / "hinge_params_used.json").write_text(json.dumps(prm), encoding="utf-8")
    if ev is not None:
        e = dict(ev)
        if fingerprint:
            e["params"] = {"path": "pushover/hinge_params_used.json", "fingerprint": G.fingerprint(prm)}
        (job / G.EVIDENCE).write_text(json.dumps(e), encoding="utf-8")
    return job


def test_the_four_states(tmp_path):
    job = _job(tmp_path)
    assert G.state(PRM, str(job))[0] == G.GROUNDED                       # Revise ran: IS clauses grounded
    assert G.state(dict(PRM, verified=True), str(job))[0] == G.VERIFIED  # never for an India backbone, but honoured
    assert G.state(PRM, str(tmp_path / "nothing"))[0] == G.UNVERIFIED    # nobody looked
    assert G.state(COLLECTED, str(tmp_path / "nothing"))[0] == G.COLLECTED   # snl collect read the IS values


def test_it_is_found_from_the_output_folder_too(tmp_path):
    """The reports render from pushover/ and nlrha/; the record lives at the job root."""
    job = _job(tmp_path)
    assert G.state(PRM, str(job / "pushover"))[0] == G.GROUNDED
    assert G.job_root(str(job / "pushover")) == str(job)


def test_the_fingerprint_ignores_provenance_so_a_re_run_keeps_the_grounding(tmp_path):
    annotated = dict(PRM, grounding={"asked": "..."}, source="cited from the corpus ...")
    assert G.fingerprint(annotated) == G.fingerprint(PRM)
    job = _job(tmp_path)
    assert G.state(PRM, str(job))[0] == G.GROUNDED


def test_grounding_recorded_against_other_parameters_does_not_count(tmp_path):
    job = _job(tmp_path)
    other = dict(PRM, beam_flexure={"a": 0.09, "b": 0.11})
    assert G.fingerprint(other) != G.fingerprint(PRM)
    assert G.state(other, str(job))[0] == G.UNVERIFIED


def test_evidence_with_nothing_grounded_is_not_grounding(tmp_path):
    job = _job(tmp_path, ev={"asked": "x", "groups": {"beam_flexure": {"grounded": False}}, "clauses": {"7.7.4": {"grounded": False}}})
    assert G.state(PRM, str(job))[0] == G.UNVERIFIED
    assert G.state(COLLECTED, str(job))[0] == G.COLLECTED                # the file's own state stands


def test_a_damaged_evidence_file_never_raises(tmp_path):
    job = _job(tmp_path); (job / G.EVIDENCE).write_text("{not json", encoding="utf-8")
    assert G.state(PRM, str(job)) == (G.UNVERIFIED, None)


# ---------------------------------------------------------------- what the reports end up saying
LEGACY_PUSH = ('<h1>x</h1><div class="banner">UNVERIFIED MODELLING PARAMETERS — hinge_params.json has '
               'verified=false. Source note: placeholder</div><div class="note">Not for construction.</div>')
LEGACY_NL = ('<h1>x</h1><div class="banner">UNVERIFIED COMPONENT PARAMETERS — backbones are placeholders. '
             'Cyclic deterioration is OFF in this prototype although 16.3.1 requires it unless shown not to '
             'govern.</div><div class="note">Not for construction.</div>')


def test_the_grounded_block_cites_the_is_clauses_and_names_the_backbones_assumptions():
    html = G.block_html(G.GROUNDED, EV, PRM)
    assert "7.11.1.1" in html and "p. 28" in html and "12.8.1" in html      # the citations are in the document
    assert "modelling assumptions" in html and "not acceptance criteria" in html
    assert STATEMENT in html and 'data-provenance="grounded"' in html
    assert "UNVERIFIED" not in html and "ASCE" not in html and "AISC" not in html


def test_the_collected_block_names_the_is_values():
    html = G.block_html(G.COLLECTED, None, COLLECTED)
    assert 'data-provenance="collected"' in html and "IS 2062 (Part 1):2025 Table 3, p. 9" in html
    assert "modelling assumptions" in html and STATEMENT in html


def test_the_unverified_banner_is_india_wording():
    html = G.block_html(G.UNVERIFIED, None, PRM)
    assert "Collect specification values" in html and "modelling assumptions" in html
    assert "ASCE" not in html and "AISC" not in html


def test_patching_a_report_replaces_only_the_provenance_block(tmp_path):
    p = tmp_path / "r.html"; p.write_text(LEGACY_PUSH, encoding="utf-8")
    assert G.patch(str(p), G.GROUNDED, EV, PRM) == G.PATCHED
    out = p.read_text(encoding="utf-8")
    assert "UNVERIFIED" not in out and "7.11.1.1" in out
    assert "<h1>x</h1>" in out and "Not for construction." in out


def test_patching_keeps_a_disclosure_that_was_sharing_the_banner(tmp_path):
    p = tmp_path / "n.html"; p.write_text(LEGACY_NL, encoding="utf-8")
    assert G.patch(str(p), G.GROUNDED, EV, PRM) == G.PATCHED
    out = p.read_text(encoding="utf-8")
    assert "Cyclic deterioration is OFF" in out and "UNVERIFIED" not in out


def test_patching_twice_is_not_an_error(tmp_path):
    p = tmp_path / "r.html"; p.write_text(LEGACY_PUSH, encoding="utf-8")
    assert G.patch(str(p), G.GROUNDED, EV, PRM) == G.PATCHED
    assert G.patch(str(p), G.GROUNDED, EV, PRM) == G.UNCHANGED
    assert p.read_text(encoding="utf-8").count("data-provenance") == 1


def test_an_india_report_block_is_patched_in_place(tmp_path):
    """The India pushover / NLRHA pages write the marked block themselves (report_india.py)."""
    p = tmp_path / "r.html"
    p.write_text("<h1>x</h1>" + G.block_html(G.COLLECTED, None, COLLECTED) + "<p>curve</p>", encoding="utf-8")
    assert G.patch(str(p), G.GROUNDED, EV, COLLECTED) == G.PATCHED
    out = p.read_text(encoding="utf-8")
    assert 'data-provenance="grounded"' in out and "IS 2062 (Part 1):2025 Table 3" in out and "<p>curve</p>" in out


def test_a_report_with_no_provenance_block_says_so(tmp_path):
    p = tmp_path / "r.html"; p.write_text("<h1>x</h1><p>nothing here</p>", encoding="utf-8")
    assert G.patch(str(p), G.GROUNDED, EV, PRM) == G.ABSENT
    assert G.patch(str(tmp_path / "missing.html"), G.GROUNDED, EV, PRM) == G.ABSENT


def test_going_back_to_unverified_is_possible(tmp_path):
    p = tmp_path / "r.html"; p.write_text(LEGACY_PUSH, encoding="utf-8")
    G.patch(str(p), G.GROUNDED, EV, PRM)
    assert G.patch(str(p), G.UNVERIFIED, None, PRM) == G.PATCHED
    assert "UNVERIFIED MODELLING PARAMETERS" in p.read_text(encoding="utf-8")


def test_the_one_line_summary_distinguishes_the_states():
    assert G.summary(G.UNVERIFIED, None, PRM).startswith("UNVERIFIED placeholders")
    assert "IS clauses retrieved" in G.summary(G.GROUNDED, EV, PRM) and "modelling assumptions" in G.summary(G.GROUNDED, EV, PRM)
    assert G.summary(G.COLLECTED, None, COLLECTED).startswith("IS specification values collected")
    assert G.summary(G.VERIFIED, None, dict(PRM, source="checked")).startswith("verified ·")


def test_the_analysis_run_re_applies_the_grounding_it_used_to_erase(tmp_path):
    from pushover.cli import _copy_params
    job = _job(tmp_path)
    src = tmp_path / "input_params.json"
    src.write_text(json.dumps(PRM), encoding="utf-8")
    dst = job / "pushover" / "hinge_params_used.json"
    _copy_params(str(src), str(dst))
    out = json.loads(dst.read_text(encoding="utf-8"))
    assert out["grounding"]["clauses"]["7.11.1.1"] == "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 28]"
    assert out["grounding"]["groups"] == {} and "source" not in out     # no backbone citation to claim
    assert out["verified"] is False
    assert G.state(out, str(job))[0] == G.GROUNDED


def test_a_run_with_different_parameters_does_not_inherit_the_citation(tmp_path):
    from pushover.cli import _copy_params
    job = _job(tmp_path)
    src = tmp_path / "other.json"
    src.write_text(json.dumps(dict(PRM, beam_flexure={"a": 0.09})), encoding="utf-8")
    dst = job / "pushover" / "hinge_params_used.json"
    _copy_params(str(src), str(dst))
    out = json.loads(dst.read_text(encoding="utf-8"))
    assert "grounding" not in out and G.state(out, str(job))[0] == G.UNVERIFIED
