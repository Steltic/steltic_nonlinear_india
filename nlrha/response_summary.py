"""response_summary.py -- India NLRHA response summary (owner ruling D7: informative, no verdict).

Replaces the ASCE 7-22 §16.4 evaluation for India jobs. It reports, per level (DBE / MCE):
  * storey drifts: per record and the suite mean / max (X, Y, both edges);
  * peak base shear per record vs the IS 1893 design VB and vs the elastic base shear Sa(T1)·W at the level;
  * displacement ductility demand = peak roof displacement / yield roof displacement of the pushover bilinear fit
    (when a pushover package is available);
  * member fibre-strain ratios (eps/eps_y) and chord rotations per (kind, section, storey) with the IS 800 §12
    joint-rotation capacity shown as a REFERENCE value (and IS 18168 where it gives one);
  * brace ductility (tension / shortening over the yield deformation) and buckling counts;
  * force in capacity-protected (force-controlled) columns vs IS 800 7.1.2 Pd -- information;
  * non_vacuous: False when the SFRS members produced no rows (an all([]) can never pass -- WP4.3).
There is no ACCEPTABLE / NOT ACCEPTABLE, no ASCE drift limit, no Risk Category.
"""
from __future__ import annotations
import math
import numpy as np

IS_NL_STATEMENT = ("IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; "
                   "results are for information.")
KIP_TO_KN = 4.4482216152605


def _sfrs_kinds(system: str | None) -> set:
    s = str(system or "").upper()
    if "EBF" in s or "ECCENTRIC" in s:
        return {"brace", "col", "beam", "link"}                 # NL-10: the links are the EBF's yielding members
    if any(k in s for k in ("CBF", "SBF", "BRACE")):
        return {"brace", "col", "beam"}
    return {"col", "beam"}


def summarise(results, pkg, level: str, target_label: str, T1: float | None = None, pushover_pkg: dict | None = None,
              fc_rows: list | None = None) -> dict:
    from pushover import india_materials as IM
    from pushover.member_response import group_summary
    from . import india_hazard as IH
    ind = pkg.basis.india or {}
    ok = [r for r in results if r.get("converged")]
    n_story = len(results[0]["heights"]) if results else 0
    heights = results[0]["heights"] if results else []
    per = []
    for r in results:
        pk = np.asarray(r.get("peak_story_drift") or np.zeros((n_story, 2)))
        vb = r.get("peak_base_shear_kip") or [None, None]
        per.append(dict(record=r["record"], label=r["label"], sf=r["sf"], converged=bool(r["converged"]), reason=r.get("reason"),
                        max_drift_X=float(pk[:, 0].max()) if r["converged"] else None,
                        max_drift_Y=float(pk[:, 1].max()) if r["converged"] else None,
                        storey_drift=pk.tolist() if r["converged"] else None,
                        peak_roof_mm=[v * 25.4 for v in (r.get("peak_roof_in") or [0, 0])],
                        residual_max=(max(r["residual_drift"]) if r["converged"] else None),
                        base_shear_kN=[(v * KIP_TO_KN if v is not None else None) for v in vb],
                        seconds=r.get("seconds"), steps=r.get("steps"), retry=r.get("retry")))
    drifts = np.array([r["peak_story_drift"] for r in ok]) if ok else np.zeros((0, n_story, 2))
    storey = []
    for i in range(n_story):
        storey.append(dict(story=i + 1, h_mm=heights[i] * 25.4,
                           mean_X=float(drifts[:, i, 0].mean()) if len(ok) else None,
                           mean_Y=float(drifts[:, i, 1].mean()) if len(ok) else None,
                           max_X=float(drifts[:, i, 0].max()) if len(ok) else None,
                           max_Y=float(drifts[:, i, 1].max()) if len(ok) else None))
    # base shear
    VB = ind.get("VB_kN"); W = ind.get("W_kN")
    VBx, VBy = IH.vb_direction_kN(ind, "X"), IH.vb_direction_kN(ind, "Y")     # NL-4: V-bar_B per direction
    vbx = [p["base_shear_kN"][0] for p in per if p["converged"] and p["base_shear_kN"][0] is not None]
    vby = [p["base_shear_kN"][1] for p in per if p["converged"] and p["base_shear_kN"][1] is not None]
    Sa_T1 = None; V_el = None
    if T1 and ind.get("Z") is not None:
        Sa_T1 = IH.elastic_sa(T1, Z=ind["Z"], I=ind["I"], soil=ind["soil"], level=level)
        V_el = Sa_T1 * W if W else None
    bs = dict(mean_X_kN=float(np.mean(vbx)) if vbx else None, mean_Y_kN=float(np.mean(vby)) if vby else None,
              max_kN=float(max(vbx + vby)) if (vbx or vby) else None, VB_design_kN=VB,
              VB_design_X_kN=VBx, VB_design_Y_kN=VBy,
              elastic_kN=V_el, Sa_T1_g=Sa_T1, T1_s=T1,
              basis="VB: IS 1893 design base shear per direction (V-bar_B of the HR package, per-direction R); "
                    "elastic = Sa(T1)·W at this level (no R)")
    ratios = []
    if VBx and bs["mean_X_kN"] is not None:
        bs["mean_X_over_VB"] = bs["mean_X_kN"] / VBx; ratios.append(bs["mean_X_over_VB"])
    if VBy and bs["mean_Y_kN"] is not None:
        bs["mean_Y_over_VB"] = bs["mean_Y_kN"] / VBy; ratios.append(bs["mean_Y_over_VB"])
    if ratios:
        bs["mean_over_VB"] = max(ratios)
    if V_el and bs["max_kN"]:
        bs["mean_over_elastic"] = max(v for v in (bs["mean_X_kN"], bs["mean_Y_kN"]) if v is not None) / V_el
    # ductility from the pushover bilinear fit
    duct = None
    if pushover_pkg and pushover_pkg.get("directions"):
        duct = {}
        for d, j in (("X", 0), ("Y", 1)):
            dd = pushover_pkg["directions"].get(d) or {}
            uy = (dd.get("capacity") or {}).get("uy_fit_in")
            roofs = [p["peak_roof_mm"][j] / 25.4 for p in per if p["converged"]]
            if uy and roofs:
                duct[d] = dict(uy_mm=uy * 25.4, mu_mean=float(np.mean(roofs) / uy), mu_max=float(max(roofs) / uy))
    # members
    ref = IM.reference_rotation(pkg.basis.system)
    meta = results[0].get("member_meta") if results else None
    mem = group_summary([r.get("member_peaks") or {} for r in ok], meta, ref) if (meta and ok) else dict(member_groups=[], brace_groups=[], link_groups=[])
    kinds = _sfrs_kinds(pkg.basis.system)
    have = {g["kind"] for g in mem["member_groups"]} | ({"brace"} if mem["brace_groups"] else set()) | \
        ({"link"} if mem.get("link_groups") else set())
    missing = sorted(kinds - have)
    nv = dict(ok=not missing and bool(ok), sfrs_kinds=sorted(kinds), missing_kinds=missing,
              n_member_rows=len(mem["member_groups"]), n_brace_rows=len(mem["brace_groups"]),
              note="rows must exist for every SFRS member kind; an empty table never passes (WP4.3)")
    return dict(
        jurisdiction="india", level=level, target_label=target_label, statement=IS_NL_STATEMENT,
        acceptance_basis=None, verdict=None,
        n_records=len(results), n_converged=len(ok), converged_all=len(ok) == len(results) and bool(results),
        per_record=per, story=storey, base_shear=bs, ductility=duct,
        member_groups=mem["member_groups"], brace_groups=mem["brace_groups"], link_groups=mem.get("link_groups") or [],
        reference_rotation=ref,
        force_controlled_columns=fc_rows or [], non_vacuous=nv,
        max_mean_drift=(max(max(s["mean_X"], s["mean_Y"]) for s in storey) if (storey and ok) else None),
        max_peak_drift=(max(max(s["max_X"], s["max_Y"]) for s in storey) if (storey and ok) else None),
    )


def fc_columns(results, pkg, PG: dict) -> list:
    """Peak compression in columns vs IS 800 7.1.2 Pd (information). Worst per (section, storey)."""
    from pushover import india_materials as IM, india_model as IMD
    ok = [r for r in results if r.get("converged")]
    if not ok:
        return []
    best = {}
    for c in (ok[0].get("peak_colN") or {}):
        vals = [float(r["peak_colN"].get(c, 0.0)) for r in ok]
        sec = pkg.schedule.get(c, {}).get("section")
        e = next((e for e in pkg.model.elements if e["tag"] == c), None)
        if not sec or e is None:
            continue
        L_mm = math.dist(pkg.model.nodes[e["n1"]], pkg.model.nodes[e["n2"]]) * 25.4
        fy = IMD.fy_section(pkg, sec, "col", tag=c)["fy_MPa"]
        pd = IM.is800_Pd(sec, L_mm, fy, hollow_forming=IMD.material_ctx(pkg)["plan"]["hollow_forming"])
        Pmean = float(np.mean(vals)) * KIP_TO_KN; Pmax = float(np.max(vals)) * KIP_TO_KN
        row = dict(ele=c, section=sec, z_mm=pkg.model.nodes[e["n1"]][2] * 25.4, P_mean_kN=Pmean, P_max_kN=Pmax,
                   PG_kN=PG.get(c, 0.0) * KIP_TO_KN, Pd_kN=pd["Pd_N"] / 1e3, ratio_mean=Pmean / (pd["Pd_N"] / 1e3),
                   ratio_max=Pmax / (pd["Pd_N"] / 1e3), cls=pd["cls"], KLr=pd["KLr"], cite=pd["cite"])
        k = (sec, round(row["z_mm"]))
        if k not in best or row["ratio_max"] > best[k]["ratio_max"]:
            best[k] = row
    return sorted(best.values(), key=lambda r: (r["z_mm"], r["section"]))
