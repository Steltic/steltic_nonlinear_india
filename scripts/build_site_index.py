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
  gate, gate_notes             complete_gate.json status and notes (solver failures are stated, never silent)
  pushover                     per direction Vmax/VB and Vmax/W, whether the curve ended in a numerical stop (Vmax a
                               lower bound) and whether the IS-MCE target displacement was reached
  nlrha                        the record set ("FEMA P-695 far-field set, amplitude-scaled to the IS 1893 spectrum"),
                               per level the number of record pairs and how many converged, the max mean storey drift
                               and the scale-factor range; n_records / n_converged are kept for the current page and
                               count analyses (pairs x levels)
  ddm                          gravity lambda_u as the headline, min phi_s x lambda_u kept as information (US/AU
                               calibration), solver-failure counts, B-1.2 (worst D/C rounded UP), b11_met and its parts
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


def pushover_results(job):
    po = _j(os.path.join(job, "pushover", "pushover_package.json")) or {}
    out = {}
    for d, dd in sorted((po.get("directions") or {}).items()):
        cap = dd.get("capacity") or {}
        k = d.lower()
        out["vmax_vb_" + k] = _r(cap.get("Vmax_over_VB"), 1)
        out["vmax_w_" + k] = _r(cap.get("Vmax_over_W"), 3)
        tail = cap.get("tail_status") or (dd.get("tail") or {}).get("status")
        out["vmax_lower_bound_" + k] = (tail == "lower_bound") or str(dd.get("stop_reason") or "").startswith("solver")
        mce = (dd.get("nsp") or {}).get("IS-MCE") or {}
        if mce:
            out["mce_target_reached_" + k] = bool(mce.get("reached_target"))
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
    lam = floor3(h["gravity_lambda_u"])
    phi = floor3(h["min_phi_lambda"])
    dc = ceil3(h["b12_dc"])
    lateral_ok = bool(((ddm.get("b11_preconditions") or {}).get("lateral_restraint_confirmed")))
    return dict(gravity_lambda=lam, gravity_lambda_text=txt3(lam),
                gravity_status=STATUS_WORDS.get(h["gravity_status"], (h["gravity_status"] or "").lower().replace("_", " ") or None),
                gravity_combo=h["gravity_combo"],
                min_phi_lambda=phi, min_phi_lambda_text=txt3(phi),
                min_phi_lambda_note="information only: phi_s from US/AU reliability calibrations, not IS 800 / IS 875",
                n_runs=h["n_runs"], solver_failures=h["solver_failures"], runaway_steps=h["runaway_steps"],
                b12_ok=h["b12_ok"], b12_dc=dc, b12_dc_text=txt3(dc),
                b12_member=(h["b12_member"].replace("_", " ") if h["b12_member"] else None), b12_combo=h["b12_combo"],
                b12_not_evaluated=h["b12_not_evaluated"], b12_lambda1_not_reached=len(h["b12_lambda1_not_reached"]),
                b11_met=bool(h["b11_sections_compact"]) and lateral_ok,
                b11_sections_compact=h["b11_sections_compact"],
                b11_lateral_restraint=("confirmed" if lateral_ok else (h["b11_lateral_restraint"] or "not checked")),
                imposed_load_basis=h["imposed_load_basis"],
                reclassified_runaways=n_re,
                reclassified_note=("%d stored sweep(s) read as numerical runaways (NL-36); the DDM run predates the guard "
                                   "and is due a re-run" % n_re) if n_re else None)


def meta_line(res):
    p, n, d = res.get("pushover") or {}, res.get("nlrha") or {}, res.get("ddm") or {}
    parts = []
    vb = [p.get("vmax_vb_x"), p.get("vmax_vb_y")]
    if any(v is not None for v in vb):
        w = [p.get("vmax_w_x"), p.get("vmax_w_y")]
        parts.append("Pushover Vmax/VB %s (Vmax/W %s)" % (" / ".join("%.1f" % v for v in vb if v is not None),
                                                          " / ".join("%.2f" % v for v in w if v is not None)))
    if n.get("drift_dbe_pct") is not None:
        parts.append("NLRHA mean drift %.2f %% DBE / %.2f %% MCE (%s pairs converged)" % (
            n["drift_dbe_pct"], n.get("drift_mce_pct") or 0, n.get("converged_text") or "?"))
    if d.get("gravity_lambda") is not None:
        parts.append("DDM gravity λu %s (%s)" % (d["gravity_lambda_text"], d.get("gravity_status")))
    if d.get("solver_failures"):
        parts.append("%d DDM solver failure%s" % (d["solver_failures"], "" if d["solver_failures"] == 1 else "s"))
    return " · ".join(parts)


def flag_line(res):
    d = res.get("ddm") or {}
    out = []
    if d.get("b12_ok") is False and (d.get("b12_dc") or 0) > 1.0:
        out.append("DDM: IS 800 Annex B-1.2 section check at λ = 1 not satisfied: %s, D/C %s under %s." % (
            d.get("b12_member"), d.get("b12_dc_text"), d.get("b12_combo")))
    elif d.get("b12_ok") is False and d.get("b12_lambda1_not_reached"):
        out.append("DDM: λ = 1 not reached in %d combination(s), so the IS 800 Annex B-1.2 check is not satisfied there."
                   % d["b12_lambda1_not_reached"])
    if d.get("solver_failures"):
        out.append("DDM: %d sweep(s) stopped numerically (SOLVER_FAILURE%s); their λ is not a capacity." % (
            d["solver_failures"], (", %d numerical runaway(s)" % d["runaway_steps"]) if d.get("runaway_steps") else ""))
    if d.get("gravity_lambda") is not None and d["gravity_lambda"] < 1.0:
        out.append("DDM: gravity λu %s is below 1.0." % d["gravity_lambda_text"])
    return " ".join(out) or None


def run_entry(job, prev=None, rid=None):
    gate = _j(os.path.join(job, "complete_gate.json")) or {}
    res = dict(gate=gate.get("status"), gate_notes=gate.get("notes") or [], pushover=pushover_results(job),
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
    e["results"] = res
    return e


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
