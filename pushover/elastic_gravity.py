"""elastic_gravity.py -- gravity-only members modelled elastic, with a yield check (NL-21).

Standard practice for nonlinear analysis of a building: the seismic-force-resisting system (SFRS) is modelled
nonlinear, the gravity system elastic, and the gravity members are CHECKED to stay elastic. On the India path the
members that are not part of the SFRS stay elastic by default:

  * columns whose HR package role is `gravity_col`;
  * beams pinned about the major axis at BOTH ends (HR `-releasey/-releasez 3`) that are not in a braced / EBF bay
    (a beam with an end at a brace node whose plan projection it overlaps, or collinear with an EBF link it touches,
    is SFRS even when pinned; neighbouring-bay beams that only touch a brace node stay gravity).

Everything else -- lateral columns, moment-connected beams, braces, EBF links, panel zones -- is unchanged. An elastic
member is built as TWO elasticBeamColumn sub-elements (the HR A, E, G, J, Iy, Iz, transformation and end releases;
the extra mid node carries only the numerical mass), so the HR gravity replay and the mid-span moment are exact
for the uniform loads the HR records.

After each analysis the peak demand of every elastic member is checked:
    ratio = |N| / (fy A) + |M_major| / (fy S_major) + |M_minor| / (fy S_minor)      (linear P-M, first yield)
at both ends of both sub-elements (so mid-span is included), fy the member's own IS 2062 value. A ratio > 1.0 flags
the member: `snl run` promotes it to fibre (<job>/nl_promote_fibre.json) and re-runs; the COMPLETE gate refuses while
a flagged member is still elastic.

    SNL_GRAVITY_ELASTIC=0|1  (or numerics.gravity_elastic) switches it; default ON for India, OFF for USA.
"""
from __future__ import annotations

import json
import os

import openseespy.opensees as ops

PROMOTE_FILE = "nl_promote_fibre.json"
CURRENT: dict = {}            # the elastic members of the model now in OpenSees: tag -> record
BASIS = ("gravity-only members (HR role gravity_col; beams pinned at both ends outside braced / EBF bays) modelled "
         "elastic (HR section properties, same releases, loads and mass); first-yield check |N|/Py + |Mmaj|/My,maj + "
         "|Mmin|/My,min <= 1.0 at the ends and mid-span; a member above 1.0 is promoted to fibre and the analysis re-run")


def enabled(pkg, prm=None) -> bool:
    env = os.environ.get("SNL_GRAVITY_ELASTIC")
    if env not in (None, ""):
        return env.strip().lower() not in ("0", "false", "off", "no")
    num = (prm or {}).get("numerics") or {}
    if num.get("gravity_elastic") is not None:
        return bool(num["gravity_elastic"])
    return getattr(pkg.basis, "jurisdiction", None) == "india"


def _analysis():
    return (os.environ.get("SNL_ANALYSIS") or "").strip().lower() or None


def promoted(pkg, analysis=None) -> set:
    """Members promoted to fibre for THIS analysis (pushover / nlrha, $SNL_ANALYSIS set by each CLI) plus any promoted
    for all analyses ('tags'). Separate lists: a gravity column that yields at 3 % drift in the pushover must be fibre
    there, but need not slow down an NLRHA whose demands stay far below it."""
    p = os.path.join(str(getattr(pkg, "root", "") or ""), PROMOTE_FILE)
    try:
        d = json.load(open(p, encoding="utf-8")) or {}
    except Exception:
        return set()
    a = analysis or _analysis()
    return {int(t) for t in (d.get("tags") or [])} | ({int(t) for t in (d.get(a) or [])} if a else set())


def promote(job, tags, why="", analysis=None) -> list:
    """Add member tags to <job>/nl_promote_fibre.json under `analysis` (None: all analyses). Returns that list."""
    p = os.path.join(str(job), PROMOTE_FILE)
    try:
        d = json.load(open(p, encoding="utf-8")) or {}
    except Exception:
        d = {}
    key = analysis or "tags"
    cur = sorted({int(t) for t in (d.get(key) or [])} | {int(t) for t in tags})
    d[key] = cur
    d["history"] = list(d.get("history") or []) + [dict(analysis=analysis or "all", added=sorted(int(t) for t in tags), why=why)]
    d["note"] = "members promoted from elastic to fibre after the NL-21 yield check (per analysis; 'tags' = all)"
    json.dump(d, open(p, "w", encoding="utf-8"), indent=1)
    return cur


def _major_release(e, slot):
    rel = e.get("release") or []
    flag = "-releasey" if slot == "Iy" else "-releasez"
    return int(rel[rel.index(flag) + 1]) if flag in rel else 0


def _plan_overlap(a1, a2, b1, b2, tol=1e-3):
    """Length of the plan-projection overlap of segments a and b when they are collinear in plan (else 0)."""
    ax, ay = a2[0] - a1[0], a2[1] - a1[1]
    La = (ax * ax + ay * ay) ** 0.5
    bx, by = b2[0] - b1[0], b2[1] - b1[1]
    Lb = (bx * bx + by * by) ** 0.5
    if La < 1e-9 or Lb < 1e-9:
        return 0.0
    ux, uy = ax / La, ay / La
    if abs(ux * by - uy * bx) > tol * Lb:                     # not parallel in plan
        return 0.0
    if abs(ux * (b1[1] - a1[1]) - uy * (b1[0] - a1[0])) > tol * max(La, Lb):   # parallel but offset
        return 0.0
    s1 = ux * (b1[0] - a1[0]) + uy * (b1[1] - a1[1]); s2 = ux * (b2[0] - a1[0]) + uy * (b2[1] - a1[1])
    lo, hi = max(0.0, min(s1, s2)), min(La, max(s1, s2))
    return max(0.0, hi - lo)


def _collinear(a1, a2, b1, b2, tol=1e-3) -> bool:
    ax, ay = a2[0] - a1[0], a2[1] - a1[1]
    La = (ax * ax + ay * ay) ** 0.5
    bx, by = b2[0] - b1[0], b2[1] - b1[1]
    Lb = (bx * bx + by * by) ** 0.5
    if La < 1e-9 or Lb < 1e-9:
        return False
    return abs(ax * by - ay * bx) <= tol * La * Lb and abs(ax * (b1[1] - a1[1]) - ay * (b1[0] - a1[0])) <= tol * La * max(La, Lb)


def classify(pkg, prm=None) -> dict:
    """{tag: reason} of the members built elastic (empty when the option is off).

    A beam stays in the SFRS (fibre) when it is moment-connected at either end, or when an end is a node of a brace /
    EBF link whose plan projection it overlaps (braced-bay, chevron and EBF beams). Beams of the neighbouring bays that
    only touch a brace node at their end are gravity beams."""
    if not enabled(pkg, prm):
        return {}
    from .nonlinear_model import member_kind, strong_I_slot
    m = pkg.model
    by_node = {}
    for e in m.elements:
        role = (pkg.schedule.get(e["tag"]) or {}).get("role")
        if e.get("etype") in ("Truss", "truss", "corotTruss", "ElasticTimoshenkoBeam") or role in ("brace", "link") \
                or member_kind(pkg, e) == "brace":
            for n in (e["n1"], e["n2"]):
                by_node.setdefault(n, []).append((m.nodes[e["n1"]], m.nodes[e["n2"]], role or e.get("etype")))
    keep = promoted(pkg)
    out = {}
    for e in m.elements:
        if "etype" in e or e["tag"] in keep:
            continue
        rec = pkg.schedule.get(e["tag"]) or {}
        sec, role = rec.get("section"), rec.get("role")
        kind = member_kind(pkg, e)
        if not sec or kind not in ("col", "beam"):
            continue
        if kind == "col" and role == "gravity_col":
            out[e["tag"]] = "HR role gravity_col"
        elif kind == "beam" and role != "link":
            if _major_release(e, strong_I_slot(pkg, e, kind)) != 3:
                continue                                  # moment-connected -> SFRS
            p1, p2 = m.nodes[e["n1"]], m.nodes[e["n2"]]
            L = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            braced = False
            for n in (e["n1"], e["n2"]):
                for q1, q2, rl in by_node.get(n, []):
                    horizontal = abs(q2[2] - q1[2]) < 1e-6        # an EBF link: collinear beam touching it
                    if _plan_overlap(p1, p2, q1, q2) > 1e-3 * L or (horizontal and _collinear(p1, p2, q1, q2)):
                        braced = True; break
                if braced:
                    break
            if not braced:
                out[e["tag"]] = "pinned both ends, not in a braced / EBF bay"
    return out


def split_releases(rel):
    """HR end-release args of one element -> (args of sub-element 1 at end i, args of sub-element 2 at end j)."""
    a, b = [], []
    rel = list(rel or [])
    for flag in ("-releasey", "-releasez"):
        if flag in rel:
            c = int(rel[rel.index(flag) + 1])
            if c in (1, 3):
                a += [flag, 1]
            if c in (2, 3):
                b += [flag, 2]
    return a, b


def capacities(pkg, e, kind, sec) -> dict:
    """Py (kip), My major / minor (kip-in) at first yield, from the section record (inch) and the member's fy."""
    from . import sections_db as SD
    from .nonlinear_model import strong_I_slot
    p = SD.props(sec)
    if getattr(pkg.basis, "jurisdiction", None) == "india":
        from . import india_model as IMD
        from snl.india_units import MPA_TO_KSI
        fy = IMD.fy_section(pkg, sec, kind, tag=e["tag"])["fye_MPa"] * MPA_TO_KSI
    else:
        fy = 50.0
    slot = strong_I_slot(pkg, e, kind)
    return dict(Py=fy * float(p["A"]), My_maj=fy * float(p["Sx"]), My_min=fy * float(p["Sy"]),
                i_maj=(5 if slot == "Iz" else 4), fy_ksi=fy)


def register(tag, subs, kind, sec, cap, reason):
    CURRENT[int(tag)] = dict(subs=list(subs), kind=kind, section=sec, reason=reason, **cap)


def reset():
    CURRENT.clear()


def ratio_of(f, c) -> float:
    if not f or len(f) < 12:
        return 0.0
    im, imn = c["i_maj"], (9 - c["i_maj"])            # 4 <-> 5
    r = 0.0
    for o in (0, 6):
        r = max(r, abs(f[o]) / c["Py"] + abs(f[o + im]) / c["My_maj"] + abs(f[o + imn]) / c["My_min"])
    return r


def sample() -> dict:
    """{tag: ratio} now (both sub-elements, both ends)."""
    out = {}
    for t, c in CURRENT.items():
        r = 0.0
        for s in c["subs"]:
            try:
                r = max(r, ratio_of(ops.eleResponse(s, "localForce"), c))
            except Exception:
                pass
        out[t] = r
    return out


def envelope(peaks: dict, smp: dict) -> dict:
    for t, r in smp.items():
        if r > peaks.get(t, 0.0):
            peaks[t] = r
    return peaks


def summary(peaks: dict, limit=1.0, meta=None) -> dict:
    """Package block: counts, the largest ratios, the members above `limit` (flagged -> must be promoted)."""
    meta = meta or {}
    top = sorted(peaks.items(), key=lambda kv: -kv[1])[:15]
    flagged = sorted(int(t) for t, r in peaks.items() if r > limit)
    return dict(n_elastic=len(peaks), max_ratio=(round(top[0][1], 4) if top else 0.0), limit=limit,
                flagged_elastic=flagged,
                top=[dict(tag=int(t), ratio=round(r, 4), section=(meta.get(int(t)) or {}).get("section"),
                          kind=(meta.get(int(t)) or {}).get("kind")) for t, r in top],
                basis=BASIS)


def meta_now() -> dict:
    return {t: dict(section=c["section"], kind=c["kind"], reason=c["reason"]) for t, c in CURRENT.items()}
