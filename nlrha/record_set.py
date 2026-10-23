"""record_set.py -- what the NLRHA record suite is, in words, for every India report (second wave, review E_NL item 15).

Every fact comes from the repository's own record data and selection code, never typed in:
  * the library: records/p695_farfield/index.json -- set name, source, and per pair the earthquake, year, magnitude,
    rupture distance, site-class letter, mechanism and (where flagged) pulse=True;
  * the suite of a run: the `ground_motions` block of each level's nlrha_package.json (gm_scaling.json) -- the
    selected pairs, their scale factors, the period range, the common multiplier and the suite-mean / target ratio;
  * the rule: nlrha/ground_motions.select_and_scale -- the n pairs whose RotD100 spectrum best fits the SHAPE of the
    target over [T_lower, T_upper] (smallest dispersion of ln(target / RotD100)); one factor per pair for both
    components = the pair's geometric-mean fit to the target x one common multiplier k >= 1 chosen so that the suite
    mean is >= 0.9 x target at every period in the range and >= the target on average;
  * the target: nlrha/india_hazard (owner ruling D6) -- IS 1893 elastic DBE = (Z/2)·I·Sa/g, MCE = Z·I·Sa/g, 5 %, no R;
  * IS 1893 (Part 1):2016 7.7.4, quoted from the India corpus transcription (india_hazard.CITE).

`disclosure(...)` returns the sentences; `block_html(...)` the marked HTML block the NLRHA reports carry; and
`refresh_reports(nlrha_dir)` writes that block (and the corrected record-count wording) into NLRHA reports and the
NLRHA viewer that were generated before this module existed -- report-only, no re-analysis, idempotent.
"""
from __future__ import annotations

import html
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(os.path.dirname(_HERE), "records", "p695_farfield")
MARK_START = "<!-- steltic:record-set-disclosure -->"
MARK_END = "<!-- /steltic:record-set-disclosure -->"
SHED_MARK_START = "<!-- steltic:shed-base-shear-note -->"
SHED_MARK_END = "<!-- /steltic:shed-base-shear-note -->"


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                                  # noqa: BLE001
        return None


def is_p695(name):
    return "p-695" in str(name or "").lower() or "p695" in str(name or "").lower() or "atc-63" in str(name or "").lower()


def library_facts(set_dir=None):
    """The shipped record library (records/p695_farfield/index.json) summarised; None when the index is missing."""
    idx = _load(os.path.join(set_dir or LIBRARY_DIR, "index.json"))
    if not idx:
        return None
    recs = idx.get("records") or []
    events = []
    for r in recs:
        ev = (r.get("earthquake"), r.get("year"), r.get("M"))
        if ev not in events:
            events.append(ev)

    def rng(key):
        v = [float(r[key]) for r in recs if isinstance(r.get(key), (int, float))]
        return (min(v), max(v)) if v else (None, None)
    return dict(name=idx.get("set"), source=idx.get("source"), n_pairs=len(recs), n_components=2 * len(recs),
                events=events, n_events=len(events), M=rng("M"), r_rup_km=rng("r_rup_km"),
                site_classes=sorted({str(r.get("site_class")) for r in recs if r.get("site_class")}),
                mechanisms=sorted({str(r.get("mechanism")) for r in recs if r.get("mechanism")}),
                n_pulse=sum(1 for r in recs if r.get("pulse")), p695=is_p695(idx.get("set")))


def _gm(level_pkg):
    """The ground_motions block of a level package (or a gm_scaling.json gm dict) -- tolerant of either."""
    if not level_pkg:
        return {}
    return level_pkg.get("ground_motions") or level_pkg.get("gm") or level_pkg


def suite_facts(levels):
    """levels: {"DBE": level nlrha_package.json (or its ground_motions block), "MCE": ...} -> per level the pairs, scale
    factors, period range, common multiplier and converged count, plus whether MCE uses the DBE pairs (and the ratio of
    the scale factors). Only what the packages hold."""
    out = dict(levels={}, same_pairs=None, mce_over_dbe_sf=None)
    ids = {}
    sfs = {}
    for lv, p in (levels or {}).items():
        g = _gm(p)
        sel = g.get("selected") or []
        rs = (p or {}).get("response_summary") or {}
        sf = [float(x["sf"]) for x in sel if x.get("sf") is not None]
        ids[lv] = [x.get("id") for x in sel]
        sfs[lv] = {x.get("id"): float(x["sf"]) for x in sel if x.get("sf") is not None}
        out["levels"][lv] = dict(
            pairs=len(sel) or rs.get("n_records"), converged=rs.get("n_converged"),
            sf_min=min(sf) if sf else None, sf_max=max(sf) if sf else None,
            T_lower=g.get("T_lower"), T_upper=g.get("T_upper"), common_multiplier=g.get("common_multiplier"),
            min_ratio=g.get("min_ratio_in_range"), sf_bounds=g.get("sf_bounds"), target_label=g.get("target_label"),
            sets=[(s.get("set") if isinstance(s, dict) else s) for s in (g.get("sets") or [])],
            events=sorted({(x.get("earthquake"), x.get("year")) for x in sel if x.get("earthquake")}, key=lambda e: (e[1] or 0, e[0])))
    if "DBE" in ids and "MCE" in ids and ids["DBE"] and ids["MCE"]:
        out["same_pairs"] = sorted(map(str, ids["DBE"])) == sorted(map(str, ids["MCE"]))
        if out["same_pairs"]:
            ratios = [sfs["MCE"][k] / sfs["DBE"][k] for k in sfs["DBE"] if k in sfs["MCE"] and sfs["DBE"][k]]
            if ratios and max(ratios) - min(ratios) <= 0.01 * max(ratios):
                out["mce_over_dbe_sf"] = round(sum(ratios) / len(ratios), 2)
    return out


def _range(a, b, fmt="%.1f"):
    if a is None:
        return "?"
    return (fmt % a) if b is None or abs(a - b) < 1e-9 else ("%s–%s" % (fmt % a, fmt % b))


def analyses_text(suite):
    """'11 record pairs (two horizontal components each), run at DBE and at MCE: 22 analyses, 22 converged'."""
    L = suite.get("levels") or {}
    if not L:
        return None
    pairs = [L[lv].get("pairs") or 0 for lv in L]
    conv = [L[lv].get("converged") for lv in L]
    lvs = [lv for lv in ("DBE", "MCE") if lv in L] + [lv for lv in L if lv not in ("DBE", "MCE")]
    n = sum(pairs)
    nc = sum(c for c in conv if c is not None) if all(c is not None for c in conv) else None
    if len(set(pairs)) == 1:
        head = "%d record pairs (two horizontal components each), run at %s" % (pairs[0], " and at ".join(lvs))
    else:
        head = "record pairs (two horizontal components each): %s" % ", ".join("%d at %s" % (L[lv].get("pairs") or 0, lv) for lv in lvs)
    return "%s: %d analyses%s" % (head, n, (", %d converged" % nc) if nc is not None else "")


def disclosure(levels, lib=None):
    """Plain-English sentences on the record set of one NLRHA run (levels as for suite_facts). Facts from the packages
    and the library index only."""
    lib = lib if lib is not None else library_facts()
    s = suite_facts(levels)
    L = s["levels"]
    first = next(iter(L.values()), {})
    names = [n for lv in L.values() for n in (lv.get("sets") or []) if n]
    set_name = names[0] if names else ((lib or {}).get("name"))
    p695 = is_p695(set_name) and lib and lib.get("p695") and not [n for n in names if not is_p695(n)]
    out = []
    if p695:
        evs = "; ".join("%s %s (M %s)" % (e, y, m) for e, y, m in sorted(lib["events"], key=lambda e: (e[1] or 0, e[0] or "")))
        used = sorted({e for lv in L.values() for e in (lv.get("events") or [])}, key=lambda e: (e[1] or 0, e[0] or ""))
        out.append("Record set: %s; the library's %d pairs come from %d earthquakes: %s. Source: %s.%s" % (
            lib["name"], lib["n_pairs"], lib["n_events"], evs, lib["source"],
            (" This run's pairs come from %s." % "; ".join("%s %s" % e for e in used)) if used else ""))
        out.append("The set holds no Indian or Himalayan records (magnitudes M %s, rupture distances %s km, site classes %s "
                   "in the US letters of the library index, %s), so near-field and long-duration effects of Indian earthquakes "
                   "are not represented. Indian or regional records can be supplied with --records-set." % (
                       _range(*lib["M"]), _range(*lib["r_rup_km"]), " / ".join(lib["site_classes"]),
                       ("no record flagged as a near-fault pulse" if not lib["n_pulse"] else "%d flagged as near-fault pulses" % lib["n_pulse"])))
    else:
        out.append("Record set: %s (supplied with --records-set). The tool does not check the tectonic origin of user "
                   "records; the engineer confirms that they suit the site." % (set_name or "not recorded"))
    lvs = [lv for lv in ("DBE", "MCE") if lv in L] + [lv for lv in L if lv not in ("DBE", "MCE")]
    if first:
        out.append("Selection and scaling (nlrha ground_motions.select_and_scale): at each level the %s pairs whose "
                   "maximum-direction (RotD100) spectrum best fits the shape of the target over T = %s s are used; each pair "
                   "has one scale factor for both components, its own geometric-mean fit to the target times one common "
                   "factor (%s), so that the suite mean is at least 0.9 × the target at every period in that range and not "
                   "below it on average. Target: IS 1893 (Part 1):2016 elastic spectrum, DBE = (Z/2)·I·Sa/g, MCE = Z·I·Sa/g, "
                   "5 %% damping, no R. IS 1893 7.7.4 asks for “an appropriate ground motion (preferably compatible with the "
                   "design acceleration spectrum in the desired range of natural periods)”; the 0.9 × target rule is this "
                   "tool's convention, not IS text." % (
                       first.get("pairs"), _range(first.get("T_lower"), first.get("T_upper"), "%.2f"),
                       "; ".join("%s %.3f" % (lv, L[lv]["common_multiplier"]) for lv in lvs
                                 if L[lv].get("common_multiplier") is not None) or "not recorded"))
    at = analyses_text(s)
    if at:
        extra = ""
        if s.get("same_pairs") and s.get("mce_over_dbe_sf"):
            extra = (" The MCE suite is the DBE suite with every scale factor × %.2f (the MCE target is twice the DBE "
                     "target, so the shape fit picks the same pairs)." % s["mce_over_dbe_sf"])
        elif s.get("same_pairs") is False:
            extra = " The DBE and MCE suites use different pairs."
        out.append("Analyses: %s.%s" % (at, extra))
    sfr = "; ".join("%s %s" % (lv, _range(L[lv].get("sf_min"), L[lv].get("sf_max"), "%.3f")) for lv in lvs if L[lv].get("sf_min") is not None)
    if sfr:
        b = [L[lv].get("sf_bounds") for lv in lvs if L[lv].get("sf_bounds")]
        out.append("Scale factors: %s; %s." % (sfr, ("bounds %s" % b[0]) if b else
                                                "no scale-factor bounds were set (the engineer may set nl_plan.gm_selection.sf_bounds)"))
    return out


def facts_for_index(levels, lib=None):
    """The record-set fields of the site index (scripts/build_site_index.py)."""
    lib = lib if lib is not None else library_facts()
    s = suite_facts(levels)
    names = [n for lv in s["levels"].values() for n in (lv.get("sets") or []) if n]
    p695 = bool(lib and lib.get("p695") and (not names or all(is_p695(n) for n in names)))
    return dict(record_set_full=(lib or {}).get("name") if p695 else (names[0] if names else None),
                record_set_source=(lib or {}).get("source") if p695 else None,
                record_set_note=("no Indian or Himalayan records (M %s, %d earthquakes); near-field and long-duration "
                                 "effects of Indian earthquakes are not represented" % (_range(*lib["M"]), lib["n_events"]))
                if p695 else "user-supplied records; tectonic origin not checked by the tool",
                scaling=("one factor per pair: shape fit to the IS 1893 elastic spectrum (DBE (Z/2)·I·Sa/g, MCE Z·I·Sa/g, "
                         "no R), suite mean >= 0.9 x target over the period range"),
                analyses_text=analyses_text(s), same_pairs_dbe_mce=s.get("same_pairs"), mce_over_dbe_sf=s.get("mce_over_dbe_sf"))


def block_html(levels, lib=None, heading=True):
    """The marked disclosure block for an NLRHA report (index or level page)."""
    lines = disclosure(levels, lib)
    body = "".join("<li>%s</li>" % html.escape(x) for x in lines)
    return ("%s<div class='note' id='record-set'>%s<ul>%s</ul></div>%s" % (
        MARK_START, "<b>Ground-motion record set</b>" if heading else "", body, MARK_END))


def _levels_of(nlrha_dir):
    levels = {}
    for lv in ("DBE", "MCE"):
        p = _load(os.path.join(nlrha_dir, lv, "nlrha_package.json"))
        if p:
            g = _load(os.path.join(nlrha_dir, lv, "gm_scaling.json"))
            if g and not (p.get("ground_motions") or {}).get("selected"):
                p = dict(p, ground_motions=g.get("gm") or {})
            levels[lv] = p
    return levels


def _insert(h, block):
    """Replace an earlier block, else insert after the IS statement div / note, else after <h1>."""
    if MARK_START in h and MARK_END in h:
        return h[:h.index(MARK_START)] + block + h[h.index(MARK_END) + len(MARK_END):]
    i = h.find("<h2>1 Ground motions</h2>")                  # a level page: before section 1
    if i >= 0:
        return h[:i] + block + "\n" + h[i:]
    i = h.find("</table>")                                   # the index page: after the levels table
    if i >= 0:
        i += len("</table>")
        return h[:i] + "\n" + block + h[i:]
    i = h.find("</h1>")
    return (h[:i + 5] + block + h[i + 5:]) if i >= 0 else (h + block)


OLD_BASIS = ("selection/scaling rules per EOR; IS 1893 7.7.4 requires motions 'preferably compatible with the design "
             "acceleration spectrum in the desired range of natural periods'. This tool fits the suite mean RotD100 to >= 0.9 x "
             "the IS elastic target over [T_lower, T_upper] (EOR-adoptable convention, not IS law).")


BASIS_SENTENCE = ("Record selection and scaling (IS 1893 (Part 1):2016 7.7.4; one scale factor per record pair; suite mean "
                  "at least 0.9 × the IS elastic target over [T_lower, T_upper], this tool's convention, not IS text): see "
                  "'Ground-motion record set'.")


def refresh_reports(nlrha_dir, shed=None):
    """Write the record-set disclosure into the NLRHA reports of one run (index + DBE / MCE pages) and correct the
    record-count wording of the reports and the NLRHA viewer: 'records (converged)' -> 'record pairs (converged)',
    'Scale-factor bounds: None' -> 'none set', the 7.7.4 sentence; with `shed` (a dict from snl.compare.shed_basis)
    the index also states the suite-mean base shear over W. Report-only and idempotent. Returns the files changed."""
    levels = _levels_of(nlrha_dir)
    if not levels:
        return []
    block = block_html(levels)
    changed = []
    for rel in ["nlrha_report.html"] + [os.path.join(lv, "nlrha_report.html") for lv in levels]:
        p = os.path.join(nlrha_dir, rel)
        if not os.path.exists(p):
            continue
        h0 = h = open(p, encoding="utf-8").read()
        h = h.replace(html.escape(OLD_BASIS), html.escape(BASIS_SENTENCE))
        h = h.replace("<p>Scale-factor bounds: None</p>", "<p>Scale-factor bounds: none set (the engineer may set "
                      "nl_plan.gm_selection.sf_bounds).</p>")
        h = h.replace("<th>records (converged)</th>", "<th>record pairs (converged)</th>")
        h = _insert(h, block)
        if rel == "nlrha_report.html" and shed:
            h = _shed_note_index(h, nlrha_dir, levels, shed)
        if h != h0:
            open(p, "w", encoding="utf-8").write(h)
            changed.append(p)
    v = os.path.join(nlrha_dir, "nlrha_viewer_3d.html")
    if os.path.exists(v):
        h0 = h = open(v, encoding="utf-8").read()
        at = analyses_text(suite_facts(levels))
        if at:
            # the viewer embeds its meta as JSON: the middle dot is "\u00b7" there
            h = re.sub(r"(\\u00b7|·) ((?:DBE|MCE)(?:, (?:DBE|MCE))*) (\\u00b7|·) \d+ records (\\u00b7|·) information only",
                       lambda m: "%s %s %s %s %s information only" % (m.group(1), m.group(2), m.group(3), at, m.group(4)), h)
        h = h.replace("['Records · converged', `${S.n_records} · ${S.n_converged}`]",
                      "['Record pairs · converged', `${S.n_records} · ${S.n_converged}`]")
        if h != h0:
            open(v, "w", encoding="utf-8").write(h)
            changed.append(v)
    return changed


def shed_note_text(shed):
    return ("%s: VB is the R-reduced IS 1893 design base shear, which is small for a light shed, so V/VB is large and is "
            "not a measure of the structure's reserve. The suite-mean peak base shear over the seismic weight W is the "
            "comparable figure." % (shed.get("basis") or "Shed"))


def _shed_note_index(h, nlrha_dir, levels, shed):
    W = shed.get("W_kN")
    rows = []
    for lv, p in levels.items():
        bs = ((p or {}).get("response_summary") or {}).get("base_shear") or {}
        if W and bs.get("mean_X_kN") is not None:
            rows.append("%s: suite-mean peak V / W = %.3f (X) / %.3f (Y)" % (lv, bs["mean_X_kN"] / W, (bs.get("mean_Y_kN") or 0) / W))
    block = "%s<p class='note'><b>%s</b>%s</p>%s" % (
        SHED_MARK_START, html.escape(shed_note_text(shed)), (" " + html.escape("; ".join(rows)) + ".") if rows else "",
        SHED_MARK_END)
    if SHED_MARK_START in h and SHED_MARK_END in h:
        return h[:h.index(SHED_MARK_START)] + block + h[h.index(SHED_MARK_END) + len(SHED_MARK_END):]
    m = re.search(r"</table>", h)
    return (h[:m.end()] + block + h[m.end():]) if m else (h + block)
