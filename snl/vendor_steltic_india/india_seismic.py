"""IS 1893 (Part 1) : 2016 drift and irregularity helpers for steltic_india.

Clause text was checked against /workspace/INDIA_STEEL/pdfs/IS_1893_Part_1_2016_Amd2_Reff2021.pdf
(and the India RAG corpus stem IS_1893_Part_1_2016). Do not invent numerical limits —
missing items are explicit TODO with found:false.
"""
from __future__ import annotations

import re as _re

# D1: one constant for the edition (a future switch is a one-line change).
IS1893_EDITION = "IS 1893 (Part 1):2016 + Amd 1 (2017) + Amd 2 (2020)"
IS1893_STEM = "IS_1893_Part_1_2016"


# ---------------------------------------------------------------------------
# WP1.4 -- IS 1893 Table 8 importance factor (Amd 2: 'educational buildings' for 'schools')
# ---------------------------------------------------------------------------
# H20: keyword classes, matched on word boundaries (no 'mall' in 'small', no 'shop' in 'workshop').  Each class
# maps to an explicit occupancy flag; an explicit flag (True/False) overrides the keywords of its class.
_T8_I_CLASSES = {
    "hospital": ("hospital", "hospitals"),
    "educational": ("school", "schools", "educational", "education", "college", "colleges", "university",
                    "universities", "institute"),
    "food_storage": ("food storage", "food warehouse", "food godown", "grain storage", "granary"),
    "assembly": ("cinema", "cinema hall", "shopping mall", "mall", "assembly hall", "assembly halls",
                 "community hall", "subway", "subway station"),
    "lifeline": ("critical governance", "governance", "signature", "monument", "lifeline", "emergency",
                 "telephone exchange", "television", "radio station", "bus station", "metro", "railway station",
                 "airport", "fuel station", "power station", "fire station"),
}
_T8_ROW_I = tuple(k for ks in _T8_I_CLASSES.values() for k in ks)
_T8_ROW_II = ("residential", "residence", "residences", "apartment", "apartments", "housing", "hostel", "hostels",
              "dormitory", "dormitories", "hotel", "motel", "guest house", "office", "offices", "commercial",
              "retail", "shop", "shops", "business", "mercantile")
_T8_RESIDENTIAL = ("residential", "residence", "residences", "apartment", "apartments", "housing", "hostel",
                   "hostels", "dormitory", "dormitories", "hotel", "motel", "guest house")
# institution names that a residential use takes precedence over (a university dormitory is residential)
_T8_INSTITUTION_NAMES = ("educational", "hospital")
_T8_STORAGE = ("warehouse", "warehouses", "storage", "godown", "godowns", "store", "stores", "cold store")
_T8_FLAGS = ("food_storage", "educational", "hospital", "assembly", "lifeline", "important")
D8_AREA_ROW = "owner ruling D8 (area proxy for Table 8 (ii))"


# RR-BUG-1: a keyword preceded (within its phrase) by a negation -- 'non-food storage', 'no food storage',
# 'not a hospital', 'without any food storage', 'excluding food storage' -- names what the building is NOT and
# must not select the class.  The negation attaches to the keyword: only filler words may stand between them
# ('no food storage' negates 'food storage' but not the bare 'storage' keyword, since 'food' is not filler).
_NEGATIONS = ("non", "no", "not", "without", "excluding", "except", "nor", "never")
_NEG_FILLER = ("a", "an", "the", "any", "for", "of", "as", "used", "being", "intended", "meant", "use", "type",
               "kind", "cum")


def _negated(use: str, start: int) -> bool:
    """True when the keyword starting at ``use[start]`` is preceded by a negation in its own phrase (RR-BUG-1)."""
    before = _re.split(r"[.;:|]", use[:start])[-1]            # phrase boundary
    words = _re.findall(r"[a-z0-9]+", before)
    for w in reversed(words):
        if w in _NEGATIONS:
            return True
        if w not in _NEG_FILLER:
            return False
    return False


def _kw(use: str, words, negated: list = None) -> list:
    """Keywords of ``words`` found in ``use`` on word boundaries (H20), ignoring negated occurrences (RR-BUG-1:
    'non-food storage', 'no food storage', 'not a hospital').  Negated keywords are appended to ``negated``."""
    out = []
    for w in words:
        pos = [m.start() for m in _re.finditer(r"(?<![a-z0-9])" + _re.escape(w) + r"(?![a-z0-9])", use)]
        if not pos:
            continue
        if any(not _negated(use, p) for p in pos):
            out.append(w)
        elif negated is not None and w not in negated:
            negated.append(w)
    return out


def importance_factor(occupancy) -> dict:
    """IS 1893 Table 8 (with Amd 2) importance factor from an occupancy record.

    occupancy = {use | uses, persons | area_m2 + occupant_load_m2_per_person, and the explicit class flags
                 educational, hospital, food_storage, assembly, lifeline, important}  (a list of such records =
    mixed occupancy, Note 4 takes the larger I).  Returns {found, I, row, cite, note, matched_keyword, basis,
    warnings}.
    H20: keywords match on word boundaries; residential uses (hostel, dormitory, residence ...) take precedence over
    institution names (university, school, hospital) unless the matching flag (educational / hospital) is True; an
    explicit flag overrides the keywords of its class; a storage use without ``food_storage`` declared is 1.0 with a
    warning asking to declare it (Table 8 (i) 'food storage buildings (such as warehouses)' -> 1.5).
    Clinic: owner ruling D8 -> 1.2 (a ruling, not a Table 8 row).  Commercial/residential without a person count:
    owner ruling D8 -- > 2,000 m2 -> 1.2, labelled as the ruling (area proxy for the Table 8 (ii) person count, R2).
    """
    cite = IS1893_EDITION + " Table 8"
    if isinstance(occupancy, (list, tuple)):
        rs = [importance_factor(o) for o in occupancy]
        if not rs or not all(r.get("found") for r in rs):
            bad = [r.get("note") for r in rs if not r.get("found")] or ["empty list"]
            return {"found": False, "I": None, "cite": cite, "note": "; ".join(map(str, bad)),
                    "warnings": [w for r in rs for w in (r.get("warnings") or [])]}
        best = max(rs, key=lambda r: r["I"])
        return dict(best, note="mixed occupancy, Table 8 Note 4: larger I governs; " + str(best.get("note") or ""),
                    warnings=[w for r in rs for w in (r.get("warnings") or [])])
    if not isinstance(occupancy, dict) or not occupancy:
        return {"found": False, "I": None, "cite": cite,
                "note": "occupancy{use, persons | area_m2 + occupant_load_m2_per_person, food_storage, "
                        "educational, hospital, assembly, lifeline} missing from the brief/cfg (D8)"}
    use = " ; ".join(str(u) for u in ([occupancy.get("use")] + list(occupancy.get("uses") or [])) if u).lower()
    use_txt = use
    use = _re.sub(r"\s*[,;]+\s*", " ; ", use)             # RR-BUG-1: keep phrase boundaries for negation scope
    use = _re.sub(r"\s+", " ", _re.sub(r"[_/()\-]+", " ", use)).strip(" ;")
    warnings = []
    negated = []
    flags = {k: occupancy.get(k) for k in _T8_FLAGS}
    true_flags = [k for k, v in flags.items() if v is True]
    residential = _kw(use, _T8_RESIDENTIAL, negated)
    hits = {}
    for cls, words in _T8_I_CLASSES.items():
        if flags.get(cls) is False:          # explicit 'not this class' overrides its keywords
            continue
        neg0 = len(negated)
        m = _kw(use, words, negated)
        if m:
            hits[cls] = m
        elif len(negated) > neg0 and flags.get(cls) is None:
            warnings.append("use %r: negated keyword %r ignored (not a Table 8 (i) %s building); declare "
                            "occupancy['%s'] = False to confirm (RR-BUG-1)" % (use_txt, negated[neg0], cls, cls))
    if residential:
        for cls in _T8_INSTITUTION_NAMES:
            if cls in hits and flags.get(cls) is not True:
                warnings.append("use %r: residential keyword %r takes precedence over the institution name %r "
                                "(Table 8 (ii)/(iii)); set occupancy['%s'] = True if the building itself is a "
                                "Table 8 (i) %s building" % (use_txt, residential[0], hits[cls][0], cls, cls))
                hits.pop(cls)
    if true_flags or hits:
        if true_flags:
            matched, basis = "flag:" + ",".join(true_flags), "flag"
        else:
            cls0 = sorted(hits)[0]
            matched, basis = hits[cls0][0], "keyword"
            warnings.append("Table 8 (i) (I = 1.5) from the keyword %r in use %r only -- declare the class flag "
                            "(occupancy['%s'] = True) to confirm" % (matched, use_txt, cls0))
        return {"found": True, "I": 1.5, "row": "Table 8 (i)", "cite": cite, "matched_keyword": matched,
                "basis": basis, "warnings": warnings,
                "note": "important service / community / educational / hospital / food storage (%s)"
                        % ", ".join(true_flags or [k for v in hits.values() for k in v][:2])}
    storage = _kw(use, _T8_STORAGE, negated)
    if storage and "food_storage" not in occupancy:
        warnings.append("storage use %r: declare occupancy['food_storage'] (True/False) -- IS 1893 Table 8 (i) "
                        "'food storage buildings (such as warehouses)' take I = 1.5; I = 1.0 assumed for "
                        "general storage" % use)
    clinic = _kw(use, ("clinic", "clinics"), negated)
    if clinic:
        return {"found": True, "I": 1.2, "row": "owner ruling D8 (clinic; not a Table 8 row)", "cite": cite,
                "matched_keyword": clinic[0], "basis": "ruling", "warnings": warnings,
                "note": "clinic: owner ruling D8 fixes I = 1.2 (not a Table 8 (i) hospital building)"}
    persons = occupancy.get("persons")
    if persons is None and occupancy.get("area_m2") and occupancy.get("occupant_load_m2_per_person"):
        persons = float(occupancy["area_m2"]) / float(occupancy["occupant_load_m2_per_person"])
    res_com = _kw(use, _T8_ROW_II, negated)
    if res_com:
        if persons is not None:
            if float(persons) > 200:
                return {"found": True, "I": 1.2, "row": "Table 8 (ii)", "cite": cite, "persons": float(persons),
                        "matched_keyword": res_com[0], "basis": "persons", "warnings": warnings,
                        "note": "residential/commercial, occupancy %.0f > 200 persons (per independent unit, Note 3)"
                                % float(persons)}
            return {"found": True, "I": 1.0, "row": "Table 8 (iii)", "cite": cite, "persons": float(persons),
                    "matched_keyword": res_com[0], "basis": "persons", "warnings": warnings,
                    "note": "residential/commercial with %.0f <= 200 persons" % float(persons)}
        if occupancy.get("area_m2") is not None:
            A = float(occupancy["area_m2"])
            I = 1.2 if A > 2000.0 else 1.0
            row = D8_AREA_ROW if I > 1.0 else "owner ruling D8 (area proxy; Table 8 (iii))"
            return {"found": True, "I": I, "row": row, "cite": cite + "; " + row,
                    "matched_keyword": res_com[0], "basis": "ruling", "warnings": warnings,
                    "note": "persons not stated: owner ruling D8 (area proxy for the Table 8 (ii) '> 200 persons'; "
                            "> 2,000 m2 -> 1.2); area %.0f m2 -> I = %.1f" % (A, I)}
        return {"found": False, "I": None, "cite": cite, "warnings": warnings,
                "note": "residential/commercial occupancy needs persons or area_m2 (+ occupant load) (D8)"}
    if use:
        return {"found": True, "I": 1.0, "row": "Table 8 (iii)", "cite": cite, "matched_keyword": None,
                "basis": "all_other", "warnings": warnings,
                "note": "all other buildings (use %r)" % use}
    return {"found": False, "I": None, "cite": cite, "note": "occupancy.use missing"}

# ---------------------------------------------------------------------------
# WP1.3 -- IS 1893 6.4.2 design acceleration coefficient (read from the PDF p.9)
# ---------------------------------------------------------------------------
_SOIL = {"I": ("rock or hard", 0.40, 1.00, 0.25), "II": ("medium stiff", 0.55, 1.36, 0.34),
         "III": ("soft", 0.67, 1.67, 0.42)}


def soil_type(soil) -> str:
    s = str(soil or "").strip().lower()
    if s.startswith("type"):
        s = s[4:].strip()
    if s in ("i", "1", "rock", "hard", "rock or hard", "rock/hard", "a") or "rock" in s or "hard" in s:
        return "I"
    if s in ("iii", "3", "soft", "c") or "soft" in s:
        return "III"
    if s in ("ii", "2", "medium", "stiff", "b") or "medium" in s or "stiff" in s or "(type ii)" in s:
        return "II"
    raise ValueError("soil type %r not recognised (IS 1893 6.4.2.1: I rock/hard, II medium/stiff, III soft)" % soil)


def sa_over_g(T, soil, method="RSA") -> float:
    """IS 1893 (Part 1):2016 6.4.2 Sa/g, 5 % damping.

    method 'ESM' (6.4.2(a), Fig. 2(a)): 2.5 plateau from T = 0.
    method 'RSA' (6.4.2(b), Fig. 2(b)): 1 + 15T for T < 0.10 s, then the plateau.
    Corners 0.40 / 0.55 / 0.67 s; 1.00/T, 1.36/T, 1.67/T up to 4 s; tails 0.25 / 0.34 / 0.42.
    """
    T = float(T)
    if T < 0:
        raise ValueError("period must be >= 0")
    _, Tc, c, tail = _SOIL[soil_type(soil)]
    m = str(method or "RSA").upper()
    if m in ("RSA", "RS", "MRSA", "DYNAMIC") and T < 0.10:
        return 1.0 + 15.0 * T
    if T <= Tc:
        return 2.5
    if T <= 4.0:
        return c / T
    return tail


def design_Ah(Z, I, R, T, soil, method="RSA") -> float:
    """Ah = (Z/2)(I/R)(Sa/g) -- R applied ONCE (6.4.2)."""
    return (float(Z) / 2.0) * (float(I) / float(R)) * sa_over_g(T, soil, method)


def cqc_rho(wi, wj, zeta=0.05) -> float:
    """IS 1893 7.7.5.3(a) cross-modal coefficient, beta = wj / wi, zeta = 0.05."""
    b = float(wj) / float(wi)
    return 8.0 * zeta ** 2 * (1.0 + b) * b ** 1.5 / ((1.0 - b ** 2) ** 2 + 4.0 * zeta ** 2 * b * (1.0 + b) ** 2)


TABLE7_RHO = {"II": 0.007, "III": 0.011, "IV": 0.016, "V": 0.024}     # IS 1893 Table 7 (percent / 100)


def esm_summary(W_by_floor_N, heights_mm, Z, I, R, soil, zone, Ta) -> dict:
    """IS 1893 7.6 equivalent static method from the (engine) seismic weights.

    Ta: seconds, or {'X': Tx, 'Y': Ty}.  R: number, or {'X': R_x, 'Y': R_y} (H06 per-direction R).
    VB = max(Ah W, rho W) (7.6.1, 7.2.2 / Table 7), Qi = VB Wi hi^2 / sum(Wj hj^2) (7.6.3(a)).
    Returns a seismic_summary fragment (kN) and the unfactored story forces in N."""
    W = [float(w) for w in W_by_floor_N]
    hs = []
    z = 0.0
    for h in heights_mm:
        z += float(h)
        hs.append(z / 1000.0)
    Tad = Ta if isinstance(Ta, dict) else {"X": float(Ta), "Y": float(Ta)}
    Rd = {k: float(v) for k, v in R.items()} if isinstance(R, dict) else {"X": float(R), "Y": float(R)}
    R = min(Rd.values())
    rho = TABLE7_RHO.get(str(zone).upper().replace("ZONE", "").strip())
    Wt = sum(W)
    out = {"W_kN": round(Wt / 1000.0, 3), "W_by_floor_kN": [round(w / 1000.0, 3) for w in W],
           "hi_m": [round(h, 4) for h in hs], "Z": Z, "I": I, "R": R, "soil": soil, "zone": zone,
           "cite": IS1893_EDITION + " 6.4.2, 7.2.2 (Table 7), 7.6.1, 7.6.3"}
    sf = {}
    den = sum(w * h * h for w, h in zip(W, hs))
    for d in ("X", "Y"):
        sa = sa_over_g(Tad[d], soil, "ESM")
        Ah = max((float(Z) / 2.0) * (float(I) / Rd[d]) * sa, rho or 0.0)
        out["R_%s" % d.lower()] = Rd[d]
        VB = Ah * Wt
        Q = [VB * w * h * h / den for w, h in zip(W, hs)]
        out["Ta_%s_s" % d.lower()] = round(Tad[d], 4)
        out["Sa_g_%s" % d.lower()] = round(sa, 4)
        out["Ah_%s" % d.lower()] = round(Ah, 6)
        out["VB_%s_kN" % d.lower()] = round(VB / 1000.0, 3)
        out["Qi_%s_kN" % d.lower()] = [round(q / 1000.0, 3) for q in Q]
        sf["EQ_" + d] = {str(k + 1): ([q, 0.0, 0.0] if d == "X" else [0.0, q, 0.0]) for k, q in enumerate(Q)}
    gov = "X" if out["VB_x_kN"] >= out["VB_y_kN"] else "Y"
    out.update(Ta_s=out["Ta_%s_s" % gov.lower()], Sa_g=out["Sa_g_%s" % gov.lower()], Ah=out["Ah_%s" % gov.lower()],
               VB_kN=out["VB_%s_kN" % gov.lower()], rho_min=rho)
    return {"seismic_summary": out, "story_forces": sf, "story_forces_units": "N"}


# NOTE (WP1.3 item 8, documented for the WP6 example rewrite): the example build scripts
# IN_Ex7..Ex15 carry an ESM helper `_sa_g` that returns 1 + 15T for T <= 0.1 s -- that is the RSA
# branch.  ESM uses 2.5 from T = 0 (6.4.2(a)); Ex13 VB_x 151.7 kN must be 161.2 kN.  Every job
# must call india_seismic.sa_over_g(T, soil, "ESM") instead of a local helper.

# --- authoritative clause anchors (found:true) ---------------------------------
CLAUSES = {
    "storey_drift_limit": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "7.11.1.1",
        "text": (
            "Storey drift in any storey shall not exceed 0.004 times the storey height, "
            "under the action of design base of shear VB with no load factors mentioned in 6.3, "
            "that is, with partial safety factor for all loads taken as 1.0."
        ),
        "limit_ratio": 0.004,
    },
    "drift_no_dynamic_scale": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "7.11.1.2",
        "text": (
            "Displacement estimates obtained from dynamic analysis need not be scaled, "
            "as stated in 7.7.3.2 (Amd 2)."
        ),
    },
    "plan_irregularities_table": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 5",
        "cite": "7.1 / Table 5",
        "types": [
            "Torsional Irregularity",
            "Re-entrant Corners",
            "Floor Slabs having Excessive Cut-Outs or Openings",
            "Out-of-Plane Offsets in Vertical Elements",
            "Non-Parallel Lateral Force System",
        ],
    },
    "vertical_irregularities_table": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 6",
        "cite": "7.1 / Table 6",
        "types": [
            "Stiffness Irregularity (Soft Storey)",
            "Mass Irregularity",
            "Vertical Geometric Irregularity",
            "In-Plane Discontinuity in Vertical Elements Resisting Lateral Force",
            "Strength Irregularity (Weak Storey)",
            "Floating or Stub Columns",
            "Irregular Modes of Oscillation in Two Principal Plan Directions",
        ],
    },
    "torsional_irregularity_trigger": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 5 (i)",
        "text": (
            "A building is said to be torsionally irregular, when the maximum horizontal "
            "displacement of any floor in the direction of the lateral force at one end of the "
            "floor is more than 1.5 times its minimum horizontal displacement at the far end of "
            "the same floor in that direction."
        ),
        "ratio_trigger": 1.5,
        # follow-on 1.5–2.0 and >2.0 configuration/analysis rules: see Table 5 concluded
    },
    "reentrant_corner": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 5 (ii)",
        "text": (
            "A building is said to have a re-entrant corner in any plan direction, when its "
            "structural configuration in plan has a projection of size greater than 15 percent "
            "of its overall plan dimension in that direction."
        ),
        "projection_ratio": 0.15,
    },
    "soft_storey": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 6 (i) + Amendment 2",
        "text": (
            "A soft storey is a storey whose lateral stiffness is less than that of the storey above. "
            "In a building with stiffness irregularity: (1) Dynamic Analysis shall be employed to "
            "capture the actual distribution of lateral stiffness along the height; and (2) the "
            "inter-storey drift shall be limited to 0.2 percent in that storey and all storeys below "
            "with stiffness irregularity. (URM-infill SPD >20% → model infills; see also 7.9.)"
        ),
        "stiffness_ratio_trigger": 1.0,  # Ki < Ki_above  ⇒ soft (Amd2 wording; no 0.7 factor)
        "soft_storey_drift_limit": 0.002,
        "requires_dynamic_analysis": True,
    },
    "mass_irregularity": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "Table 6 (ii)",
        "text": (
            "Mass irregularity shall be considered to exist, when the seismic weight (as per 7.7) "
            "of any floor is more than 150 percent of that of the floors below."
        ),
        "ratio_trigger": 1.5,
    },
    "design_eccentricity": {
        "found": True,
        "stem": "IS_1893_Part_1_2016",
        "clause": "7.8.2",
        "text": (
            "edi = 1.5*esi + 0.05*bi  OR  esi - 0.05*bi, whichever gives the more severe effect "
            "on lateral force resisting elements."
        ),
    },
}

# Explicit gaps — do not fabricate ASCE analogues
TODO = [
    {
        "id": "asce_Cd_Ie_drift_amplification",
        "found": False,
        "note": (
            "IS 1893 7.11.1.1 checks storey drift under VB with γ=1.0; it does NOT use ASCE 7 "
            "δ = Cd*δe/Ie. India path must NOT apply Cd/Ie amplification to the drift gate."
        ),
    },
    {
        "id": "asce_table_12_12_1_risk_category_limits",
        "found": False,
        "note": "No IS 1893 equivalent to ASCE Table 12.12-1 risk-category drift limits; use 0.004 h.",
    },
    {
        "id": "asce_12_12_1_1_rho_drift_reduction",
        "found": False,
        "note": "No IS 1893 ρ divisor on drift limit for moment-frame-only systems.",
    },
    {
        "id": "tir_ax_amplification_asce_12_8_4_3",
        "found": False,
        "note": (
            "ASCE Ax = (δmax/(1.2 δavg))^2 does not appear in IS 1893. Use 7.8.2 design "
            "eccentricity (1.5 esi ± 0.05 bi) instead; do not invent an Ax factor."
        ),
    },
    {
        "id": "vertical_geometric_125pct_automation",
        "found": True,
        "clause": "Table 6 (iii)",
        "note": (
            "Limit (horizontal dimension of LFRS in a storey > 125% of storey below) is known, "
            "but automated detection from cfg footprint is only a geometric proxy — agent must confirm."
        ),
    },
]



def storey_stiffness_soft_flags(storey_stiffness: list[float] | None) -> dict:
    """Classify soft storeys from lateral stiffness samples (force/displacement per storey).

    IS 1893 Table 6 (i) Amd2: soft when Ki < K(i+1) (storey above). Returns per-storey flags
    and the governing drift limit (0.002 on soft storeys and all below).

    storey_stiffness: list length = n_storeys, index 0 = lowest storey. Units arbitrary but
    consistent (e.g. kip/in from Vb_storey / drift_storey). If None/empty → found data missing.
    """
    out = {
        "found": True,
        "standard": "IS_1893_Part_1_2016 Table 6 (i) Amd2",
        "asce_Ax": {"found": False, "note": "No Ax amplification in IS 1893; use cl.7.8.2 eccentricity."},
        "soft_storeys": [],
        "drift_limit_by_storey": [],
        "requires_dynamic_analysis": False,
        "note": None,
    }
    if not storey_stiffness:
        out["note"] = (
            "No storey_stiffness[] provided — height-jump proxy in classify_vertical_irregularities "
            "is advisory only; agent must supply Ki from analysis (e.g. storey shear / storey drift)."
        )
        return out
    K = [float(x) for x in storey_stiffness]
    n = len(K)
    soft = [False] * n
    for i in range(n - 1):
        # i is below i+1; soft if Ki < K(above)
        if K[i] < K[i + 1]:
            soft[i] = True
    # Once a soft storey exists, Amd2 limits drift to 0.002 in that storey AND all below
    lim = []
    below_soft = False
    # walk from top: mark cascade downward
    cascade = [False] * n
    seen = False
    for i in range(n - 1, -1, -1):
        if soft[i]:
            seen = True
        if seen and (soft[i] or any(soft[j] for j in range(i, n))):
            # all storeys at or below any soft storey
            pass
    for i in range(n):
        if any(soft[j] for j in range(i, n)):  # this storey or any above is soft → 0.002 if at/below soft
            # Amd2: "in that storey and all storeys below"
            pass
    # Correct cascade: for each soft storey s, storeys 0..s get 0.002
    limit = [CLAUSES["storey_drift_limit"]["limit_ratio"]] * n
    for s, is_soft in enumerate(soft):
        if is_soft:
            for i in range(0, s + 1):
                limit[i] = CLAUSES["soft_storey"]["soft_storey_drift_limit"]
    out["soft_storeys"] = soft
    out["drift_limit_by_storey"] = limit
    out["requires_dynamic_analysis"] = any(soft)
    out["soft_storey_indices"] = [i for i, f in enumerate(soft) if f]
    return out


def drift_allowable_for_storey(cfg, storey_index: int = 0) -> float:
    """Allowable drift ratio for a storey, applying soft-storey 0.002 when flagged."""
    base, _ = drift_allowable(cfg)
    flags = cfg.get("_soft_storey_flags") or {}
    lims = flags.get("drift_limit_by_storey")
    if lims and 0 <= storey_index < len(lims):
        return float(lims[storey_index])
    # cfg may list soft storey indices directly
    soft_idx = cfg.get("soft_storey_indices") or []
    if soft_idx:
        # storeys at or below any soft storey → 0.002
        max_soft = max(int(i) for i in soft_idx)
        if storey_index <= max_soft:
            return float(CLAUSES["soft_storey"]["soft_storey_drift_limit"])
    return base


def drift_allowable(cfg) -> tuple[float, bool]:
    """Return (allowable storey drift ratio, rho_applied).

    Default 0.004 per IS 1893 Part 1:2016 cl.7.11.1.1. cfg['drift_limit'] may override
    when the agent has RAG-justified a stricter project/special limit (e.g. 0.002 for
    URM-infill storeys per Table 6 notes). rho_applied is always False (no ASCE ρ rule).
    """
    dl = cfg.get("drift_limit")
    if dl is None or dl == "":
        dl = CLAUSES["storey_drift_limit"]["limit_ratio"]
    # WP1.9: never above 7.11.1.1 (0.004); a larger cfg value is a preflight ERROR, and the gate
    # still uses 0.004 (the CFS cap ported to HR, spec 1.10).
    return min(float(dl), CLAUSES["storey_drift_limit"]["limit_ratio"]), False


def design_story_drifts(elastic_drifts, cfg) -> list[float]:
    """Map analysis interstorey drifts to the IS 1893 design-drift check values.

    Under 7.11.1.1 the check uses drifts from design base shear VB with load factors = 1.0.
    When the analysis already applied design seismic forces (Ah with R), elastic storey
    drifts are the design drifts — do NOT multiply by Cd/Ie.

    If cfg['load_plan']['seismic_summary'] supplies an explicit drift_amplification factor
    retrieved from RAG, that factor is applied; otherwise factor = 1.0.
    """
    factor = 1.0
    lp = cfg.get("load_plan") or {}
    summ = lp.get("seismic_summary") or {}
    if summ.get("drift_amplification") is not None:
        factor = float(summ["drift_amplification"])
    # Honor explicit cfg override only when agent set it from RAG
    if cfg.get("is1893_drift_factor") is not None:
        factor = float(cfg["is1893_drift_factor"])
    return [float(d) * factor for d in elastic_drifts]


def max_design_drift(elastic_drifts, cfg) -> float:
    vals = design_story_drifts(elastic_drifts, cfg)
    return max(abs(v) for v in vals) if vals else 0.0


def classify_plan_irregularities(cfg, footprint_flags: dict | None = None) -> dict:
    """IS 1893 Table 5 screen from footprint flags (+ optional torsion ratio).

    footprint_flags keys (from engine3d.plan_irregularities geometric proxy):
      reentrant, setback, nonparallel, nonrect
    Optional cfg['torsion_ratio'] or cfg['_tir_screen'] = δmax/δmin for Table 5(i).
    """
    flags = dict(footprint_flags or {})
    out = {
        "standard": "IS_1893_Part_1_2016",
        "cite": "Table 5 / cl.7.1",
        "items": [],
        "todos": [t for t in TODO if not t.get("found", True)],
    }
    tir = cfg.get("torsion_ratio")
    if tir is None:
        tir = cfg.get("_tir_screen")
    if tir is not None:
        tir = float(tir)
        trig = CLAUSES["torsional_irregularity_trigger"]["ratio_trigger"]
        out["items"].append({
            "type": "Torsional Irregularity",
            "triggered": tir > trig,
            "ratio": tir,
            "trigger": trig,
            "cite": "IS 1893 Table 5 (i)",
            "found": True,
        })
    else:
        out["items"].append({
            "type": "Torsional Irregularity",
            "triggered": None,
            "cite": "IS 1893 Table 5 (i)",
            "found": True,
            "note": "No δmax/δmin ratio in cfg — agent must compute from accidental-torsion analysis.",
        })

    _rp = flags.get("reentrant_projection") or {}
    out["items"].append({
        "type": "Re-entrant Corners",
        "triggered": bool(flags.get("reentrant")),
        "cite": "IS 1893 Table 5 (ii)",
        "trigger": "projection > 15% of plan dimension",
        "found": True,
        "max_projection_ratio": _rp.get("max_ratio"),
        "note": ("Table 5(ii) projection test per direction on each level's framed footprint "
                 "(max projection / plan dimension = %.3f vs 0.15)" % float(_rp["max_ratio"])
                 if _rp.get("max_ratio") is not None else
                 "Geometric proxy from footprint non-convexity; confirm projection ratio vs 15%."),
    })
    out["items"].append({
        "type": "Non-Parallel Lateral Force System",
        "triggered": bool(flags.get("nonparallel")),
        "cite": "IS 1893 Table 5 (v)",
        "found": True,
    })
    # Cut-outs / out-of-plane offsets: not inferred from grid alone
    out["items"].append({
        "type": "Floor Slabs having Excessive Cut-Outs or Openings",
        "triggered": None,
        "cite": "IS 1893 Table 5 (iii)",
        "found": True,
        "note": "TODO agent/RAG: opening area vs 50% floor slab — not auto-detected from cfg grid.",
    })
    out["items"].append({
        "type": "Out-of-Plane Offsets in Vertical Elements",
        "triggered": None,
        "cite": "IS 1893 Table 5 (iv)",
        "found": True,
        "note": "TODO agent: declare if LFRS offsets exist; Zones III–V have 0.2% drift / specialist rules.",
    })
    return out


def classify_vertical_irregularities(cfg) -> dict:
    """IS 1893 Table 6 screen — stiffness/mass/geometry proxies only where cfg allows."""
    out = {
        "standard": "IS_1893_Part_1_2016",
        "cite": "Table 6 / cl.7.1",
        "items": [],
    }
    heights = cfg.get("heights") or []
    soft = bool(cfg.get("softstorey_check"))
    # Height jump proxy: first storey much taller than typical
    if len(heights) >= 2 and heights[0] > 1.3 * (sum(heights[1:]) / max(1, len(heights) - 1)):
        soft = True
    out["items"].append({
        "type": "Stiffness Irregularity (Soft Storey)",
        "triggered": soft,
        "cite": "IS 1893 Table 6 (i)",
        "found": True,
        "note": (
            "True soft-storey is stiffness-based (Table 6(i) Amd2: Ki < K_above). "
            "Call storey_stiffness_soft_flags(Ki) after analysis; height jump / cfg flag is advisory only. "
            "When soft: dynamic analysis required; inter-storey drift ≤ 0.002 in soft storey and below. "
            "ASCE Ax amplification: found:false — use cl.7.8.2 design eccentricity."
        ),
    })

    mass_irreg = False
    extra = cfg.get("extra_mass_floors") or {}
    if extra:
        mass_irreg = True  # agent must verify 150% rule with seismic weights
    out["items"].append({
        "type": "Mass Irregularity",
        "triggered": mass_irreg if extra else None,
        "cite": "IS 1893 Table 6 (ii)",
        "trigger": "floor seismic weight > 150% of floor below",
        "found": True,
        "note": "cfg['extra_mass_floors'] present ⇒ check 150% rule via RAG/weights; not auto-proven.",
    })

    setback = False
    # geometric setback via plan callable name or flag from plan_irregularities
    if cfg.get("_vertical_setback") or cfg.get("plan") is not None:
        # plan=setback is a USA archetype hint; treat as possible vertical geometric irregularity
        setback = True
    out["items"].append({
        "type": "Vertical Geometric Irregularity",
        "triggered": setback if cfg.get("_vertical_setback") is not None else None,
        "cite": "IS 1893 Table 6 (iii)",
        "trigger": "LFRS horizontal dimension > 125% of storey below",
        "found": True,
    })
    for t, cite in [
        ("In-Plane Discontinuity in Vertical Elements Resisting Lateral Force", "Table 6 (iv)"),
        ("Strength Irregularity (Weak Storey)", "Table 6 (v)"),
        ("Floating or Stub Columns", "Table 6 (vi)"),
        ("Irregular Modes of Oscillation in Two Principal Plan Directions", "Table 6 (vii)"),
    ]:
        out["items"].append({
            "type": t, "triggered": None, "cite": f"IS 1893 {cite}", "found": True,
            "note": "Not auto-screened — agent must classify from analysis/RAG.",
        })
    return out


def drift_limit_label(cfg) -> str:
    dl, _ = drift_allowable(cfg)
    return (
        f"{dl*100:.2f}% of storey height (IS 1893 Part 1:2016 cl.7.11.1.1; "
        f"VB with γ=1.0; no Cd/Ie amplification)"
    )


# ---------------------------------------------------------------------------
# IS 1893 (Part 1) : 2016 §7.6.2 — approximate fundamental period Ta
# ---------------------------------------------------------------------------
# (a) bare RC MRF:   Ta = 0.075 h^0.75
# (b) bare steel MRF: Ta = 0.085 h^0.75
# (c) all other buildings: Ta = 0.09 h / sqrt(d)
# Fail closed when a non-MRF system (SCBF/CBF/EBF/…) is paired with an MRF formula.

class TaFormulaError(ValueError):
    """Non-MRF system paired with MRF Ta formula (IS 1893 §7.6.2 fail-closed)."""


_MRF_TOKENS = (
    "smrf", "omrf", "imrf", "mrf", "moment frame", "moment-frame", "moment_frame",
    "bare mrf", "steel mrf", "rc mrf", "rcc mrf", "smf", "omf", "imf",
    "special moment", "intermediate moment", "ordinary moment",
)
_NON_MRF_TOKENS = (
    "scbf", "ocbf", "cbf", "ebf", "brbf", "braced", "sbf", "concentric",
    "eccentric", "buckling restrained", "shear wall", "dual", "spsw",
    "frame-shear", "wall frame", "infill",
)


def is_bare_mrf_system(system) -> bool:
    """True only when the SFRS is a bare moment frame (IS 1893 §7.6.2 a/b)."""
    s = str(system or "").strip().lower()
    if not s:
        return False
    if any(t in s for t in _NON_MRF_TOKENS):
        return False
    return any(t in s for t in _MRF_TOKENS)


def _looks_like_mrf_formula(formula: str) -> bool:
    f = str(formula or "").lower().replace(" ", "")
    if not f:
        return False
    # Explicit all-other / 0.09 h/√d wins even if "0.085" appears in a note
    if "0.09" in f and ("sqrt" in f or "√" in formula or "/d" in f or "√d" in formula or "h/" in f):
        return False
    if "allother" in f or "all-other" in f or "§7.6.2(c)" in formula.lower() or "7.6.2(c)" in formula.lower():
        return False
    if "0.085" in f or "0.075" in f:
        return True
    if ("h^0.75" in f or "h**0.75" in f or "h0.75" in f) and "0.09" not in f:
        return True
    return False


def approximate_Ta(h_m: float, d_m: float | None = None, system: str | None = None,
                   formula: str | None = None, material: str | None = None, *, infills: bool = False,
                   clamp: bool = True) -> dict:
    """IS 1893 (Part 1):2016 7.6.2 approximate period (PDF p.21, Amd 2 7.6.2.1).

    (a) bare MRF buildings (without masonry infills): 0.075 h^0.75 RC, 0.080 h^0.75 RC-steel
        composite, 0.085 h^0.75 steel;  (b) RC structural walls (not produced here);
    (c) all other buildings (incl. MRF WITH infills): 0.09 h / sqrt(d).
    7.6.2.1 (Amd 2): Ta shall neither be more than (a) nor less than (c) -- applied when d is given.
    Non-MRF system + MRF formula -> TaFormulaError (fail closed)."""
    h = float(h_m)
    if h <= 0:
        raise ValueError("h_m must be positive (building height in metres)")
    sys_ = system or ""
    bare_mrf = is_bare_mrf_system(sys_) and not infills
    mat = str(material or "").lower()
    sl = str(sys_).lower()
    coef_a = 0.085 if ("steel" in mat or "steel" in sl or not mat) else 0.075
    if "composite" in mat or "composite" in sl:
        coef_a = 0.080
    elif "rc" in mat or "concrete" in mat:
        coef_a = 0.075
    Ta_a = coef_a * h ** 0.75
    Ta_c = 0.09 * h / (float(d_m) ** 0.5) if (d_m is not None and float(d_m) > 0) else None
    if bare_mrf:
        kind = {0.085: "steel_mrf", 0.080: "composite_mrf", 0.075: "rc_mrf"}[coef_a]
        clause = "7.6.2(a)"
        ta = Ta_a
        used = "%.3f h^0.75" % coef_a
    else:
        kind = "all_other" if not infills else "mrf_with_infills"
        clause = "7.6.2(c)"
        if Ta_c is None:
            raise ValueError("d_m (base dimension in metres along vibration) required for 7.6.2(c)")
        ta = Ta_c
        used = "0.09 h/sqrt(d)"
    clamp_note = None
    if clamp and Ta_c is not None:
        t0 = ta
        ta = max(min(ta, Ta_a), Ta_c) if Ta_c <= Ta_a else Ta_c
        if abs(ta - t0) > 1e-12:
            clamp_note = "7.6.2.1 (Amd 2) clamp: %.4f -> %.4f s (<= (a) %.4f, >= (c) %.4f)" % (t0, ta, Ta_a, Ta_c)
    if formula is not None and _looks_like_mrf_formula(formula) and not bare_mrf:
        raise TaFormulaError(
            "IS 1893 7.6.2 fail-closed: system %r is not a bare MRF but Ta formula %r looks like MRF "
            "0.075/0.080/0.085 h^0.75 -- use 0.09 h/sqrt(d) (7.6.2(c))." % (sys_, formula))
    return {"found": True, "standard": IS1893_STEM, "edition": IS1893_EDITION, "clause": clause, "kind": kind,
            "Ta_s": float(ta), "formula": used, "h_m": h, "d_m": None if d_m is None else float(d_m),
            "system": sys_, "bare_mrf": bare_mrf, "Ta_a_s": Ta_a, "Ta_c_s": Ta_c, "clamp_note": clamp_note,
            "cite": "IS 1893 (Part 1):2016 %s%s" % (clause, " + Amd 2 7.6.2.1" if clamp else "")}


def validate_Ta_for_system(cfg, plan: dict | None = None) -> list:
    """Fail-closed findings when non-MRF jobs use an MRF Ta formula.

    Inspects cfg['system'] / load_plan.seismic_summary Ta_formula / Ta_s notes.
    Returns list of (level, message). Missing Ta is not an ERROR (agent may still
    be building the plan); wrong formula for the system is ERROR.
    """
    out = []
    if not isinstance(cfg, dict):
        return out
    plan = plan if plan is not None else (cfg.get("load_plan") or {})
    if not isinstance(plan, dict):
        plan = {}
    ss = plan.get("seismic_summary") or plan.get("seis_summary") or {}
    if not isinstance(ss, dict):
        ss = {}
    system = (
        cfg.get("system")
        or ss.get("system")
        or (cfg.get("seis") or {}).get("system")
        or ""
    )
    formula = (
        ss.get("Ta_formula")
        or ss.get("Ta_formula_note")
        or ss.get("formula")
        or cfg.get("Ta_formula")
        or ""
    )
    if not formula and not ss:
        return out  # nothing to check yet
    if formula and _looks_like_mrf_formula(str(formula)) and not is_bare_mrf_system(system):
        out.append((
            "ERROR",
            "IS 1893 §7.6.2 Ta fail-closed: system %r is not a bare MRF but load_plan "
            "uses MRF Ta formula %r. Use §7.6.2(c) Ta=0.09 h/√d (all other buildings). "
            "Do not silently keep 0.085 h^0.75 / 0.075 h^0.75 for SCBF/CBF/EBF/dual/wall systems."
            % (system or "(undeclared)", formula),
        ))
        return out
    # If system is clearly non-MRF and Ta present without formula, require formula citation
    if system and not is_bare_mrf_system(system) and ss.get("Ta_s") is not None and not formula:
        out.append((
            "WARN",
            "load_plan.seismic_summary has Ta_s but no Ta_formula — record §7.6.2(c) "
            "'0.09 h/√d' (or MRF clause if truly bare MRF) so the fail-closed gate can verify.",
        ))
    return out



def mass_irregularity_screen_note(W_by_floor_kN=None, *, zone=None, ratio_trigger=1.5):
    """Document IS 1893 Table 6(ii) mass irregularity screen (mezzanine / partial floors).

    Flags when any floor seismic weight > 150% of the floor below. Returns found screen
    result + Zone applicability note. Does not invent a dynamic-analysis mandate beyond
    what the clause/table requires — agent/policy decides RS vs ELF follow-up.
    """
    clause = CLAUSES.get("mass_irregularity") or {}
    trigger = float(clause.get("ratio_trigger") or ratio_trigger)
    weights = [float(w) for w in (W_by_floor_kN or []) if w is not None]
    ratios = []
    flagged = []
    for i in range(1, len(weights)):
        below = weights[i - 1]
        if below <= 0:
            continue
        r = weights[i] / below
        ratios.append({"floor_above_1based": i + 1, "ratio": r, "W_above": weights[i], "W_below": below})
        if r > trigger:
            flagged.append(ratios[-1])
    irregular = len(flagged) > 0
    zone_s = str(zone or "").upper().replace("ZONE", "").strip()
    return {
        "found": True if weights else False,
        "irregular": irregular if weights else None,
        "ratio_trigger": trigger,
        "ratios": ratios,
        "flagged": flagged,
        "cite": clause.get("clause") or "IS 1893 Table 6 (ii)",
        "clause_text": clause.get("text"),
        "zone": zone,
        "note": (
            "Mass irregularity Table 6(ii): seismic weight of any floor > 150%% of the floor below. "
            "Amd 2: 'In a building with mass irregularity and located in Seismic Zones III, IV and V, "
            "the earthquake effects shall be estimated by dynamic analysis (as per 7.7)'. Zone %s."
            % (zone_s or "(undeclared)")
        ),
        "requires_dynamic_analysis": bool(irregular and zone_s in ("III", "IV", "V")),
        "required_inputs": [] if weights else ["W_by_floor_kN list (seismic weight per floor)"],
    }

# --- complete-gap wave2: R / Ω0 provenance (re-export) -------------------------
try:
    from india_seismic_gates import (  # noqa: E402
        resolve_R,
        resolve_Omega0,
        validate_R,
        complete_allowed,
        R_is_proxy,
        omega0_blocks_complete,
        design_status,
        complete_gate_disclosure,
        needs_table9_miss_gate,
        table9_system_flags,
        R_OK_SOURCES,
        R_PROXY_SOURCES,
        TABLE9_SYSTEM_FLAGS,
        fetch_is18168_omega,
        resolve_Omega0_with_is18168,
    )
except ImportError:  # pragma: no cover
    pass




# ---------------------------------------------------------------------------
# WP1.8 -- IS 1893 Tables 5 and 6 as substituted by Amendment 2 (PDF pp. 50-54)
# ---------------------------------------------------------------------------
def torsion_classification(ratio) -> dict:
    """Table 5(i) (Amd 2): Delta_max / Delta_ave <= 1.2 regular; 1.2-1.4 irregular (torsional mode
    period below both translational + 3D dynamic analysis); > 1.4 revise the configuration."""
    r = float(ratio)
    if r <= 1.2:
        return {"ratio": r, "band": "<= 1.2", "irregular": False, "verdict": "regular in torsion"}
    if r <= 1.4:
        return {"ratio": r, "band": "1.2-1.4", "irregular": True, "requires_dynamic_analysis": True,
                "requires_torsional_period_check": True,
                "verdict": "torsionally irregular: fundamental torsional period must be smaller than the first two "
                           "translational periods, and 3D dynamic analysis is required (Table 5(i), Amd 2)"}
    return {"ratio": r, "band": "> 1.4", "irregular": True,
            "verdict": "revise configuration: Delta_max > 1.4 Delta_ave (Table 5(i)(ii), Amd 2)"}


def torsion_ratio_from_edges(d1, d2) -> float:
    """Delta_max / Delta_ave with Delta_ave = (Delta_max + Delta_min)/2 (Amd 2 Table 5(i))."""
    a, b = abs(float(d1)), abs(float(d2))
    mx, mn = max(a, b), min(a, b)
    return mx / ((mx + mn) / 2.0) if mx > 0 else 1.0


def soft_storey_screen(K, exempt=()) -> dict:
    """Table 6(i) (Amd 2): storey i is soft when K_i < K of the storey above; exempt storeys (declared
    split-level offsets, services storeys per the Note) are skipped and the comparison is made with
    the next non-exempt storey above."""
    n = len(K)
    ex = set(int(e) - 1 for e in (exempt or ()))
    idx = [i for i in range(n) if i not in ex]
    soft = [False] * n
    ratios = [None] * n
    for a_, i in enumerate(idx[:-1]):
        j = idx[a_ + 1]
        if K[j] and K[j] != float("inf"):
            ratios[i] = K[i] / K[j]
            soft[i] = K[i] < K[j]
    lim = [CLAUSES["storey_drift_limit"]["limit_ratio"]] * n
    for s_, f in enumerate(soft):
        if f:
            for i in range(0, s_ + 1):
                lim[i] = CLAUSES["soft_storey"]["soft_storey_drift_limit"]
    return {"soft": soft, "ratio_to_above": ratios, "drift_limit_by_storey": lim, "irregular": any(soft),
            "requires_dynamic_analysis": any(soft), "soft_storey_indices": [i for i, f in enumerate(soft) if f],
            "clause": "IS 1893 Table 6(i) (Amd 2)",
            "verdict": ("soft storey(s) %s: dynamic analysis + drift <= 0.2 %% in that storey and below"
                        % [i + 1 for i, f in enumerate(soft) if f]) if any(soft) else "no soft storey"}


R9_RULE = ("owner ruling R9: fundamental torsional mode = the longest-period mode whose rotational participation "
           "exceeds both its X and Y mass participation; Tx / Ty = the longest-period X-dominant / Y-dominant modes "
           "(distinct); Table 6(vii) counts the first three translational-dominant modes (max(mass_x, mass_y) > rot)")


def _by_period(modes):
    return sorted([dict(m, mode=m.get("mode", n + 1)) for n, m in enumerate(modes)], key=lambda m: -float(m.get("T", 0.0)))


def fundamental_modes(modes) -> dict:
    """R9 mode identification: {'torsional', 'x', 'y'} -> mode dict or None (longest-period mode of each kind)."""
    ms = _by_period(modes)
    g = lambda m, k: float(m.get(k, 0.0) or 0.0)
    tor = next((m for m in ms if g(m, "rot") > g(m, "mass_x") and g(m, "rot") > g(m, "mass_y")), None)
    tx = next((m for m in ms if g(m, "mass_x") > g(m, "mass_y") and g(m, "mass_x") >= g(m, "rot")), None)
    ty = next((m for m in ms if g(m, "mass_y") > g(m, "mass_x") and g(m, "mass_y") >= g(m, "rot")), None)
    return {"torsional": tor, "x": tx, "y": ty}


def modes_screen(modes, zone) -> dict:
    """Table 6(vii) (Amd 2): first three lateral translational modes >= 65 % mass in each direction
    (all zones); Zones IV/V also fundamental Tx, Ty at least 10 % apart.  H51: the modes counted are
    recorded (ruling R9)."""
    ms = _by_period(modes)
    trans = [m for m in ms if max(m.get("mass_x", 0), m.get("mass_y", 0)) > m.get("rot", 0)]
    first3 = trans[:3]
    mx = sum(m.get("mass_x", 0) for m in first3); my = sum(m.get("mass_y", 0) for m in first3)
    fm = fundamental_modes(modes)
    tx, ty = fm["x"], fm["y"]
    sep = None
    if tx and ty:
        sep = abs(tx["T"] - ty["T"]) / max(tx["T"], ty["T"])
    z = str(zone or "").upper()
    a_ok = mx >= 0.65 and my >= 0.65
    b_ok = True if z not in ("IV", "V") or sep is None else sep >= 0.10
    ok = a_ok and b_ok
    return {"first3_mass_x": mx, "first3_mass_y": my, "Tx": tx and tx["T"], "Ty": ty and ty["T"], "separation": sep,
            "modes_counted": [m["mode"] for m in first3], "mode_Tx": tx and tx["mode"], "mode_Ty": ty and ty["mode"],
            "modes_excluded_rotation_dominant": [m["mode"] for m in ms if m not in trans][:6],
            "rule": R9_RULE,
            "irregular": not ok, "clause": "IS 1893 Table 6(vii) (Amd 2)",
            "verdict": "modes regular" if ok else
            "revise configuration: Table 6(vii) (Amd 2) requires the first three translational modes >= 65 %% mass "
            "(%.0f %% / %.0f %%)%s" % (100 * mx, 100 * my,
                                       "" if b_ok else " and Tx, Ty at least 10 %% apart in Zone %s (%.1f %%)" % (z, 100 * (sep or 0)))}


def torsional_period_ok(modes) -> dict:
    """Table 5(i) (Amd 2): the fundamental torsional mode period must be smaller than those of the first two
    translational modes.  H03 / ruling R9: torsional = the longest-period rotation-dominant mode (not the most
    rotational one), Tx / Ty = the longest-period X- / Y-dominant modes (distinct modes)."""
    fm = fundamental_modes(modes)
    tor, tx, ty = fm["torsional"], fm["x"], fm["y"]
    rec = {"rule": R9_RULE, "clause": "IS 1893 Table 5(i) (Amd 2)",
           "mode_torsional": tor and tor["mode"], "mode_Tx": tx and tx["mode"], "mode_Ty": ty and ty["mode"]}
    if not (tor and tx and ty):
        rec.update(ok=None, reason="no %s mode identified" % "/".join(
            n for n, m in (("rotation-dominant", tor), ("X-dominant", tx), ("Y-dominant", ty)) if not m))
        return rec
    ok = tor["T"] < tx["T"] and tor["T"] < ty["T"]
    rec.update(ok=ok, T_torsion=tor["T"], Tx=tx["T"], Ty=ty["T"],
               verdict="torsional mode period below both translational periods" if ok else
               "revise configuration: fundamental torsional period %.3f s (mode %s) is not below Tx %.3f (mode %s) / "
               "Ty %.3f (mode %s) (Table 5(i), Amd 2)" % (tor["T"], tor["mode"], tx["T"], tx["mode"], ty["T"], ty["mode"]))
    return rec


def irregularity_screens(cfg, run) -> dict:
    """ONE irregularity record for the package, the report and the gates (WP1.8)."""
    import india_seismic_gates as G
    z = G.zone_of(cfg)
    out = {"edition": IS1893_EDITION}
    dr = run.get("drift") or {}
    modes = (run.get("rsa") or {}).get("modes") or run.get("modes") or []
    rmax = max([max(v["ratio"]) for v in dr.values()] or [1.0])
    tc = torsion_classification(rmax)
    tc["clause"] = "IS 1893 Table 5(i) (Amd 2); Delta at the extreme edges incl. 7.8.2 eccentricity"
    if tc.get("requires_torsional_period_check") and modes:
        tp = torsional_period_ok(modes)
        tc["torsional_period"] = tp
        if tp.get("ok") is False:
            tc["verdict"] = tp["verdict"]
    out["torsion"] = tc
    ss = {}
    exempt = [int(k) for k in (cfg.get("drift_exempt_stories") or {})] + [int(k) for k in (cfg.get("soft_storey_exempt") or [])]
    for d, v in dr.items():
        ss[d] = soft_storey_screen(v.get("stiffness_N_per_mm") or [], exempt)
    soft = {"irregular": any(v["irregular"] for v in ss.values()), "by_direction": ss,
            "clause": "IS 1893 Table 6(i) (Amd 2)",
            "stiffness_basis": next((v.get("stiffness_basis") for v in dr.values() if v.get("stiffness_basis")), None)}
    if soft["irregular"]:
        lim = [min(a, b) for a, b in zip(*(v["drift_limit_by_storey"] for v in ss.values()))] if len(ss) > 1 else \
            list(ss.values())[0]["drift_limit_by_storey"]
        cfg["_soft_storey_flags"] = {"drift_limit_by_storey": lim}
        soft["verdict"] = "; ".join("%s: %s" % (d, v["verdict"]) for d, v in ss.items() if v["irregular"])
        soft["requires_dynamic_analysis"] = True
    out["soft_storey"] = soft
    ssum = ((cfg.get("load_plan") or {}).get("seismic_summary") or {})
    W = ssum.get("W_by_floor_kN") or []
    mi = mass_irregularity_screen_note(W, zone=z)
    out["mass"] = {"irregular": bool(mi.get("irregular")), "flagged": mi.get("flagged"), "clause": "IS 1893 Table 6(ii) (Amd 2)",
                   "requires_dynamic_analysis": mi.get("requires_dynamic_analysis"), "verdict": mi.get("note")}
    try:
        import engine3d as E
        NF = len(cfg["heights"])
        ext = []
        for k in range(1, NF + 1):
            pts = E.grid(cfg, k)
            xs = [E._xy_in(cfg, i, j)[0] for i, j in pts]; ys = [E._xy_in(cfg, i, j)[1] for i, j in pts]
            ext.append(max(max(xs) - min(xs), max(ys) - min(ys)))
        vg = [k + 1 for k in range(1, NF) if ext[k - 1] > 0 and ext[k] > 1.25 * ext[k - 1]]
        out["vertical_geometric"] = {"irregular": bool(vg), "storeys": vg, "clause": "IS 1893 Table 6(iii) (Amd 2)",
                                     "requires_dynamic_analysis": bool(vg) and z in ("III", "IV", "V"),
                                     "verdict": "LFRS plan dimension > 125 %% of the storey below at %s" % vg if vg else "none"}
        pir = E.plan_irregularities(cfg)
        _rp = pir.get("reentrant_projection") or {}
        out["reentrant"] = {"irregular": bool(pir.get("reentrant")), "clause": "IS 1893 Table 5(ii) (Amd 2)",
                            "max_projection_ratio": _rp.get("max_ratio"), "trigger": 0.15, "cite": _rp.get("cite"),
                            "requires_flexible_diaphragm_analysis": bool(pir.get("reentrant")),
                            "verdict": "re-entrant corners: 3D dynamic analysis with a flexible diaphragm in addition "
                                       "to the rigid case" if pir.get("reentrant") else "none"}
        out["nonparallel"] = {"irregular": bool(pir.get("nonparallel")), "clause": "IS 1893 Table 5(v) (Amd 2)",
                              "verdict": "6.3.2.2 / 6.3.4.1 combinations" if pir.get("nonparallel") else "none"}
        fl = floating_columns(cfg)
        out["floating_columns"] = fl
    except Exception as ex:
        out["geometry_error"] = str(ex)
    ipd = cfg.get("in_plane_discontinuity")
    out["in_plane_discontinuity"] = {"irregular": bool(ipd), "clause": "IS 1893 Table 6(iv) (Amd 2)",
                                     "verdict": ("not permitted in Seismic Zones III, IV and V" if ipd and z in ("III", "IV", "V")
                                                 else ("Zone II: building drift <= 0.2 %% of height" if ipd else "none declared"))}
    ws = cfg.get("weak_storey")
    out["strength"] = {"irregular": bool(ws), "clause": "IS 1893 Table 6(v) (Amd 2)",
                       "verdict": "buildings with strength irregularity shall not be permitted" if ws else
                       "no weak storey declared (storey strengths are the EOR's declaration)"}
    oo = cfg.get("out_of_plane_offset")
    out["out_of_plane_offset"] = {"irregular": bool(oo), "clause": "IS 1893 Table 5(iv) (Amd 2)",
                                  "verdict": ("Zones III-V: forces in connecting elements x 2.5 and drift < 0.2 %% "
                                              "at and below the offset storey") if oo else "none declared"}
    if modes:
        out["modes"] = modes_screen(modes, z)
    return out


def floating_columns(cfg) -> dict:
    """Table 6(vi) (Amd 2): a column whose lower end rests on a beam (no column / base below)."""
    import engine3d as E
    info = E.build(cfg, "Linear")
    tops = set()
    bots = []
    lateral = set(info.get("moment_nodes") or [])
    brace_nodes = set()
    for (t, kind, sec, n1, n2) in info["ele"]:
        if kind == "col":
            tops.add(n2)
            bots.append((t, n1, n2))
        if kind == "brace":
            brace_nodes |= {n1, n2}
    # H35: a column whose lower end is a support (restrained foundation / declared stepped base) is not floating
    sup = E.support_nodes() | {E.ntag(i, j, k) for k, v in E.declared_node_sets(cfg, info, "stepped_bases").items()
                               for (i, j) in v}
    fl = [t for (t, n1, n2) in bots if (n1 // 100000) > 0 and n1 not in tops and n1 not in sup]
    lat = [t for (t, n1, n2) in bots if t in fl and (n1 in brace_nodes or n2 in brace_nodes or n1 in lateral or n2 in lateral)]
    return {"irregular": bool(fl), "columns": fl, "in_lateral_system": lat, "clause": "IS 1893 Table 6(vi) (Amd 2)",
            "verdict": ("not permitted: floating columns part of / supporting the lateral system %s" % lat) if lat else
            ("floating columns %s (gravity only)" % fl if fl else "none")}


def separation_required(R1, D1, R2=None, D2=None, same_floor_levels=False) -> dict:
    """IS 1893 7.11.3 (+ Amd 1): R x (D1 + D2); (R1 D1 + R2 D2)/2 when floor levels match."""
    R2 = R1 if R2 is None else R2
    D2 = 0.0 if D2 is None else D2
    if same_floor_levels:
        v = (R1 * D1 + R2 * D2) / 2.0
        c = "IS 1893 7.11.3 as amended by Amd 1: (R1 D1 + R2 D2)/2"
    else:
        v = R1 * D1 + R2 * D2
        c = "IS 1893 7.11.3: R x (D1 + D2)"
    return {"required_mm": v, "cite": c}
