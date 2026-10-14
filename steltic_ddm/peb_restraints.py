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

Stations inside an HR element become GMNIA sub-element nodes (model_gmnia splits the member there); the member ends,
the eaves and the apex already carry the HR ties and joints (no torsional restraint is added at a joint). Returns
None for a package without calc_package['peb'] chains or without cfg['flange_braces'] (every earlier gold)."""
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


def plan(nm, cfg=None):
    cfg = cfg if cfg is not None else (getattr(nm, "cfg", None) or {})
    peb = (getattr(nm, "calc_package", None) or {}).get("peb") or {}
    fb = (cfg or {}).get("flange_braces") or {}
    chains, pm = peb.get("chains") or {}, peb.get("members") or {}
    if not chains or not fb:
        return None
    nodes = nm.nodes
    by_tag = {int(m.tag): m for m in nm.members}
    hr_ties = _springs_by_node(nm)
    both = bool(cfg.get("column_lateral_support_both_flanges"))
    col_tops = {int(ch["top"]) for ch in chains.values() if ch.get("kind") == "column" and ch.get("top") is not None}
    out = dict(stations=[], member_fracs={}, studs=[], skipped=[], counts={})
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
            for h in rs.get("girts_mm") or []:
                if both:
                    st.setdefault(float(h), set()).update({"lateral", "torsion"})
                elif float(h) not in fly_c and END_TOL_MM < float(h) < H - END_TOL_MM:
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
            if any("lateral" in s["kinds"] for s in rec):
                out["studs"].append(dict(chain=cid, base=base, top=top, dir=d,
                                         stations=[i for i, s in enumerate(out["stations"]) if s in rec and "lateral" in s["kinds"]]))
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
            fly_r = coords(rb.get("fly_braces_mm") or [])
            for a in fly_r:
                st.setdefault(a, set()).update({"lateral", "torsion"})
            purl_only = coords(rb.get("purlins_mm") or []) - fly_r - {round(lo, 3), round(hi, 3), round(ridge, 3)}
            for a in (lo, hi, ridge):
                st.setdefault(round(a, 3), set()).add("lateral")
            chain_nodes = {int(n) for m in ms for n in (m.n1, m.n2)}
            for n in chain_nodes & col_tops:                             # interior supports: restraints of both flanges
                st.setdefault(round(nodes[n][ax], 3), set()).add("lateral")
            for a in purl_only:
                if _station_on_chain(ms, nodes, lambda p: p[ax], a)[0] is not None:
                    one_flange[0] += 1
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
                add(cid, "rafter", a, kinds, d, target, m)
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
    return out


def summary(p):
    if not p:
        return None
    c = p["counts"]
    return ("PEB restraints (NL-33, cfg['flange_braces'] as peb_build / D-T1): rafters %d lateral (roof-diaphragm ties) "
            "+ %d torsional; columns %d lateral (wall-line studs, %d columns) + %d torsional; %d HR elements split at a "
            "station; %d one-flange (purlin / girt only) stations not modelled (conservative)"
            % (c["rafter_lateral"], c["rafter_torsion"], c["column_lateral"], c["studs"], c["column_torsion"],
               c["split_elements"], c["not_modelled_one_flange"]))


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v)
