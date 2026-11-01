#!/usr/bin/env python3
"""build_site_index.py -- rebuild the site's nonlinear index (solutions_india/nl/index.json) from the run folders.

    python scripts/build_site_index.py --runs <root> [--previous index.json] [--override <id>=<folder> ...]
                                       [--out index.json]

<root> holds one job folder per run, at the run id's path (IN_Ex9_..., IN_Ex19_.../units/stem); each folder has the
analysis packages of `snl run` (pushover/pushover_package.json, nlrha/nlrha_package.json + nlrha/DBE|MCE/,
ddm_results.json, complete_gate.json). --override takes one run from another folder (a re-run). --previous is the
current index: its order, titles and links are kept, and runs it does not list are appended in run-id order. Every
number comes from the packages; nothing is typed in.

What each example's "results" carries (2026-10 first wave):
  gate, gate_notes             complete_gate.json status and notes (solver failures are stated, never silent);
                               2026-10 check fixes: gate_label and gate_reason_text (snl/gate_reason.py: what stopped,
                               in which combination, whether a capacity is reported, why it blocks or does not), no
                               ticket ids; pushover vmax_*_text_x/y ("≥" on a lower bound), mce_target_text_x/y where
                               the IS-MCE target was not reached, under_review_x/y + review_x/y (pushover/review.py)
  pushover                     per direction Vmax/VB and Vmax/W, whether the curve ended in a numerical stop (Vmax a
                               lower bound) and whether the IS-MCE target displacement was reached; second wave: `shed`
                               (snl/shed.py: single storey or industrial use in the HR package) with `headline` vmax_w --
                               a shed's meta line shows Vmax/W only (its R-reduced VB makes Vmax/VB 20-130); third wave
                               (P10, review M1): the headline is read up to the IS-MCE target displacement
                               (pushover/vmax_policy.py): headline_kind_x/y (peak / at_target / ended / whole_curve)
                               and headline_text_x/y; vmax_vb/w(_text)_x/y hold a STRENGTH only (a peak before δt, or the
                               computed peak of a curve that ended before δt: "≥" only if it was still rising), and
                               v_target_vb/w(_text)_x/y the base shear at δt where the curve is still rising there (not
                               a strength); mce_target_mm_x/y; peak_analysed_text_x/y states the peak of the analysed
                               curve (information); vmax_basis; te_below_t1_x/y, te_far_above_t1_x/y + te_note_x/y flag
                               an NSP effective period below T1 or far above it
  nlrha                      the record set ("FEMA P-695 far-field set, amplitude-scaled to the IS 1893 spectrum"),
                               per level the number of record pairs and how many converged, the max mean storey drift
                               and the scale-factor range; n_records / n_converged are kept for the current page and
                               count analyses (pairs x levels); second wave: the record set in full, its source and
                               what it lacks (nlrha/record_set.py, from records/p695_farfield/index.json), the scaling
                               rule and `analyses_text` ("11 record pairs (two horizontal components each), run at DBE
                               and at MCE: 22 analyses, 22 converged")
  ddm                          gravity lambda_u as the headline, min phi_s x lambda_u kept as information (US/AU
                               calibration; second wave: phi_s, its class and source, "not an IS 800 factor"),
                               solver-failure counts, B-1.2 (worst D/C rounded UP), b11_met and its parts
Margins (lambda, phi_s x lambda_u) are rounded DOWN to 3 decimals and demand ratios UP, and each comes with a
preformatted *_text string, so 0.997 never reads 1.00 (IN_Ex10).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

RECORD_SET_P695 = "FEMA P-695 far-field set, amplitude-scaled to the IS 1893 spectrum"
STATUS_WORDS = {"LIMIT_POINT": "limit point", "PLASTIC_PLATEAU": "plastic plateau", "DUCTILITY_CAP": "ductility cap"}


def _j(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def floor3(x):
    return None if x is None else math.floor(float(x) * 1000.0 + 1e-9) / 1000.0


def ceil3(x):
    return None if x is None else math.ceil(float(x) * 1000.0 - 1e-9) / 1000.0


def txt3(x):
    return None if x is None else "%.3f" % x


def _r(x, n):
    return None if x is None else round(float(x), n)


def record_set_name(nl_pkg, lv_pkgs):
    """The suite's record library, in words. The shipped default is the FEMA P-695 far-field set (PEER NGA)."""
    lib = str(((nl_pkg or {}).get("gm_basis") or {}).get("record_library") or "")
    sets = set()
    for p in lv_pkgs.values():
        for s_ in ((p or {}).get("ground_motions") or {}).get("sets") or []:
            sets.add(str(s_.get("name") if isinstance(s_, dict) else s_))
    user = [s_ for s_ in sets if s_ and "p695" not in s_.lower()]
    if "P-695" in lib and not user:
        return RECORD_SET_P695
    return ("%s, amplitude-scaled to the IS 1893 spectrum" % (lib.split(" (")[0] or ", ".join(sorted(user)))) if (lib or user) else None


def _ge(lb):
    return "≥ " if lb else ""


def pushover_results(job):
    from snl.shed import shed_basis
    from pushover import review as RV
    po = _j(os.path.join(job, "pushover", "pushover_package.json")) or {}
    sb = shed_basis(job)
    rv = RV.directions_under_review(job)
    out = dict(shed=sb["shed"], shed_basis=sb["basis"],
               headline=("vmax_w" if sb["shed"] else "vmax_vb"),
               vmax_vb_note=("on a shed VB (the R-reduced IS 1893 design base shear) is small, so Vmax/VB is large and is "
                             "not the headline: Vmax/W is" if sb["shed"] else None))
    from pushover import vmax_policy as VP
    for d, dd in sorted((po.get("directions") or {}).items()):
        cap = dd.get("capacity") or {}
        k = d.lower()
        # third wave, P10 / review M1: the headline is read up to the IS-MCE target displacement (vmax_policy):
        # a strength (Vmax) only where the curve peaks before δt; the base shear at δt where it is still rising
        h = VP.vmax_to_target(dd)
        if h is None:                                   # no IS-MCE target recorded: the whole-curve peak, as before
            tail = cap.get("tail_status") or (dd.get("tail") or {}).get("status")
            h = dict(V_over_VB=cap.get("Vmax_over_VB"), V_over_W=cap.get("Vmax_over_W"), kind="whole_curve",
                     is_strength=True, at_target=False, label="Vmax (whole curve)",
                     lower_bound=(tail == "lower_bound") or str(dd.get("stop_reason") or "").startswith("solver"),
                     target_mm=None, peak_analysed=None)
        lb = bool(h.get("lower_bound"))
        strength = bool(h.get("is_strength"))
        out["headline_kind_" + k] = h["kind"]
        out["headline_text_" + k] = VP.headline_text(d, h) if h.get("target_mm") is not None and d not in rv else None
        out["vmax_vb_" + k] = _r(h.get("V_over_VB"), 1) if strength else None
        out["vmax_w_" + k] = _r(h.get("V_over_W"), 3) if strength else None
        out["v_target_vb_" + k] = _r(h.get("V_over_VB"), 1) if h.get("at_target") else None
        out["v_target_w_" + k] = _r(h.get("V_over_W"), 3) if h.get("at_target") else None
        out["vmax_lower_bound_" + k] = lb
        out["mce_target_mm_" + k] = _r(h.get("target_mm"), 1)
        out["peak_analysed_text_" + k] = VP.peak_text(d, h) if (d not in rv and h.get("peak_analysed")) else None
        tf = VP.te_flags(dd)
        out["te_below_t1_" + k] = any(f[3] == "below" for f in tf)
        out["te_far_above_t1_" + k] = any(f[3] == "far_above" for f in tf)
        out["te_note_" + k] = VP.te_note(d, tf)
        # check fixes, finding 2: preformatted text with "≥" where the value is a lower bound, "under review" where it
        # is; review M1: the Vmax texts only for a strength, the V(δt) texts for the base shear at the target
        if d in rv:
            out["vmax_vb_text_" + k] = out["vmax_w_text_" + k] = "under review"
            out["v_target_vb_text_" + k] = out["v_target_w_text_" + k] = None
        else:
            fv = lambda key, f: (("%s" + f) % (_ge(lb), h[key])) if h.get(key) is not None else None   # noqa: E731
            out["vmax_vb_text_" + k] = fv("V_over_VB", "%.1f") if strength else None
            out["vmax_w_text_" + k] = fv("V_over_W", "%.2f") if strength else None
            out["v_target_vb_text_" + k] = fv("V_over_VB", "%.1f") if h.get("at_target") else None
            out["v_target_w_text_" + k] = fv("V_over_W", "%.2f") if h.get("at_target") else None
        mce = (dd.get("nsp") or {}).get("IS-MCE") or {}
        if mce:
            out["mce_target_reached_" + k] = bool(mce.get("reached_target"))
            if mce.get("reached_target") is False:         # check fixes, finding 1
                end = ((dd.get("response") or {}).get("IS-MCE") or {}).get("roof_disp_mm")
                if end is None and cap.get("u_end_in") is not None:
                    end = float(cap["u_end_in"]) * 25.4
                out["mce_target_text_" + k] = (
                    ("IS-MCE target not reached: the curve ended in a numerical stop at %.0f mm of the %.1f mm target; the "
                     "values shown are at the curve end" % (end, mce["target_disp_mm"]))
                    if (end is not None and mce.get("target_disp_mm")) else
                    "IS-MCE target not reached: the curve ended in a numerical stop before it; the values shown are at the curve end")
        out["under_review_" + k] = d in rv
        if d in rv:                                        # check fixes, finding 4
            out["review_" + k] = rv[d].get("summary")
    if po.get("directions"):
        out["vmax_basis"] = VP.BASIS
    if any(out.get("vmax_lower_bound_" + d.lower()) for d in (po.get("directions") or {})):
        out["vmax_lower_bound_note"] = ("≥ marks a lower bound: the curve ended in a numerical stop before the IS-MCE "
                                        "target displacement while still rising, so the strength is at least this")
    return out


def nlrha_results(job):
    nl = _j(os.path.join(job, "nlrha", "nlrha_package.json")) or {}
    lv_pkgs, levels = {}, {}
    for lv, info in (nl.get("levels") or {}).items():
        p = _j(os.path.join(job, "nlrha", info.get("package") or os.path.join(lv, "nlrha_package.json"))) or {}
        lv_pkgs[lv] = p
        rs = p.get("response_summary") or {}
        sel = ((p.get("ground_motions") or {}).get("selected")) or []
        sfs = [float(x["sf"]) for x in sel if x.get("sf") is not None] or [float(x) for x in info.get("scale_factors") or []]
        levels[lv] = dict(pairs=int(rs.get("n_records") or info.get("n_records") or len(sel) or 0),
                          converged=int(rs.get("n_converged") or info.get("n_converged") or 0),
                          drift_pct=_r(100 * info["max_mean_drift"], 2) if info.get("max_mean_drift") is not None else None,
                          sf_min=_r(min(sfs), 3) if sfs else None, sf_max=_r(max(sfs), 3) if sfs else None)
    out = dict(record_set=record_set_name(nl, lv_pkgs), levels=levels)
    if lv_pkgs:                                   # second wave: what the set is, where it comes from, what it lacks
        from nlrha import record_set as RSET
        for lv, p in lv_pkgs.items():
            g = _j(os.path.join(job, "nlrha", lv, "gm_scaling.json")) or {}
            if g and not ((p or {}).get("ground_motions") or {}).get("selected"):
                lv_pkgs[lv] = dict(p or {}, ground_motions=g.get("gm") or {})
        out.update(RSET.facts_for_index(lv_pkgs))
    for lv in ("DBE", "MCE"):
        L = levels.get(lv) or {}
        out["drift_%s_pct" % lv.lower()] = L.get("drift_pct")
        out["pairs_%s" % lv.lower()] = L.get("pairs")
        out["converged_%s" % lv.lower()] = L.get("converged")
    if levels:
        out["converged_text"] = " · ".join("%d/%d" % ((levels.get(lv) or {}).get("converged") or 0, (levels.get(lv) or {}).get("pairs") or 0)
                                           for lv in ("DBE", "MCE") if lv in levels)
        out["n_records"] = sum(L["pairs"] for L in levels.values())        # analyses (pairs x levels): the current page
        out["n_converged"] = sum(L["converged"] for L in levels.values())
    return out


def ddm_results(job):
    from snl.compare import ddm_headline
    from steltic_ddm.cli import reclassify_stored_run
    ddm = _j(os.path.join(job, "ddm_results.json"))
    if not ddm:
        return {}
    # NL-36: results computed before the runaway guard are read through it, so a runaway lambda is never published
    # as a capacity even where the run has not been repeated yet
    dlam = (ddm.get("options") or {}).get("dlam") or 0.05
    n_re = sum(1 for r in ddm.get("runs") or [] if reclassify_stored_run(r, dlam))
    if n_re:
        from steltic_ddm.cli import b12_summary
        ddm["b12_check"] = b12_summary([r.get("b12") for r in ddm["runs"] if r.get("b12")])
    h = ddm_headline(ddm)
    ph = h.get("phi") or {}
    lam = floor3(h["gravity_lambda_u"])
    phi = floor3(h["min_phi_lambda"])
    dc = ceil3(h["b12_dc"])
    lateral_ok = bool(((ddm.get("b11_preconditions") or {}).get("lateral_restraint_confirmed")))
    return dict(gravity_lambda=lam, gravity_lambda_text=txt3(lam),
                gravity_status=STATUS_WORDS.get(h["gravity_status"], (h["gravity_status"] or "").lower().replace("_", " ") or None),
                gravity_combo=h["gravity_combo"],
                min_phi_lambda=phi, min_phi_lambda_text=txt3(phi),
                min_phi_lambda_note=("information only, no pass/fail: phi_s%s is a system resistance factor from US / "
                                     "Australian reliability calibrations%s, not an IS 800 factor; the code check is "
                                     "B-1.2 at lambda = 1" % (
                                         (" = %.2f" % ph["phi_s"]) if ph.get("phi_s") is not None else "",
                                         (" (class %s: %s)" % (ph.get("cls"), ph.get("description"))) if ph.get("cls") else "")),
                min_phi_lambda_combo=h.get("phi_combo"), phi_s=ph.get("phi_s"), phi_s_class=ph.get("cls"),
                phi_s_source=ph.get("source"),
                n_runs=h["n_runs"], solver_failures=h["solver_failures"], runaway_steps=h["runaway_steps"],
                b12_ok=h["b12_ok"], b12_dc=dc, b12_dc_text=txt3(dc),
                b12_member=(h["b12_member"].replace("_", " ") if h["b12_member"] else None), b12_combo=h["b12_combo"],
                b12_not_evaluated=h["b12_not_evaluated"], b12_lambda1_not_reached=len(h["b12_lambda1_not_reached"]),
                b11_met=bool(h["b11_sections_compact"]) and lateral_ok,
                b11_sections_compact=h["b11_sections_compact"],
                b11_lateral_restraint=("confirmed" if lateral_ok else (h["b11_lateral_restraint"] or "not checked")),
                imposed_load_basis=h["imposed_load_basis"],
                reclassified_runaways=n_re,
                reclassified_note=("%d stored sweep(s) read as numerical runaways by the plausibility bounds of the "
                                   "method; the DDM run predates those bounds and is due a re-run" % n_re) if n_re else None)


def meta_line(res):
    p, n, d = res.get("pushover") or {}, res.get("nlrha") or {}, res.get("ddm") or {}
    parts = []
    # check fixes: "≥" on a lower bound, "under review" instead of the number (findings 2 and 4); third wave, P10 and
    # review M1: read up to the IS-MCE target -- "Vmax/VB" for a strength, "V(δt)/VB" for the base shear at the target
    tgt = " up to the IS-MCE target" if p.get("vmax_basis") else ""

    def per_dir(base):
        f = "%.1f" if base == "vb" else "%.2f"
        out = []
        for d in ("x", "y"):
            for kind, lab in (("vmax", "Vmax"), ("v_target", "V(δt)")):
                t, v = p.get("%s_%s_text_%s" % (kind, base, d)), p.get("%s_%s_%s" % (kind, base, d))
                if t or v is not None:                         # the preformatted text, else the number
                    out.append((d.upper(), "%s/%s" % (lab, base.upper()), t or f % v))
                    break
        return out

    def phrase(vals, where=True):
        if len({lab for _, lab, _ in vals}) == 1:
            return "%s%s %s" % (vals[0][1], tgt if (where and vals[0][1].startswith("Vmax")) else "",
                                " / ".join(v for _, _, v in vals))
        return "; ".join("%s %s %s" % (d, lab, v) for d, lab, v in vals)
    w, vb = per_dir("w"), per_dir("vb")
    if p.get("shed") and w:                                   # second wave: no Vmax/VB headline on a shed
        parts.append("Pushover " + phrase(w))
    elif vb:
        parts.append("Pushover %s (%s)" % (phrase(vb), phrase(w, where=False) if w else "V/W not recorded"))
    if n.get("drift_dbe_pct") is not None:
        lv = n.get("levels") or {}
        pairs = sorted({(L or {}).get("pairs") for L in lv.values()})
        if len(pairs) == 1 and pairs[0]:
            runs_txt = "%d record pairs at %s: %d/%d analyses converged" % (
                pairs[0], " and ".join(k for k in ("DBE", "MCE") if k in lv), n.get("n_converged") or 0, n.get("n_records") or 0)
        else:
            runs_txt = "%s pairs converged" % (n.get("converged_text") or "?")
        parts.append("NLRHA mean drift %.2f %% DBE / %.2f %% MCE (%s)" % (
            n["drift_dbe_pct"], n.get("drift_mce_pct") or 0, runs_txt))
    if d.get("gravity_lambda") is not None:
        from snl.public_text import status_words              # third wave, P10: the status in words
        parts.append("DDM gravity λu %s (%s)" % (d["gravity_lambda_text"], status_words(d.get("gravity_status"))))
    if d.get("solver_failures"):
        parts.append("%d DDM solver failure%s" % (d["solver_failures"], "" if d["solver_failures"] == 1 else "s"))
    return " · ".join(parts)


def flag_line(res):
    d = res.get("ddm") or {}
    p = res.get("pushover") or {}
    out = []
    for k in ("x", "y"):                                   # check fixes, findings 1 and 4
        if p.get("review_" + k):
            out.append(p["review_" + k])
        elif p.get("mce_target_text_" + k):
            out.append("Pushover %s: %s." % (k.upper(), p["mce_target_text_" + k]))
    if d.get("b12_ok") is False and (d.get("b12_dc") or 0) > 1.0:
        out.append("DDM: IS 800 Annex B-1.2 section check at λ = 1 not satisfied: %s, D/C %s under %s." % (
            d.get("b12_member"), d.get("b12_dc_text"), d.get("b12_combo")))
    elif d.get("b12_ok") is False and d.get("b12_lambda1_not_reached"):
        out.append("DDM: λ = 1 not reached in %d combination(s), so the IS 800 Annex B-1.2 check is not satisfied there."
                   % d["b12_lambda1_not_reached"])
    if d.get("solver_failures"):
        out.append("DDM: %d sweep%s stopped numerically%s; %s λ is not a capacity." % (
            d["solver_failures"], "" if d["solver_failures"] == 1 else "s",
            ((" (a numerical runaway)" if d["solver_failures"] == 1 else " (%d of them numerical runaways)" % d["runaway_steps"])
             if d.get("runaway_steps") else ""),
            "its" if d["solver_failures"] == 1 else "their"))
    if d.get("gravity_lambda") is not None and d["gravity_lambda"] < 1.0:
        out.append("DDM: gravity λu %s is below 1.0." % d["gravity_lambda_text"])
    return " ".join(out) or None


def run_entry(job, prev=None, rid=None):
    gate = _j(os.path.join(job, "complete_gate.json")) or {}
    # check fixes, finding 3: the gate's reason in plain words (snl/gate_reason.py), and notes without ticket ids even
    # when complete_gate.json was written by older code
    from snl.gate_reason import gate_reason
    from snl.public_text import scrub
    gr = gate_reason(job, gate=gate) if gate else None
    res = dict(gate=gate.get("status"), gate_label=(gr or {}).get("label"), gate_reason_text=(gr or {}).get("text"),
               gate_notes=[scrub(x) for x in (gate.get("notes") or [])], pushover=pushover_results(job),
               nlrha=nlrha_results(job), ddm=ddm_results(job))
    e = dict(prev or {})
    rid = rid or e.get("id")
    e.setdefault("id", rid)
    e.setdefault("title", rid)
    for k, rel in (("summary", "four_analyses.html"), ("viewer", "steltic_viewer_bundle.html"),
                   ("pushover", "pushover/pushover_report.html"), ("nlrha", "nlrha/nlrha_report.html"), ("ddm", "ddm_report.html")):
        e.setdefault(k, "%s/%s" % (rid, rel))
    e["gate"] = res["gate"]
    e["meta"] = meta_line(res)
    fl = flag_line(res)
    if fl:
        e["flag"] = fl
    else:
        e.pop("flag", None)
    e["results"] = _scrubbed(res)
    return e


def _scrubbed(x):
    """Every string of an index entry as public text (no ticket ids, no 'EOR'): stored strings written by older code."""
    from snl.public_text import scrub
    if isinstance(x, dict):
        return {k: _scrubbed(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_scrubbed(v) for v in x]
    return scrub(x) if isinstance(x, str) else x


def find_runs(root):
    out = []
    for dp, dn, fn in os.walk(root):
        if "ddm_results.json" in fn or "complete_gate.json" in fn:
            rel = os.path.relpath(dp, root).replace(os.sep, "/")
            if rel.split("/")[-1].startswith("_"):
                continue
            out.append(rel)
        dn[:] = [d for d in dn if not d.startswith(("_", ".")) and d not in ("pushover", "nlrha", "design", "figs", "rag")]
    return sorted(out)


def build(runs_root, previous=None, overrides=None):
    prev = (_j(previous) or {}).get("examples") if previous else None
    overrides = dict(overrides or {})
    found = set(find_runs(runs_root)) | set(overrides)
    order = [e["id"] for e in (prev or [])] + sorted(found - {e["id"] for e in (prev or [])})
    by_prev = {e["id"]: e for e in (prev or [])}
    examples = []
    for rid in order:
        job = overrides.get(rid) or os.path.join(runs_root, rid)
        if not os.path.isdir(job):
            if rid in by_prev:
                examples.append(by_prev[rid])               # no run folder here: the entry is kept as it was
            continue
        examples.append(run_entry(job, by_prev.get(rid), rid))
    return dict(examples=examples)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", required=True, help="folder holding the run folders at their id paths")
    ap.add_argument("--previous", help="the current index.json (order, titles, links kept)")
    ap.add_argument("--override", action="append", default=[], metavar="ID=FOLDER", help="take run ID from FOLDER")
    ap.add_argument("--out", default="index.json")
    a = ap.parse_args(argv)
    ov = dict(x.split("=", 1) for x in a.override)
    idx = build(a.runs, a.previous, ov)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote %s: %d examples" % (a.out, len(idx["examples"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
