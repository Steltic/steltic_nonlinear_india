"""peb_restraints.py -- NL-33: the out-of-plane restraint system of a PEB shed in the DDM GMNIA model.

The HR PEB model has no purlins, girts or fly braces: the design reads them as member buckling and LTB lengths
(steltic_india peb_build, cfg['flange_braces'], owner ruling D-T1 -- "LTB segment by segment between restraints").
A GMNIA of that bare frame buckles out of plane (IN_Ex1: 10 m columns and 15 m rafter halves free between the
base, the knee and the apex, corotational fibre elements without warping) at lambda ~ 0.26 under 1.5DL + 1.5LL --
a failure of the model, not of the design. This module rebuilds the restraints the design relies on, at the same
stations and with the same reading as peb_build:

  rafters  purlins_mm / fly_braces_mm are plan distances from the eave of each slope (lo + d and hi - d on the
           cfg['roof_planes'] plan axis). Fly-brace station (both flanges held -- the design's Ly): lateral +
           torsional restraint. A purlin-only station holds the outer flange alone; a centroid-line fibre model
           cannot represent a one-flange restraint (a centroid restraint would also hold the free flange), so it is
           NOT modelled -- conservative: the GMNIA unbraced length is the fly-brace spacing (counted in
           counts['not_modelled_one_flange']). The lateral restraint ties the rafter node, in the
           horizontal direction normal to the rafter's plane, to the roof's rigid diaphragm -- through a diaphragm
           slave node and a zeroLength spring, exactly as the HR model ties the eaves (zeroLength 7001xxx, 1e9 N/mm):
           the braced roof the HR declared rigid (IS 1893 7.6.4) carries the purlins.
  columns  girts_mm / fly_braces_mm are heights above the column base (the chain's own `restraints`, else
           cfg['flange_braces']['column']). Fly-brace station (or a girt with
           cfg['column_lateral_support_both_flanges']): lateral + torsional; a girt-only station: not modelled, as a
           purlin-only station. The lateral restraint
           ties the column node, in its weak-axis direction, to the wall line: a rigid stud pinned at the column base
           and tied to the column top, so the restraint follows the wall's racking (base 0, eave as the frame moves)
           and adds no stiffness to the building's own sway.
  torsion  a zeroLength on the member's own axis (dir 4, the element's local frame) to a fixed node.
  canopies cfg['flange_braces']['canopy'] distances from the root: fly-brace stations torsional only.
  warping  the fibre beam-columns have no warping degree of freedom, so a deep welded I between torsional restraints
           twisted under its own major-axis moment at a fraction of its lateral-torsional buckling resistance (IN_Ex1
           1.5DL+1.5LL: 0.03 rad of twist and a 19 kN-m minor moment in the 1.5 m column top between the last fly brace
           and the knee; St Venant-only Mcr 1 100 kN-m against ~15 000 kN-m with warping). warping_intervals[mtag]
           gives each part of an HR element the length L_t between the MODELLED torsional restraints that bound it (2 x
           the gap where a bound is a joint or an end without a torsional spring); model_gmnia gives each welded I
           sub-element the equivalent torsional stiffness G J + pi^2 E Cw / L_t^2 (the warping term of the elastic LTB
           moment, exact for a fork-supported segment).

Stations inside an HR element become GMNIA sub-element nodes (model_gmnia splits the member there); the member ends,
the eaves and the apex already carry the HR ties and joints (no torsional restraint is added at a joint). Returns
None for a package without calc_package['peb'] chains or without cfg['flange_braces'] (every earlier gold) --
unless the package is a ROLLED-section India shed (NL-38, rolled_source below): sloped cfg['roof_planes'] rafters and
columns whose design counted intermediate out-of-plane restraint (K_factors Ky < 1) get the same treatment from the
spacings the HR cfg declares (the brief's when it declares none)."""
import math

END_TOL_MM = 1.0          # a station within 1 mm of an element end is that end node


def _springs_by_node(nm):
    out = set()
    for a in getattr(nm, "springs", None) or []:
        a = list(a)
        if "-dir" not in a:
            continue
        j = a.index("-dir")
        dirs = []
        for v in a[j + 1:]:
            if isinstance(v, str):
                break
            dirs.append(int(v))
        for n in (a[2], a[3]):
            for d in dirs:
                out.add((int(n), d))
    return out


def _station_on_chain(ms, nodes, pos, a):
    """(target, member) for plan / height position `a` on a chain of members: target ("node", tag) at an element end,
    ("frac", mtag, f) inside an element. pos(node) -> the coordinate along the chain."""
    for m in ms:
        a1, a2 = pos(nodes[m.n1]), pos(nodes[m.n2])
        lo, hi = min(a1, a2), max(a1, a2)
        if lo - END_TOL_MM <= a <= hi + END_TOL_MM:
            if abs(a - a1) <= END_TOL_MM:
                return ("node", int(m.n1)), m
            if abs(a - a2) <= END_TOL_MM:
                return ("node", int(m.n2)), m
            return ("frac", int(m.tag), round((a - a1) / (a2 - a1), 9)), m
    return None, None


def _warping_intervals(ms, nodes, pos, c0, c1, tpoints, out):
    """NL-33: for each HR element, [(f0, f1, L_t), ...] -- the element's fractions lying in each gap between the
    chain's torsional restraints and the warping length L_t of that gap, along the member. `tpoints` are the chain
    coordinates (height above the base, plan distance, or distance from a cantilever root) of the MODELLED torsional
    restraints (the fly-brace springs). A gap bounded by a chain end -- base, knee, apex, interior support, cantilever
    root or tip, none of which carries a torsional spring in the GMNIA -- takes L_t = 2 x the gap (a warping length
    with one end free to twist; conservative against the design basis, which counts those joints as restraints of
    both flanges). Sub-elements never straddle a station, so each takes the L_t of its own gap."""
    tp = {round(float(p), 3) for p in tpoints}
    pts = sorted(tp | {round(float(c0), 3), round(float(c1), 3)})
    for m in ms:
        a1, a2 = pos(nodes[m.n1]), pos(nodes[m.n2])
        if abs(a2 - a1) < 1e-9:
            continue
        L = math.dist(nodes[m.n1], nodes[m.n2])
        lo, hi = min(a1, a2), max(a1, a2)
        ivs = []
        for q0, q1 in zip(pts, pts[1:]):
            o0, o1 = max(q0, lo), min(q1, hi)
            if o1 - o0 <= 1e-6:
                continue
            factor = 1.0 if (q0 in tp and q1 in tp) else 2.0
            f0, f1 = sorted(((o0 - a1) / (a2 - a1), (o1 - a1) / (a2 - a1)))
            ivs.append((round(f0, 9), round(f1, 9), round((q1 - q0) * L / abs(a2 - a1) * factor, 1)))
        if ivs:
            out[int(m.tag)] = sorted(ivs)


def plan(nm, cfg=None):
    """The restraint plan of a PEB shed (NL-33, calc_package['peb'] chains + cfg['flange_braces']) or, failing that,
    of a rolled-section shed (NL-38, rolled_source: sloped cfg['roof_planes'] rafters and the columns whose design
    counted intermediate out-of-plane restraint). None when neither applies."""
    cfg = cfg if cfg is not None else (getattr(nm, "cfg", None) or {})
    peb = (getattr(nm, "calc_package", None) or {}).get("peb") or {}
    fb = (cfg or {}).get("flange_braces") or {}
    chains, pm = peb.get("chains") or {}, peb.get("members") or {}
    if not chains or not fb:
        src = rolled_source(nm, cfg) if not chains else None
        if src is None:
            return None
        out = _plan(nm, cfg, src["chains"], src["members"], src["flange_braces"], both=False,
                    col_tops=src["col_tops"], rafter_abs=src["rafter_abs"])
        out["source"] = "rolled"
        out["basis"] = src["basis"]
        return out
    return _plan(nm, cfg, chains, pm, fb, both=bool(cfg.get("column_lateral_support_both_flanges")))


TRUSS_CHORD_ROLES = ("truss_top_chord", "truss_bottom_chord")


def _bottom_chord_ties(cfg, pl, lo, hi):
    """Plan positions of the bottom-chord ties on a roof plane, and where they were read: the plane's (or
    cfg['truss_restraints']) `bottom_chord_ties_mm` (plan distances from the first eave), else the bottom chord's
    out-of-plane buckling length the design used (cfg['member_overrides'] 'truss_bottom_chord[:<section>]' Ly_mm):
    ties every Ly from the eave, inside the span. ([], None) when neither is declared."""
    for src, d in (("roof plane bottom_chord_ties_mm", pl), ("truss_restraints bottom_chord_ties_mm",
                                                              (cfg or {}).get("truss_restraints") or {})):
        v = d.get("bottom_chord_ties_mm")
        if v:
            return sorted(lo + float(x) for x in v if lo + END_TOL_MM < lo + float(x) < hi - END_TOL_MM), src
    for k, o in sorted(((cfg or {}).get("member_overrides") or {}).items()):
        if str(k).split(":")[0] == "truss_bottom_chord" and isinstance(o, dict) and o.get("Ly_mm"):
            ly = float(o["Ly_mm"])
            n = int((hi - lo) / ly + 1e-6)
            return [lo + i * ly for i in range(1, n + 1) if lo + i * ly < hi - END_TOL_MM], \
                "every Ly = %g mm (member_overrides %s)" % (ly, k)
    return [], None


def _truss_chords(nm, cfg, out, hr_ties, add):
    """Third wave (IN_Ex21): the out-of-plane restraints of the chords of roof trusses (members with the roles
    truss_top_chord / truss_bottom_chord). The HR model ties only the eaves; the design reads the chords' out-of-plane
    buckling length between the restraints (IS 800 7.5.3 / 7.2.4: purlins at the top-chord panel points, the
    bottom-chord ties). A chord is a compact angle member, held whole by a purlin cleat or a tie (no one-flange case,
    no lateral-torsional buckling), so each station is a lateral restraint only, tied in the horizontal direction
    normal to the truss to the roof diaphragm as a rafter station (model_gmnia): the braced roof and the
    end-bay bottom-chord bracing the ties are anchored to. Top chord: every chord node at a panel point when the
    plane declares `purlins_at_nodes`, else `purlins_mm` (plan distances from each eave). Bottom chord:
    _bottom_chord_ties. Nodes the HR model already ties are left out."""
    chords = [m for m in nm.members if getattr(m, "role", None) in TRUSS_CHORD_ROLES]
    if not chords:
        return
    nodes = nm.nodes
    planes = (cfg or {}).get("roof_planes") or []
    out.setdefault("truss_basis", [])
    for ip, pl in enumerate(planes):
        ax = 1 if str(pl.get("axis", "Y")).upper() == "Y" else 0
        lo, hi = sorted(float(v) for v in pl.get("eave_coords_mm") or (0.0, 0.0))
        d = 1 if ax == 1 else 2
        lines = {}
        for m in chords:
            a1, a2 = nodes[m.n1][ax], nodes[m.n2][ax]
            if lo - END_TOL_MM <= min(a1, a2) and max(a1, a2) <= hi + END_TOL_MM:
                lines.setdefault((m.role, round(nodes[m.n1][1 - ax], 0)), []).append(m)
        ties, tsrc = _bottom_chord_ties(cfg, pl, lo, hi)
        purl = sorted({round(a, 3) for v in pl.get("purlins_mm") or [] for a in (lo + float(v), hi - float(v))
                       if lo - 1 <= a <= hi + 1})
        out["truss_basis"].append(dict(plane=ip, top_chord=("every panel point (purlins_at_nodes)"
                                                            if pl.get("purlins_at_nodes") else
                                                            ("purlins_mm" if purl else "none declared")),
                                       bottom_chord=tsrc or "none declared", bottom_chord_ties_mm=[round(a, 1) for a in ties]))
        for (role, line), ms in sorted(lines.items()):
            cid = "%s@%g" % (role, line)
            if role == "truss_top_chord":
                if pl.get("purlins_at_nodes"):
                    for n in sorted({int(x) for m in ms for x in (m.n1, m.n2)}, key=lambda q: nodes[q][ax]):
                        if (n, d) not in hr_ties:
                            add(cid, role, nodes[n][ax], {"lateral"}, d, ("node", n), next(m for m in ms if n in (m.n1, m.n2)))
                    continue
                pos = purl
            else:
                pos = ties
            for a in pos:
                target, m = _station_on_chain(ms, nodes, lambda p: p[ax], a)
                if target is None or (target[0] == "node" and (target[1], d) in hr_ties):
                    continue
                add(cid, role, a, {"lateral"}, d, target, m)


def _plan(nm, cfg, chains, pm, fb, both, col_tops=None, rafter_abs=None):
    nodes = nm.nodes
    by_tag = {int(m.tag): m for m in nm.members}
    hr_ties = _springs_by_node(nm)
    if col_tops is None:
        col_tops = {int(ch["top"]) for ch in chains.values() if ch.get("kind") == "column" and ch.get("top") is not None}
    out = dict(stations=[], member_fracs={}, studs=[], skipped=[], counts={}, warping_intervals={})
    one_flange = [0]

    def add(chain, kind, a, kinds, d, target, m):
        if target is None:
            out["skipped"].append(dict(chain=chain, at_mm=a, reason="no element at this station"))
            return None
        st = dict(chain=chain, member_kind=kind, at_mm=round(float(a), 1), kinds=sorted(kinds), dir=d, target=target,
                  mtag=int(m.tag))
        if target[0] == "frac":
            out["member_fracs"].setdefault(target[1], set()).add(target[2])
        out["stations"].append(st)
        return st

    for cid, ch in sorted(chains.items()):
        kind = ch.get("kind")
        tags = [int(t) for mid in (ch.get("members") or []) for t in ((pm.get(mid) or {}).get("elements") or [])]
        ms = [by_tag[t] for t in tags if t in by_tag]
        if not ms:
            continue
        if kind == "column":
            rs = ch.get("restraints") if ch.get("restraints") is not None else (fb.get("column") or {})
            base, top = int(ch["base"]), int(ch["top"])
            zb = nodes[base][2]
            H = nodes[top][2] - zb
            d = 1 if str(ch.get("strong_dir")) == "Y" else 2            # weak-axis (out-of-plane) direction
            st = {}
            fly_c = {float(h) for h in rs.get("fly_braces_mm") or []}
            for h in rs.get("lateral_mm") or []:                       # NL-38 (rolled): lateral restraint only
                st.setdefault(float(h), set()).add("lateral")
            for h in rs.get("girts_mm") or []:
                if both:
                    st.setdefault(float(h), set()).update({"lateral", "torsion"})
                elif float(h) not in fly_c and float(h) not in st and END_TOL_MM < float(h) < H - END_TOL_MM:
                    one_flange[0] += 1
            for h in fly_c:
                st.setdefault(h, set()).update({"lateral", "torsion"})
            rec = []
            for h, kinds in sorted(st.items()):
                if not (END_TOL_MM < h < H - END_TOL_MM):
                    continue
                target, m = _station_on_chain(ms, nodes, lambda p: p[2] - zb, h)
                s = add(cid, "column", h, kinds, d, target, m)
                if s:
                    rec.append(s)
            _warping_intervals(ms, nodes, lambda p: p[2] - zb, 0.0, H,
                               [s_["at_mm"] for s_ in rec if "torsion" in s_["kinds"]], out["warping_intervals"])
            if any("lateral" in s["kinds"] for s in rec):
                stud = dict(chain=cid, base=base, top=top, dir=d,
                            stations=[i for i, s in enumerate(out["stations"]) if s in rec and "lateral" in s["kinds"]])
                if ch.get("base_fixed") is False:
                    stud["base_fixed"] = False                         # NL-38: a column element above a floor / roof
                out["studs"].append(stud)
        elif kind == "rafter":
            planes = cfg.get("roof_planes") or []
            try:
                pl = planes[int(ch.get("plane", 0))]
            except (IndexError, TypeError, ValueError):
                out["skipped"].append(dict(chain=cid, reason="roof plane %s not in cfg['roof_planes']" % ch.get("plane")))
                continue
            ax = 1 if str(pl.get("axis", "Y")).upper() == "Y" else 0     # plan coordinate along the rafter
            lo, hi = sorted(float(v) for v in pl.get("eave_coords_mm") or (0.0, 0.0))
            ridge = float(pl.get("ridge_coord_mm", 0.5 * (lo + hi)))
            d = 1 if ax == 1 else 2                                      # horizontal, normal to the frame plane
            rb = fb.get("rafter") or {}

            def coords(lst):
                s_ = set()
                for v in lst:
                    for a in (lo + float(v), hi - float(v)):
                        if lo - 1 <= a <= hi + 1:
                            s_.add(round(a, 3))
                return s_
            st = {}
            ra = (rafter_abs or {}).get(int(ch.get("plane", 0)))
            if ra is not None:                                           # NL-38 (rolled): absolute plan positions
                fly_r = {round(float(a), 3) for a in ra.get("fly") or []}
                purl_all = {round(float(a), 3) for a in ra.get("purlin") or []}
            else:
                fly_r = coords(rb.get("fly_braces_mm") or [])
                purl_all = coords(rb.get("purlins_mm") or [])
            for a in fly_r:
                st.setdefault(a, set()).update({"lateral", "torsion"})
            purl_only = purl_all - fly_r - {round(lo, 3), round(hi, 3), round(ridge, 3)}
            for a in (lo, hi, ridge):
                st.setdefault(round(a, 3), set()).add("lateral")
            chain_nodes = {int(n) for m in ms for n in (m.n1, m.n2)}
            for n in chain_nodes & col_tops:                             # interior supports: restraints of both flanges
                st.setdefault(round(nodes[n][ax], 3), set()).add("lateral")
            for a in purl_only:
                if _station_on_chain(ms, nodes, lambda p: p[ax], a)[0] is not None:
                    one_flange[0] += 1
            c_lo = min(min(nodes[m.n1][ax], nodes[m.n2][ax]) for m in ms)
            c_hi = max(max(nodes[m.n1][ax], nodes[m.n2][ax]) for m in ms)
            tors = []
            for a, kinds in sorted(st.items()):
                target, m = _station_on_chain(ms, nodes, lambda p: p[ax], a)
                if target is None:
                    continue                                             # station on the other slope's chain
                if target[0] == "node":
                    n = target[1]
                    kinds = set(kinds)
                    if n in col_tops or abs(a - ridge) <= END_TOL_MM or abs(a - lo) <= END_TOL_MM or abs(a - hi) <= END_TOL_MM:
                        kinds.discard("torsion")                         # a joint (knee, apex, support): no torsion spring
                    if (n, d) in hr_ties:
                        kinds.discard("lateral")                         # the HR model already ties it
                    if not kinds:
                        continue
                if "torsion" in kinds:
                    tors.append(a)
                add(cid, "rafter", a, kinds, d, target, m)
            _warping_intervals(ms, nodes, lambda p: p[ax], c_lo, c_hi, tors, out["warping_intervals"])
        elif kind == "canopy":
            # NL-33: a cantilever (attached canopy): cfg['flange_braces']['canopy'] distances from the root (peb_build
            # reads other beam members the same way). Fly-brace stations: torsional restraint only -- the canopy
            # purlins tie to no modelled diaphragm, so no lateral restraint (conservative); purlin-only: not modelled.
            cb = fb.get("canopy") or {}
            root = (ch.get("nodes") or [None])[0]
            if root is None or int(root) not in nodes:
                out["skipped"].append(dict(chain=cid, reason="canopy root node not in the model"))
                continue
            r0 = nodes[int(root)]
            Lc = max(math.dist(r0, nodes[n]) for m in ms for n in (m.n1, m.n2))
            pos = (lambda r0_: (lambda p: math.dist(r0_, p)))(r0)
            fly_k = {round(float(v), 3) for v in cb.get("fly_braces_mm") or []}
            one_flange[0] += sum(1 for v in cb.get("purlins_mm") or []
                                 if round(float(v), 3) not in fly_k and END_TOL_MM < float(v) < Lc - END_TOL_MM)
            tors = []
            for a in sorted(fly_k):
                if not (END_TOL_MM < a < Lc - END_TOL_MM):
                    continue
                target, m = _station_on_chain(ms, nodes, pos, a)
                if add(cid, "canopy", a, {"torsion"}, None, target, m):
                    tors.append(a)
            _warping_intervals(ms, nodes, pos, 0.0, Lc, tors, out["warping_intervals"])
    _truss_chords(nm, cfg, out, hr_ties, add)
    # several chains can name the same HR node (an apex shared by both slopes): keep one station per node and direction
    seen, keep = {}, []
    for i, s in enumerate(out["stations"]):
        key = (s["target"], s["dir"])
        if key in seen:
            prev = keep[seen[key]]
            prev["kinds"] = sorted(set(prev["kinds"]) | set(s["kinds"]))
            remap = seen[key]
        else:
            seen[key] = len(keep); keep.append(s); remap = seen[key]
        s["_new"] = remap
    for stud in out["studs"]:
        stud["stations"] = sorted({out["stations"][i]["_new"] for i in stud["stations"]})
    for s in keep:
        s.pop("_new", None)
    out["stations"] = keep
    out["member_fracs"] = {k: sorted(v) for k, v in out["member_fracs"].items()}
    c = out["counts"]
    c["rafter_lateral"] = sum(1 for s in keep if s["member_kind"] == "rafter" and "lateral" in s["kinds"])
    c["rafter_torsion"] = sum(1 for s in keep if s["member_kind"] == "rafter" and "torsion" in s["kinds"])
    c["column_lateral"] = sum(1 for s in keep if s["member_kind"] == "column" and "lateral" in s["kinds"])
    c["column_torsion"] = sum(1 for s in keep if s["member_kind"] == "column" and "torsion" in s["kinds"])
    c["studs"] = len(out["studs"])
    c["split_elements"] = len(out["member_fracs"])
    c["not_modelled_one_flange"] = one_flange[0]
    c["canopy_torsion"] = sum(1 for s in keep if s["member_kind"] == "canopy" and "torsion" in s["kinds"])
    c["truss_top_chord_lateral"] = sum(1 for s in keep if s["member_kind"] == "truss_top_chord")
    c["truss_bottom_chord_lateral"] = sum(1 for s in keep if s["member_kind"] == "truss_bottom_chord")
    wl = [iv[2] for ivs in out["warping_intervals"].values() for iv in ivs]
    c["warping_length_mm"] = [min(wl), max(wl)] if wl else None
    return out


# --------------------------------------------------------------------------------------------------------------------
# NL-38: rolled-section (non-PEB) sheds
# --------------------------------------------------------------------------------------------------------------------
# Spacings the briefs state, used ONLY when the HR cfg declares none (the plan then says so). Quoted from
# steltic_india/test_buildings/<brief>.txt; mm.
BRIEF_SPACINGS = {
    "IN_Ex6_OMRF_warehouse_mezzanine_Hyderabad": dict(purlin=1500.0, girt=2000.0,
                                                      quote="purlins at 1.5 m, girts at 2.0 m"),
    "IN_Ex7_Crane_bay_OMRF_OCBF_Vizag": dict(purlin=1500.0, girt=2300.0, quote="purlins at 1.5 m, girts at 2.3 m"),
    "IN_Ex8_SMF_portal_Chennai_wind": dict(purlin=1500.0, girt=2000.0, fly=3000.0,
                                           quote="purlins at 1.5 m (roof), girts at 2.0 m (walls) ... fly braces at 3.0 m"),
    "IN_Ex9_Gable_warehouse_SMF_SCBF_snow_Shimla": dict(purlin=1500.0, girt=1500.0,
                                                        quote="purlins and girts at 1.5 m as IS 808 channels"),
    "IN_Ex10_SCBF_bigbox_flexdiaphragm_Indore": dict(girt=2375.0,
                                                     quote="Wall girts at 2.375 m restrain the column weak axis"),
}


def _by_role(v, role):
    """A cfg value that is a number or {role: number} (LLT_sag_mm / LLT_hog_mm convention)."""
    if isinstance(v, dict):
        v = v.get(role)
    try:
        return float(v) if v is not None and float(v) > 0 else None
    except (TypeError, ValueError):
        return None


def _secondary_spacing(cfg, word):
    for sm in (cfg.get("secondary_members") or []):
        txt = ("%s %s" % (sm.get("id") or "", sm.get("kind") or "")).lower()
        if word in txt and sm.get("spacing_mm"):
            try:
                return float(sm["spacing_mm"]), "cfg['secondary_members'] '%s' spacing_mm" % (sm.get("id") or sm.get("kind"))
            except (TypeError, ValueError):
                pass
    return None, None


def rolled_spacings(cfg, name=None):
    """(spacings, sources, fallback) for a rolled shed, from the HR cfg first:
      fly     rafter fly braces (both flanges): cfg['LLT_hog_mm']['roof'] -- the design's bottom-flange LTB length;
      purlin  roof purlins (top flange only): cfg['secondary_members'] purlin spacing_mm, else cfg['LLT_sag_mm']['roof'];
      girt    wall girts (outer flange only): cfg['secondary_members'] girt spacing_mm.
    A spacing the cfg does not declare comes from BRIEF_SPACINGS[name] and is listed in `fallback`."""
    sp, src, fb = {}, {}, []
    v = _by_role(cfg.get("LLT_hog_mm"), "roof")
    if v:
        sp["fly"], src["fly"] = v, "cfg['LLT_hog_mm']['roof'] (the design's bottom-flange LTB length, fly-brace spacing)"
    v, s_ = _secondary_spacing(cfg, "purlin")
    if not v:
        v = _by_role(cfg.get("LLT_sag_mm"), "roof")
        s_ = "cfg['LLT_sag_mm']['roof'] (the design's top-flange LTB length, purlin spacing)" if v else None
    if v:
        sp["purlin"], src["purlin"] = v, s_
    v, s_ = _secondary_spacing(cfg, "girt")
    if v:
        sp["girt"], src["girt"] = v, s_
    brief = BRIEF_SPACINGS.get(str(name or cfg.get("name") or ""))
    for k in ("fly", "purlin", "girt"):
        if k not in sp and brief and brief.get(k):
            sp[k], src[k] = brief[k], "brief (cfg declares none): '%s'" % brief["quote"]
            fb.append(k)
    return sp, src, fb


def _india(cfg):
    plan_ = (cfg or {}).get("load_plan") if isinstance(cfg, dict) else None
    return str((plan_ or {}).get("jurisdiction") or (cfg or {}).get("jurisdiction") or "").lower() == "india"


def _side_positions(eave, ridge, dz, spacing):
    """Plan positions of restraints at `spacing` along the SLOPE from the eave at plan coordinate `eave` towards the
    ridge (the last gap, next to the ridge, may be shorter)."""
    run = ridge - eave
    if abs(run) < 1.0 or not spacing:
        return []
    Ls = math.hypot(run, dz)
    out, k = [], 1
    while k * spacing < Ls - END_TOL_MM:
        out.append(eave + run * (k * spacing / Ls))
        k += 1
    return out


def rolled_source(nm, cfg):
    """NL-38: restraint chains of a ROLLED-section (non-PEB) India shed, from the HR cfg -- the out-of-plane restraint
    the member design counted on, which the HR frame model (and so the GMNIA) does not contain:

      rafters  every sloped beam of a cfg['roof_planes'] plane, chained per frame line. Fly braces (both flanges held,
               the design's LLT_hog_mm['roof']) at that spacing along the slope from each eave: lateral restraint tied to
               the roof diaphragm + torsional restraint; plus a lateral tie at the apex and the eaves where the HR model
               has none (as NL-33). Purlins (top flange only) are counted, not modelled (a centroid-line model cannot
               hold one flange; conservative). Corotational rafters without these restraints buckle out of plane far
               below their in-plane capacity (IN_Ex9 2026-09: lambda 0.61 under 1.5DL+1.5LL+1.5SL with the HR roof
               NPB600 at D/C 0.81).
      columns  every column element whose role has K_factors Ky < 1 -- the design's out-of-plane buckling length
               Ky x L counts intermediate restraint (girts / fly braces). Lateral restraint (weak-axis direction, to a
               rigid stud on the element's chord) at k x Ky x L from the element's foot, exactly the HR flexural basis.
               No torsional restraint: the HR LTB check of a column uses the element length (no LLT declared).
      warping  rolled I sections in a chain carry G J + pi^2 E Cw / L_t^2 (L_t as NL-33: between modelled torsional
               restraints, twice the gap next to a joint without one).

    Returns None for a PEB package, a non-India cfg, or a shed with neither sloped rafters nor such columns."""
    cfg = cfg or {}
    if not _india(cfg) or ((getattr(nm, "calc_package", None) or {}).get("peb") or {}).get("chains"):
        return None
    nodes = nm.nodes
    name = cfg.get("name") or getattr(nm, "name", None)
    sp, src, fallback = rolled_spacings(cfg, name)
    chains, pm, rafter_abs = {}, {}, {}
    n_raf = n_col = 0
    # ---- rafters
    for idx, pl in enumerate(cfg.get("roof_planes") or []):
        try:
            ax = 1 if str(pl.get("axis", "Y")).upper() == "Y" else 0
            lo, hi = sorted(float(v) for v in pl.get("eave_coords_mm") or (0.0, 0.0))
            ridge = float(pl.get("ridge_coord_mm", 0.5 * (lo + hi)))
            dz = float(pl.get("ridge_z_mm", 0.0)) - float(pl.get("eave_z_mm", 0.0))
        except (TypeError, ValueError):
            continue
        oax = 1 - ax
        lines = {}
        for m in nm.members:
            if m.kind != "beam" or m.role == "link":
                continue
            p1, p2 = nodes[m.n1], nodes[m.n2]
            if abs(p1[2] - p2[2]) <= 1.0 or abs(p1[oax] - p2[oax]) > 1.0:
                continue                                         # not a sloped rafter in this plane's direction
            if not all(lo - 1.0 <= p[ax] <= hi + 1.0 for p in (p1, p2)):
                continue
            lines.setdefault(round(p1[oax], 0), []).append(m)
        if not lines:
            continue
        fly = sp.get("fly")
        rafter_abs[idx] = dict(
            fly=sorted(set(round(a, 3) for a in _side_positions(lo, ridge, dz, fly) + _side_positions(hi, ridge, dz, fly))),
            purlin=sorted(set(round(a, 3) for a in _side_positions(lo, ridge, dz, sp.get("purlin")) +
                              _side_positions(hi, ridge, dz, sp.get("purlin")))))
        for c, ms in sorted(lines.items()):
            cid = "R%d@%.0f" % (idx, c)
            ms = sorted(ms, key=lambda m: min(nodes[m.n1][ax], nodes[m.n2][ax]))
            pm[cid] = dict(elements=[int(m.tag) for m in ms])
            chains[cid] = dict(kind="rafter", plane=idx, members=[cid])
            n_raf += 1
    # ---- columns with a declared out-of-plane restraint (Ky < 1)
    K = cfg.get("K_factors") or {}
    for m in nm.members:
        if m.kind != "col":
            continue
        kk = K.get(m.role) or K.get("col") or {}
        try:
            Ky = float(kk.get("Ky")) if isinstance(kk, dict) and kk.get("Ky") is not None else None
        except (TypeError, ValueError):
            Ky = None
        if not Ky or Ky >= 1.0:
            continue
        a, b = (m.n1, m.n2) if nodes[m.n1][2] <= nodes[m.n2][2] else (m.n2, m.n1)
        H = nodes[b][2] - nodes[a][2]
        if H <= 1.0 or math.hypot(nodes[b][0] - nodes[a][0], nodes[b][1] - nodes[a][1]) > 1.0:
            continue                                             # vertical columns only
        s = Ky * H
        lat = []
        k = 1
        while k * s < H - END_TOL_MM:
            lat.append(round(k * s, 1)); k += 1
        if not lat:
            continue
        girts = []
        if sp.get("girt"):
            k = 1
            z0 = nodes[a][2]
            # girts at the declared spacing from the ground (wall line), inside this element
            while k * sp["girt"] < nodes[b][2] - END_TOL_MM:
                h = k * sp["girt"] - z0
                if END_TOL_MM < h < H - END_TOL_MM:
                    girts.append(round(h, 1))
                k += 1
        sd = "Y" if int(getattr(m, "transf", 1) or 1) == 1 else "X"     # transf 1: strong axis resists Y (engine3d)
        cid = "C%d" % int(m.tag)
        pm[cid] = dict(elements=[int(m.tag)])
        chains[cid] = dict(kind="column", base=int(a), top=int(b), strong_dir=sd, members=[cid],
                           restraints=dict(lateral_mm=lat, girts_mm=girts), base_fixed=(a in nm.fixes),
                           Ky=Ky, KyL_mm=round(s, 1))
        n_col += 1
    if not chains:
        return None
    col_tops = {int(max((m.n1, m.n2), key=lambda t: nodes[t][2])) for m in nm.members if m.kind == "col"}
    basis = dict(spacings_mm=sp, sources=src, brief_fallback=fallback, rafter_chains=n_raf, column_elements=n_col,
                 column_rule="lateral restraint at k x Ky x L (cfg K_factors[role]['Ky'] < 1), no torsional restraint "
                             "(the HR column LTB check uses the element length)",
                 rafter_rule="fly braces (lateral + torsional) at LLT_hog_mm['roof'] along the slope from each eave; "
                             "purlins (top flange only) not modelled")
    return dict(chains=chains, members=pm, flange_braces={"rafter": {}}, col_tops=col_tops, rafter_abs=rafter_abs,
                basis=basis)


def summary(p):
    if not p:
        return None
    c = p["counts"]
    if p.get("source") == "rolled":
        b = p.get("basis") or {}
        spc = b.get("spacings_mm") or {}
        return ("Rolled-section restraints (from the HR design input%s): rafters %d lateral (roof-diaphragm ties) + %d "
                "torsional (fly braces at %s mm along the slope); columns %d lateral (studs on %d column elements at "
                "Ky·L, no torsional); %d HR elements split at a station; %d one-flange (purlin / girt only) stations "
                "not modelled (conservative); warping lengths %s mm"
                % (("; %s spacing from the project brief" % ", ".join(b["brief_fallback"])) if b.get("brief_fallback") else "",
                   c["rafter_lateral"], c["rafter_torsion"], ("%.0f" % spc["fly"]) if spc.get("fly") else "—",
                   c["column_lateral"], c["studs"], c["split_elements"], c["not_modelled_one_flange"],
                   "-".join("%.0f" % v for v in (c.get("warping_length_mm") or [])) or "none"))
    return ("PEB restraints (the purlin, girt and fly-brace stations of the HR design, read as the HR design reads "
            "them: Steltic design ruling D-T1, lateral-torsional buckling checked segment by segment between "
            "restraints): rafters %d lateral (roof-diaphragm ties) "
            "+ %d torsional; columns %d lateral (wall-line studs, %d columns) + %d torsional; canopies %d torsional; %d HR "
            "elements split at a station; %d one-flange (purlin / girt only) stations not modelled (conservative); "
            "warping lengths %s mm"
            % (c["rafter_lateral"], c["rafter_torsion"], c["column_lateral"], c["studs"], c["column_torsion"],
               c.get("canopy_torsion", 0), c["split_elements"], c["not_modelled_one_flange"],
               "-".join("%.0f" % v for v in (c.get("warping_length_mm") or [])) or "none"))


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v)
