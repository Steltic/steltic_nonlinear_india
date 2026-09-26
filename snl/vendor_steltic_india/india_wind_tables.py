"""IS 875 (Part 3) : 2015 Ka / Cpe helpers (S6) — corpus-prefer, in-repo fallback.

Policy (QFM 2026-09-19 OCR reingest — Tables 5/6/7/11/18/21/22/29 corpus-HIT):
  * Table 4 Ka — prefer corpus RAG ``exact_table 4``. In-repo breakpoints are **fallback only**
    when corpus returns found:false / unavailable. Never invent beyond the three points
    (interpolate between them only).
  * Table 5 wall Cpe — prefer corpus RAG ``exact_table 5`` (clean after OCR reingest).
    In-repo ``TABLE_5_CPE_WALLS`` / ``cpe_walls()`` are **fallback only** when corpus
    found:false. Do NOT invent Cpe; do NOT use legacy Docling OCR cells if they reappear.
  * Other wind-path tables now live in corpus (prefer exact_table): 6, 7, 11, 18, 21, 22, 29.
  * Never invent Ka/Cpe outside corpus / shipped fallback tables.

Provenance / QFM note:
  * ``/workspace/handoff/qfm/IS875_P3_OCR_reingest_2026-09-19.md``
  * PDF: /workspace/INDIA_STEEL/pdfs/IS_875_Part_3_2015.pdf (BIS)
  * Table 4: QFM ``Table_4_Ka_recovered.md``; corpus exact_table 4 OK.
  * Table 5: QFM recovered page 015 + ``Table_5_recovered``; corpus exact_table 5 HIT.
"""
from __future__ import annotations

STEM = "IS_875_Part_3_2015"
COLLECTION = "engineering_standards_IS875_P3"

# ---------------------------------------------------------------------------
# Table 4 — Area Averaging Factor Ka (Clause 7.2.2)
# Prefer corpus exact_table 4; these breakpoints are fallback only.
# ---------------------------------------------------------------------------
TABLE_4_KA = {
    "found": True,
    "stem": STEM,
    "clause": "7.2.2",
    "table": "Table 4",
    "title": "Area Averaging Factor (Ka)",
    "source": "corpus_preferred",  # exact_table 4 reliable as of 2026-09-19 QFM
    "fallback_ok": True,
    "provenance": (
        "IS 875 (Part 3) : 2015 Table 4 / cl.7.2.2. "
        "Prefer RAG exact_table 4 from engineering_standards_IS875_P3. "
        "Hardcoded breakpoints match QFM-verified recovery (≤10→1.0, 25→0.9, ≥100→0.8)."
    ),
    # (A_m2_max_or_exact, Ka) — breakpoints for lookup / interpolation
    "breakpoints": [
        {"A_m2": 10.0, "Ka": 1.0, "rule": "A <= 10"},
        {"A_m2": 25.0, "Ka": 0.9, "rule": "A == 25 (interpolate from 10 and 100)"},
        {"A_m2": 100.0, "Ka": 0.8, "rule": "A >= 100"},
    ],
    "note": "Linear interpolation for intermediate values of A is permitted (Table 4 Note *).",
}


def ka_for_area_m2(A_m2: float, *, allow_fallback: bool = True) -> dict:
    """Return Ka for tributary area A (m²).

    Prefer calling this only as fallback when RAG Table 4 is missing/noisy.
    Does not invent beyond the three shipped breakpoints (+ linear interpolation).
    """
    if not allow_fallback:
        return {
            "found": False,
            "Ka": None,
            "cite": "Table 4 fallback disabled — retrieve exact_table 4 from corpus",
            "source": "refused",
        }
    A = float(A_m2)
    if A <= 10.0:
        ka = 1.0
        rule = "A <= 10 m²"
    elif A >= 100.0:
        ka = 0.8
        rule = "A >= 100 m²"
    else:
        # Linear interpolation between (10, 1.0) and (100, 0.8); 25 → 0.9 is on that line
        # (1.0 - 0.8) * (100-A)/(100-10) + 0.8, or piecewise via 25 for clarity:
        if A <= 25.0:
            ka = 1.0 + (0.9 - 1.0) * (A - 10.0) / (25.0 - 10.0)
            rule = "linear interp 10→25 m²"
        else:
            ka = 0.9 + (0.8 - 0.9) * (A - 25.0) / (100.0 - 25.0)
            rule = "linear interp 25→100 m²"
    return {
        "found": True,
        "Ka": round(ka, 6),
        "A_m2": A,
        "rule": rule,
        "cite": "IS 875 (Part 3) : 2015 Table 4 / cl.7.2.2 (in-repo fallback; prefer corpus exact_table 4)",
        "source": "india_wind_tables.TABLE_4_KA",
        "table_meta": {k: TABLE_4_KA[k] for k in ("stem", "clause", "table", "provenance")},
    }


# ---------------------------------------------------------------------------
# Table 5 — External Pressure Coefficients Cpe for walls of rectangular clad
# buildings (Clause 7.3.3.1). Verified from PDF figure — NOT from Docling OCR.
# Surfaces A/B/C/D and Local Cpe per the code table layout.
# ---------------------------------------------------------------------------
# Each row: height_ratio band, plan_ratio band, wind_angle_deg -> Cpe A,B,C,D + local
# Bands use inclusive upper bounds matching the printed table wording.

def _row(hw, lw, theta, A, B, C, D, local):
    return {
        "h_over_w": hw,
        "l_over_w": lw,
        "theta_deg": theta,
        "Cpe": {"A": A, "B": B, "C": C, "D": D},
        "Cpe_local": local,
    }


# Verified transcription of IS 875 (Part 3) : 2015 Table 5 (PDF page 15 figure).
TABLE_5_CPE_WALLS = {
    "found": True,
    "stem": STEM,
    "clause": "7.3.3.1",
    "table": "Table 5",
    "title": "External Pressure Coefficients (Cpe) for Walls of Rectangular Clad Buildings",
    "source": "corpus_preferred",  # exact_table 5 HIT after 2026-09-19 QFM OCR reingest
    "fallback_ok": True,
    "ocr_trust": False,  # legacy Docling cells still untrusted if they reappear
    "provenance": (
        "IS 875 (Part 3) : 2015 Table 5 / cl.7.3.3.1. "
        "Prefer RAG exact_table 5 from engineering_standards_IS875_P3 "
        "(QFM OCR reingest 2026-09-19 HIT). "
        "In-repo rows match QFM Table_5_recovered — use only when corpus found:false. "
        "h = height to eaves/parapet; l = greater plan dim; w = lesser plan dim."
    ),
    "definitions": {
        "h": "height to eaves or parapet",
        "l": "greater horizontal dimension of building",
        "w": "lesser horizontal dimension of building",
        "theta_0": "wind normal to face A (along w)",
        "theta_90": "wind normal to face C (along l)",
    },
    "rows": [
        # h/w ≤ 1/2
        _row("<=0.5", "1<l/w<=1.5", 0, +0.7, -0.2, -0.5, -0.5, -0.8),
        _row("<=0.5", "1<l/w<=1.5", 90, -0.5, -0.5, +0.7, -0.2, -0.8),
        _row("<=0.5", "1.5<l/w<4", 0, +0.7, -0.25, -0.6, -0.6, -1.0),
        _row("<=0.5", "1.5<l/w<4", 90, -0.5, -0.5, +0.7, -0.1, -1.0),
        # 1/2 < h/w ≤ 3/2
        _row("0.5<h/w<=1.5", "1<=l/w<=1.5", 0, +0.7, -0.25, -0.6, -0.6, -1.1),
        _row("0.5<h/w<=1.5", "1<=l/w<=1.5", 90, -0.6, -0.6, +0.7, -0.25, -1.1),
        _row("0.5<h/w<=1.5", "1.5<=l/w<4", 0, +0.7, -0.3, -0.7, -0.7, -1.1),
        _row("0.5<h/w<=1.5", "1.5<=l/w<4", 90, -0.5, -0.5, +0.7, -0.1, -1.1),
        # 3/2 < h/w < 6 (printed strict upper bound; h/w = 6 belongs to the h/w >= 6 rows)
        _row("1.5<h/w<6", "1<l/w<=1.5", 0, +0.8, -0.25, -0.8, -0.8, -1.2),
        _row("1.5<h/w<6", "1<l/w<=1.5", 90, -0.8, -0.8, +0.8, -0.25, -1.2),
        _row("1.5<h/w<6", "1.5<=l/w<4", 0, +0.7, -0.4, -0.7, -0.7, -1.2),
        _row("1.5<h/w<6", "1.5<=l/w<4", 90, -0.5, -0.5, +0.8, -0.1, -1.2),
        # h/w ≥ 6 (discrete plan ratios in the printed table)
        _row(">=6", "l/w=1.0", 0, +0.95, -1.25, -0.7, -0.7, -1.25),
        _row(">=6", "l/w=1.0", 90, -0.7, -0.7, +0.95, -1.25, -1.25),
        _row(">=6", "l/w=1.5", 0, +0.95, -1.85, -0.9, -0.9, -1.25),
        _row(">=6", "l/w=1.5", 90, -0.8, -0.8, +0.9, -0.85, -1.25),
        _row(">=6", "l/w=2", 0, +0.85, -0.75, -0.75, -0.75, -1.25),
        _row(">=6", "l/w=2", 90, -0.75, -0.75, +0.85, -0.75, -1.25),
    ],
}


def _hw_band(h_over_w: float) -> str | None:
    """H15: band edges as printed (IS 875-3 Table 5): h/w <= 1/2; 1/2 < h/w <= 3/2; 3/2 < h/w < 6; h/w >= 6."""
    r = float(h_over_w)
    if r <= 0.5:
        return "<=0.5"
    if r <= 1.5:
        return "0.5<h/w<=1.5"
    if r < 6.0:
        return "1.5<h/w<6"
    return ">=6"


def _lw_band(h_band: str, l_over_w: float) -> str | None:
    """Map plan ratio into the printed Table 5 band for the given height band (H15: printed inequalities).

    Printed: h/w <= 1/2: '1 < l/w <= 3/2', '3/2 < l/w < 4'; 1/2 < h/w <= 3/2: '1 <= l/w <= 3/2', '3/2 <= l/w < 4';
    3/2 < h/w < 6: '1 < l/w <= 3/2', '3/2 <= l/w < 4'.  l/w >= 4 has no row (an EOR Cpe is required, see
    resolve_cpe_walls(eor_cpe=...)).  WP6-fix kept: a square plan (l/w = 1.0) belongs to the first band (the lower
    bound is read as inclusive everywhere -- no other row could apply to a square building).  Where two printed rows
    both contain l/w = 3/2 (middle and upper bands), the first printed row is used."""
    r = float(l_over_w)
    if h_band in ("<=0.5", "0.5<h/w<=1.5", "1.5<h/w<6"):
        if 1.0 <= r <= 1.5:
            return {"<=0.5": "1<l/w<=1.5", "0.5<h/w<=1.5": "1<=l/w<=1.5", "1.5<h/w<6": "1<l/w<=1.5"}[h_band]
        if 1.5 < r < 4.0:
            return {"<=0.5": "1.5<l/w<4", "0.5<h/w<=1.5": "1.5<=l/w<4", "1.5<h/w<6": "1.5<=l/w<4"}[h_band]
        return None
    # h/w >= 6: discrete printed plan ratios only — no invention
    if abs(r - 1.0) < 1e-9:
        return "l/w=1.0"
    if abs(r - 1.5) < 1e-9:
        return "l/w=1.5"
    if abs(r - 2.0) < 1e-9:
        return "l/w=2"
    return None


def cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float = 0.0) -> dict:
    """Lookup Table 5 wall Cpe. Returns found:false if outside shipped bands (no invention)."""
    theta = float(theta_deg)
    if abs(theta - 0.0) > 1e-9 and abs(theta - 90.0) > 1e-9:
        return {
            "found": False,
            "Cpe": None,
            "cite": "Table 5 override only ships θ = 0° and 90° — retrieve other angles from RAG/PDF",
            "source": "refused_angle",
        }
    theta_key = 0 if abs(theta - 0.0) <= 1e-9 else 90
    hw = _hw_band(h_over_w)
    lw = _lw_band(hw, l_over_w) if hw else None
    if not hw or not lw:
        return {
            "found": False,
            "Cpe": None,
            "h_over_w": float(h_over_w),
            "l_over_w": float(l_over_w),
            "cite": (
                "Geometry outside shipped Table 5 override bands — do not invent Cpe; "
                "consult IS 875 Part 3 PDF / specialist literature (Table 5 note)."
            ),
            "source": "refused_band",
            "table_meta": {k: TABLE_5_CPE_WALLS[k] for k in ("stem", "clause", "table", "provenance")},
        }
    for row in TABLE_5_CPE_WALLS["rows"]:
        if row["h_over_w"] == hw and row["l_over_w"] == lw and row["theta_deg"] == theta_key:
            return {
                "found": True,
                "Cpe": dict(row["Cpe"]),
                "Cpe_local": row["Cpe_local"],
                "h_over_w": float(h_over_w),
                "l_over_w": float(l_over_w),
                "theta_deg": theta_key,
                "band": {"h_over_w": hw, "l_over_w": lw},
                "cite": "IS 875 (Part 3) : 2015 Table 5 / cl.7.3.3.1 (in-repo fallback; prefer corpus exact_table 5)",
                "source": "india_wind_tables.TABLE_5_CPE_WALLS",
                "table_meta": {k: TABLE_5_CPE_WALLS[k] for k in ("stem", "clause", "table", "provenance")},
            }
    return {
        "found": False,
        "Cpe": None,
        "cite": "No Table 5 override row matched — refuse invented Cpe",
        "source": "refused_miss",
    }


# Common terrain category labels (Table 2 context) — descriptive only; k2 still from RAG/PDF.
TERRAIN_CATEGORIES = {
    "found": True,
    "stem": STEM,
    "clause": "6.3.2.1",
    "note": (
        "Terrain category descriptions for agent orientation. "
        "k2 multipliers remain Table 2 — retrieve from corpus/PDF; not duplicated here to avoid drift."
    ),
    "categories": {
        1: "Exposed open terrain with few or no obstructions; z0,1 = 0.002 m",
        2: "Open terrain with well-scattered obstructions generally 1.5–10 m; z0,2 = 0.02 m",
        3: "Terrain with numerous closely spaced obstructions up to 10 m (towns); z0,3 = 0.2 m",
        4: "Terrain with numerous large high closely spaced obstructions (city centres); z0,4 = 2.0 m",
    },
}


# Tables now corpus-HIT for the wind path (QFM OCR reingest 2026-09-19).
CORPUS_LIVE_WIND_TABLES = (4, 5, 6, 7, 11, 18, 21, 22, 29)
QFM_OCR_NOTE = "/workspace/handoff/qfm/IS875_P3_OCR_reingest_2026-09-19.md"


def _corpus_found(hit) -> bool:
    """True when an agent/RAG exact_table payload is usable (found:true with content)."""
    if not isinstance(hit, dict):
        return False
    if hit.get("found") is False:
        return False
    if hit.get("found") is True:
        return True
    # tolerate alternate shapes: non-empty text/rows with content
    if hit.get("text") or hit.get("rows") or hit.get("Ka") is not None or hit.get("Cpe"):
        return True
    return False


KA_AREA_CHECK_TOL = 0.0015      # RR-BUG-6: rounding tolerance of a declared Ka against Table 4 at the actual area


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ka_from_area_table(tab, A):
    """{area_m2: Ka} (keys numeric or numeric strings) -> Ka at A, linear between rows, end values beyond."""
    pts = sorted((_num(a), _num(k)) for a, k in dict(tab).items() if _num(a) is not None and _num(k) is not None)
    if not pts:
        return None
    if A <= pts[0][0]:
        return pts[0][1]
    for (a1, k1), (a2, k2) in zip(pts, pts[1:]):
        if a1 <= A <= a2:
            return k1 + (k2 - k1) * (A - a1) / (a2 - a1) if a2 > a1 else k2
    return pts[-1][1]


def _declared_ka(hit, A, direction):
    """RR-BUG-6: the Ka a corpus / EOR hit declares for this area and direction -> (Ka, basis).
    Accepted forms: {'Ka': x} (one value, area-checked), {'Ka_x': x, 'Ka_y': y} / {'Ka': {'X': x, 'Y': y}}
    (per direction), {'table': {area_m2: Ka}} / {'Ka': {area_m2: Ka}} / {'Ka_by_area': {...}} (Table 4 rows)."""
    d = str(direction or "").upper()
    for key in ("table", "Ka_by_area", "rows_by_area"):
        if isinstance(hit.get(key), dict):
            k = _ka_from_area_table(hit[key], A)
            if k is not None:
                return k, "area_table"
    ka = hit.get("Ka")
    if isinstance(ka, dict):
        low = {str(k).upper(): v for k, v in ka.items()}
        if low.get("X") is not None or low.get("Y") is not None:
            if d in ("X", "Y") and _num(low.get(d)) is not None:
                return _num(low[d]), "per_direction"
            vals = [_num(v) for v in (low.get("X"), low.get("Y")) if _num(v) is not None]
            return (max(vals), "per_direction_max") if vals else (None, None)
        k = _ka_from_area_table(ka, A)
        return (k, "area_table") if k is not None else (None, None)
    per = {"X": _num(hit.get("Ka_x", hit.get("Ka_X"))), "Y": _num(hit.get("Ka_y", hit.get("Ka_Y")))}
    if per["X"] is not None or per["Y"] is not None:
        if d in ("X", "Y") and per[d] is not None:
            return per[d], "per_direction"
        vals = [v for v in per.values() if v is not None]
        return max(vals), "per_direction_max"
    return _num(ka), "single"


def resolve_ka(A_m2: float, corpus_hit=None, *, allow_fallback: bool = True, direction=None) -> dict:
    """Prefer corpus exact_table 4; demote in-repo Ka to fallback when corpus found:false.

    RR-BUG-6: a declared corpus Ka is per direction ('Ka_x' / 'Ka_y', ``direction`` = 'X' | 'Y') or a Table 4
    {area: Ka} table read at A_m2; a single declared Ka is checked against Table 4 at THIS tributary area and is never
    applied where Table 4 gives a higher Ka (unconservative): the Table 4 value at A_m2 is used and the record says so
    (``area_check``)."""
    if _corpus_found(corpus_hit):
        out = dict(corpus_hit)
        out.setdefault("found", True)
        out.setdefault("source", "corpus_exact_table_4")
        out.setdefault(
            "cite",
            out.get("cite") or "IS 875 (Part 3) : 2015 Table 4 (corpus exact_table 4)",
        )
        A = float(A_m2)
        ka_decl, basis = _declared_ka(corpus_hit, A, direction)
        out["A_m2"] = A
        out["resolved_via"] = "corpus"
        if direction:
            out["direction"] = str(direction).upper()
        if ka_decl is None:
            out.update(found=False, Ka=None, resolved_via="refused",
                       cite="corpus Ka hit without a usable Ka for A = %.2f m2 (%s)" % (A, out.get("cite")))
            return out
        out["Ka_declared"] = ka_decl
        out["Ka_basis_declared"] = basis
        out["Ka"] = ka_decl
        t4 = ka_for_area_m2(A)                     # Table 4 transcription, used here as the area check
        if t4.get("found") and t4.get("Ka") is not None:
            chk = {"A_m2": A, "Ka_table4": t4["Ka"], "Ka_declared": ka_decl, "ok": ka_decl >= t4["Ka"] - KA_AREA_CHECK_TOL,
                   "cite": "IS 875 (Part 3):2015 7.2.2.1 / Table 4 at the tributary area of this direction"}
            out["area_check"] = chk
            if not chk["ok"]:
                out["Ka"] = t4["Ka"]
                out["resolved_via"] = "table4_area_check"
                out["note"] = ("declared corpus Ka %.4f (%s) is below Table 4 Ka %.4f for A = %.2f m2%s -- "
                               "unconservative here; the Table 4 value at this area is used (RR-BUG-6)"
                               % (ka_decl, basis, t4["Ka"], A, (" (wind along %s)" % str(direction).upper())
                                  if direction else ""))
        return out
    fb = ka_for_area_m2(A_m2, allow_fallback=allow_fallback)
    fb["resolved_via"] = "fallback" if fb.get("found") else "refused"
    fb["corpus_found"] = False
    if direction:
        fb["direction"] = str(direction).upper()
    return fb


EOR_CPE_OK_SOURCES = frozenset({
    "eor", "eor_documented", "eor_explicit", "wind_tunnel", "specialist_literature", "documented",
})
EOR_CPE_REFUSED = frozenset({"assumed", "assumption", "silent", "invented", "guess", "placeholder", "todo", "tbd"})


def eor_cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float, eor_cpe) -> dict:
    """H15: EOR Cpe input path for geometry outside IS 875-3 Table 5 (e.g. l/w >= 4, h/w >= 6 off the printed
    plan ratios).  The Table 5 NOTE leaves such buildings to the engineer; the engine never extrapolates.  Accepts
    ``{"Cpe": {"A":..,"B":..,"C":..,"D":..}, "source": "eor_documented"|"wind_tunnel"|..., "cite"|"basis": str,
    "verify": True}`` and returns a found:true record flagged VERIFY; anything less is found:false with the missing
    inputs listed."""
    rec = dict(eor_cpe or {})
    cpe = rec.get("Cpe") if isinstance(rec.get("Cpe"), dict) else rec.get("value")
    src = str(rec.get("source") or "").strip().lower().replace(" ", "_").replace("-", "_")
    cite = rec.get("cite") or rec.get("basis")
    missing = []
    if not (isinstance(cpe, dict) and all(isinstance(cpe.get(f), (int, float)) for f in ("A", "B", "C", "D"))):
        missing.append("Cpe {A, B, C, D} (numbers)")
    if src not in EOR_CPE_OK_SOURCES or src in EOR_CPE_REFUSED:
        missing.append("source in {%s}" % ", ".join(sorted(EOR_CPE_OK_SOURCES)))
    if not cite:
        missing.append("cite / basis")
    if rec.get("verify") is not True:
        missing.append("verify: True")
    base = {"h_over_w": float(h_over_w), "l_over_w": float(l_over_w), "theta_deg": float(theta_deg)}
    if missing:
        return dict(base, found=False, Cpe=None, source="refused_eor", resolved_via="refused",
                    required_inputs=missing,
                    cite="IS 875 (Part 3):2015 Table 5 has no row for this geometry -- an EOR Cpe record "
                         "{Cpe, source, cite, verify: True} is required (do not reshape the building to fit the table)")
    return dict(base, found=True, Cpe={f: float(cpe[f]) for f in ("A", "B", "C", "D")},
                Cpe_local=rec.get("Cpe_local"), source=src, resolved_via="eor", verify=True, cite=str(cite),
                note="Geometry outside IS 875-3 Table 5 bands: EOR-declared Cpe (VERIFY before issue)")


def resolve_cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float = 0.0,
                      corpus_hit=None, *, allow_fallback: bool = True, eor_cpe=None) -> dict:
    """Prefer corpus exact_table 5; demote in-repo wall Cpe to fallback when corpus found:false.
    H15: when the geometry is outside the printed table (fallback refused_band) an ``eor_cpe`` record
    (see eor_cpe_walls) is used instead of refusing -- never an extrapolated table value."""
    if _corpus_found(corpus_hit):
        out = dict(corpus_hit)
        out.setdefault("found", True)
        out.setdefault("source", "corpus_exact_table_5")
        out.setdefault(
            "cite",
            out.get("cite") or "IS 875 (Part 3) : 2015 Table 5 (corpus exact_table 5)",
        )
        out["h_over_w"] = float(h_over_w)
        out["l_over_w"] = float(l_over_w)
        out["theta_deg"] = float(theta_deg)
        out["resolved_via"] = "corpus"
        return out
    if not allow_fallback:
        return {
            "found": False,
            "Cpe": None,
            "cite": "Table 5 fallback disabled — retrieve exact_table 5 from corpus",
            "source": "refused",
            "resolved_via": "refused",
            "corpus_found": False,
        }
    fb = cpe_walls(h_over_w, l_over_w, theta_deg)
    if not fb.get("found") and fb.get("source") == "refused_band" and eor_cpe is not None:
        eo = eor_cpe_walls(h_over_w, l_over_w, theta_deg, eor_cpe)
        eo["corpus_found"] = False
        return eo
    fb["resolved_via"] = "fallback" if fb.get("found") else fb.get("source", "refused")
    fb["corpus_found"] = False
    return fb


def override_policy() -> dict:
    """Agent-facing policy summary for load_plan / wind RAG (corpus-prefer)."""
    return {
        "Ka_Table_4": {
            "prefer": "corpus exact_table 4 (reliable as of 2026-09-19 QFM)",
            "fallback": (
                "india_wind_tables.ka_for_area_m2 — breakpoints ≤10→1.0, 25→0.9, ≥100→0.8 "
                "only when corpus found:false"
            ),
            "never": "invent Ka outside Table 4 / interpolation note",
        },
        "Cpe_Table_5_walls": {
            "prefer": "corpus exact_table 5 (HIT after 2026-09-19 QFM OCR reingest)",
            "fallback": (
                "india_wind_tables.cpe_walls / TABLE_5_CPE_WALLS — only when corpus found:false"
            ),
            "do_not_use": "legacy Docling OCR cells for Table 5 design Cpe (if they reappear)",
            "never": "invent Cpe outside corpus / shipped fallback bands; found:false if outside",
        },
        "other_wind_tables_corpus_live": list(CORPUS_LIVE_WIND_TABLES),
        "qfm_note": QFM_OCR_NOTE,
        "corpus_when_clean": (
            "When RAG returns found:true for Table 4/5 (and 6/7/11/18/21/22/29 as needed), "
            "corpus is authoritative; in-repo tables are fallback only."
        ),
    }


# --- k4 Importance Factor for Cyclonic Region (§6.3.4) ---------------------
# Corpus OCR often garbles the numeric k4 table. Allow EOR-documented values
# with an explicit cite (CFS-style eor_documented) — never invent silently.

K4_OK_SOURCES = frozenset({
    "corpus", "corpus_exact_table", "exact_table", "rag",
    "eor_documented", "eor", "documented", "explicit", "eor_explicit",
    "is15498", "printed_table", "pdf",
})
K4_REFUSED_SOURCES = frozenset({
    "assumed", "assumption", "silent", "silent_default", "invented",
    "placeholder", "todo", "tbd", "guess",
})


def resolve_k4(corpus_hit=None, *, eor_k4=None, eor_cite=None, eor_source=None,
               structure_class=None):
    """Resolve IS 875 Part 3 §6.3.4 k4.

    Prefer corpus exact digits when found:true. When OCR/digits are found:false,
    accept an EOR-documented k4 + cite (source in K4_OK_SOURCES, not invented).
    Never invent a default k4.
    """
    if _corpus_found(corpus_hit) and corpus_hit.get("k4") is not None:
        out = dict(corpus_hit)
        out.setdefault("found", True)
        out.setdefault("source", "corpus")
        out["resolved_via"] = "corpus"
        out.setdefault(
            "cite",
            out.get("cite") or "IS 875 (Part 3):2015 §6.3.4 (corpus)",
        )
        return out

    # Explicit EOR / documented path (allowed when corpus digits miss)
    k4_val = eor_k4
    src = (eor_source or "").strip().lower().replace(" ", "_").replace("-", "_")
    cite = eor_cite
    if isinstance(corpus_hit, dict) and corpus_hit.get("found") is False:
        # allow hit to carry eor fields
        k4_val = k4_val if k4_val is not None else corpus_hit.get("k4") or corpus_hit.get("eor_k4")
        src = src or str(corpus_hit.get("source") or corpus_hit.get("k4_source") or "").strip().lower().replace(" ", "_")
        cite = cite or corpus_hit.get("cite") or corpus_hit.get("eor_cite")

    if k4_val is not None and src in K4_OK_SOURCES and cite:
        return {
            "found": True,  # resolved for design use — provenance is EOR/documented, not OCR digits
            "k4": float(k4_val),
            "corpus_digits_found": False,
            "source": src,
            "resolved_via": "eor_documented" if "eor" in src or src == "documented" else src,
            "cite": str(cite),
            "structure_class": structure_class,
            "note": (
                "k4 from EOR/documented path because corpus §6.3.4 numeric digits "
                "were found:false (OCR). Not invented — cite required. Confirm against "
                "printed IS 875 P3 / IS 15498 before sealing."
            ),
            "policy": "eor_documented_ok_when_ocr_miss",
        }

    refused = []
    if k4_val is None:
        refused.append("k4 value")
    if src not in K4_OK_SOURCES:
        refused.append("k4_source in {%s}" % ", ".join(sorted(K4_OK_SOURCES)))
    if not cite:
        refused.append("k4_cite (printed clause / IS 15498 / EOR note)")
    return {
        "found": False,
        "k4": None,
        "corpus_digits_found": False,
        "source": src or None,
        "resolved_via": "refused",
        "required_inputs": refused,
        "cite": "IS 875 (Part 3):2015 §6.3.4 — retrieve digits or supply eor_documented k4+cite",
        "note": (
            "Do not invent k4. When OCR digits are found:false, set "
            "k4_source='eor_documented' with k4_cite (CFS-style provenance)."
        ),
    }


# =====================================================================================
# WP1.11 -- IS 875 (Part 3):2015 wind rules in code (values read from the licensed PDF)
# =====================================================================================
K4_BY_CLASS = {"post_cyclone": 1.30, "industrial": 1.15, "other": 1.00}          # 6.3.4 (p.9)
K4_CITE = ("IS 875 (Part 3):2015 6.3.4: 60 km coastal belt (east coast and Gujarat): post-cyclone "
           "importance 1.30, industrial 1.15, all other 1.00")
KD_CITE = "IS 875 (Part 3):2015 7.2.1: 'For the cyclone affected regions also the factor Kd shall be taken as 1.0'"
Z0 = {1: 0.002, 2: 0.02, 3: 0.2, 4: 2.0}                                            # 6.3.2.1 roughness heights (m)
DAMPING_TABLE36 = {"welded_steel": 0.010, "bolted_steel": 0.020, "rcc": 0.020, "prestressed": 0.016}

# Table 6 (7.3.3.2) pitched roofs, overall coefficients: {h/w band: {alpha: (EF, GH, EG, FH)}}
# read from the PDF p.16 scan (400 dpi); H15 (HR-E-25): the mid band (1/2 < h/w <= 3/2) FH cells at 30/45/60 deg are
# -0.8 (corpus IS_875_Part_3_2015/markdown/pages_recovered/page_016.md, settled by the 400-ppi 2015 scan and the
# 1987 print); the bottom band rows 30/40/50/60 (-1.0/-0.5/-0.8/-0.7, -0.2/-0.5/-0.8/-0.7, +0.2/-0.5/-0.8/-0.7,
# +0.5/-0.5/-0.8/-0.7) were re-read from a 300 dpi crop on 2026-09-20 (HR-INTEGRATE) and match the values below.
TABLE_6_CPE_PITCHED = {
    "le_0.5": {0: (-0.8, -0.4, -0.8, -0.4), 5: (-0.9, -0.4, -0.8, -0.4), 10: (-1.2, -0.4, -0.8, -0.6),
               20: (-0.4, -0.4, -0.7, -0.6), 30: (0.0, -0.4, -0.7, -0.6), 45: (0.3, -0.5, -0.7, -0.6),
               60: (0.7, -0.6, -0.7, -0.6)},
    "0.5_1.5": {0: (-0.8, -0.6, -1.0, -0.6), 5: (-0.9, -0.6, -0.9, -0.6), 10: (-1.1, -0.6, -0.8, -0.6),
                20: (-0.7, -0.5, -0.8, -0.6), 30: (-0.2, -0.5, -0.8, -0.8), 45: (0.2, -0.5, -0.8, -0.8),
                60: (0.6, -0.5, -0.8, -0.8)},
    "1.5_6": {0: (-0.7, -0.6, -0.9, -0.7), 5: (-0.7, -0.6, -0.8, -0.8), 10: (-0.7, -0.6, -0.8, -0.8),
              20: (-0.8, -0.6, -0.8, -0.8), 30: (-1.0, -0.5, -0.8, -0.7), 40: (-0.2, -0.5, -0.8, -0.7),
              50: (0.2, -0.5, -0.8, -0.7), 60: (0.5, -0.5, -0.8, -0.7)},
}


WIND_STRUCTURE_CLASSES = ("post_cyclone", "industrial", "other")


def k4_required(cyclone_belt, structure_class="other"):
    """6.3.4 + decision D10: k4 and Kd come from the same cyclone_belt flag.
    H21: inside the belt a missing class is not defaulted to 'other' (k4 1.00) -- found:false, k4 None."""
    if not cyclone_belt:
        return {"k4": 1.0, "Kd": None, "cite": K4_CITE + " (outside the belt: k4 = 1.0)"}
    if structure_class is None or str(structure_class).strip() == "":
        return {"found": False, "k4": None, "Kd": 1.0, "class": None,
                "cite": K4_CITE + "; wind_structure_class (post_cyclone | industrial | other) must be declared"}
    cls = str(structure_class).lower()
    cls = "post_cyclone" if any(t in cls for t in ("post", "shelter", "hospital", "school", "tower", "emergency")) \
        else ("industrial" if "industr" in cls else "other")
    return {"k4": K4_BY_CLASS[cls], "Kd": 1.0, "class": cls, "cite": K4_CITE + "; " + KD_CITE}


def roof_cpe_pitched(h_over_w, alpha_deg):
    """Table 6 overall Cpe (EF, GH at theta 0; EG, FH at theta 90), linear in roof angle."""
    band = "le_0.5" if h_over_w <= 0.5 else ("0.5_1.5" if h_over_w <= 1.5 else "1.5_6")
    if h_over_w >= 6:
        return {"found": False, "note": "h/w >= 6 outside Table 6"}
    tab = TABLE_6_CPE_PITCHED[band]
    ks = sorted(tab)
    a = max(min(float(alpha_deg), ks[-1]), ks[0])
    lo = max(k for k in ks if k <= a); hi = min(k for k in ks if k >= a)
    t = 0.0 if hi == lo else (a - lo) / (hi - lo)
    vals = tuple(tab[lo][i] + t * (tab[hi][i] - tab[lo][i]) for i in range(4))
    return {"found": True, "band": band, "alpha_deg": a, "EF": vals[0], "GH": vals[1], "EG": vals[2], "FH": vals[3],
            "cite": "IS 875 (Part 3):2015 Table 6 (7.3.3.2), linear interpolation on roof angle"}


def cpi_from_openings(opening_ratio):
    """7.3.2.1 / 7.3.2.2: <= 5 % -> +-0.2; 5-20 % -> +-0.5; > 20 % -> +-0.7."""
    r = float(opening_ratio)
    v = 0.2 if r <= 0.05 else (0.5 if r <= 0.20 else 0.7)
    return {"Cpi": v, "cite": "IS 875 (Part 3):2015 7.3.2.%s" % ("1" if r <= 0.05 else "2"),
            "opening_ratio": r}


def k2_hourly(z_m, terrain):
    """6.4: k2,i = 0.1423 ln(z/z0,i) (z0,i)^0.0706."""
    import math
    z0 = Z0[int(terrain)]
    return 0.1423 * math.log(max(float(z_m), z0 * 1.0001) / z0) * z0 ** 0.0706


def turbulence_intensity(z_m, terrain):
    """6.5: Iz,1 = 0.3507 - 0.0535 log10(z/z0,1); Iz,4 = 0.466 - 0.1358 log10(z/z0,4);
    Iz,2 = Iz,1 + (Iz,4 - Iz,1)/7; Iz,3 = Iz,1 + 3(Iz,4 - Iz,1)/7."""
    import math
    I1 = 0.3507 - 0.0535 * math.log10(float(z_m) / Z0[1])
    I4 = 0.466 - 0.1358 * math.log10(float(z_m) / Z0[4])
    return {1: I1, 2: I1 + (I4 - I1) / 7.0, 3: I1 + 3.0 * (I4 - I1) / 7.0, 4: I4}[int(terrain)]


def gust_factor_10_2(h_m, b_m, fa_hz, terrain, Vb, k1=1.0, k3=1.0, k4=1.0, beta=0.020, s_m=0.0, b0h_m=None):
    """IS 875 (Part 3):2015 10.2 along-wind Gust Factor (PDF pp.47-48):
    G = 1 + r sqrt( gv^2 Bs (1+phi)^2 + Hs gR^2 S E / beta ),  r = 2 Ih,i,
    Bs = 1/(1 + sqrt(0.26 (h-s)^2 + 0.46 bsh^2)/Lh), Lh = 85 (h/10)^0.25 (cat 1-3) / 70 (cat 4),
    phi = gv Ih,i sqrt(Bs)/2, Hs = 1 + (s/h)^2, S = 1/((1 + 3.5 fa h/Vh,d)(1 + 4 fa b0h/Vh,d)),
    E = pi N/(1 + 70.8 N^2)^(5/6), N = fa Lh/Vh,d, gR = sqrt(2 ln(3600 fa)), gv 3.0 (cat 1-2) / 4.0."""
    import math
    t = int(terrain)
    h, b = float(h_m), float(b_m)
    b0h = float(b0h_m if b0h_m is not None else b)
    Ih = turbulence_intensity(h, t)
    r = 2.0 * Ih
    gv = 3.0 if t in (1, 2) else 4.0
    Lh = (85.0 if t in (1, 2, 3) else 70.0) * (h / 10.0) ** 0.25
    Bs = 1.0 / (1.0 + math.sqrt(0.26 * (h - s_m) ** 2 + 0.46 * b ** 2) / Lh)
    phi = gv * Ih * math.sqrt(Bs) / 2.0
    Hs = 1.0 + (float(s_m) / h) ** 2
    Vhd = float(Vb) * k1 * k2_hourly(h, t) * k3 * k4
    S = 1.0 / ((1.0 + 3.5 * fa_hz * h / Vhd) * (1.0 + 4.0 * fa_hz * b0h / Vhd))
    N = fa_hz * Lh / Vhd
    E = math.pi * N / (1.0 + 70.8 * N * N) ** (5.0 / 6.0)
    gR = math.sqrt(2.0 * math.log(3600.0 * fa_hz))
    G = 1.0 + r * math.sqrt(gv ** 2 * Bs * (1.0 + phi) ** 2 + Hs * gR ** 2 * S * E / float(beta))
    return {"G": G, "r": r, "Ih": Ih, "gv": gv, "Lh": Lh, "Bs": Bs, "phi": phi, "Hs": Hs, "Vh_d": Vhd,
            "S": S, "N": N, "E": E, "gR": gR, "beta": beta,
            "cite": "IS 875 (Part 3):2015 10.2 (Gust Factor method), hourly mean speed 6.4, turbulence 6.5, Table 36"}


def along_wind_story_forces(heights_m, b_m, Cf, fa_hz, terrain, Vb, k1=1.0, k3=1.0, k4=1.0, beta=0.020):
    """Fz = Cf Az pd(hourly) G per level (10.2), N; pd = 0.6 Vz,d^2 with Vz,d = Vb k1 k2,i k3 k4."""
    z = 0.0; zs = []
    for h in heights_m:
        z += float(h); zs.append(z)
    H = zs[-1]
    g = gust_factor_10_2(H, b_m, fa_hz, terrain, Vb, k1, k3, k4, beta)
    F = []
    for i, zi in enumerate(zs):
        trib = (float(heights_m[i]) / 2.0 + (float(heights_m[i + 1]) / 2.0 if i + 1 < len(zs) else 0.0))
        Vzd = float(Vb) * k1 * k2_hourly(zi, terrain) * k3 * k4
        F.append(Cf * b_m * trib * 0.6 * Vzd ** 2 * g["G"])
    return {"F_N": F, "VB_N": sum(F), "gust": g}


# ---------------------------------------------------------------------------------------------------------------------
# X05 (HR-B-09, HR-C-12): IS 875 (Part 3):2015 10.3 across-wind load case.  Corpus text (IS_875_Part_3_2015.md, 10.3,
# pdf pp. 50-51), legible parts quoted:
#   "The across wind design peak base bending moment M c for enclosed buildings and towers shall be determined as
#    follows: M c [=] 0.5 g h p h b h^2 (1.06 - 0.06 k) sqrt(pi C fs / beta)"
#   "g h = a peak factor, = ( ) 2ln 36 00 c f in cross wind direction" (formula line OCR-broken; the legible fragments
#    '2ln', '3600', 'fc' are the 10.2 peak factor form gR = sqrt(2 ln(3600 fa)), read here with fc)
#   "h p = hourly mean wind pressure at height h, in Pa; b = the breadth of the structure normal to the wind, in m;
#    h = the height of the structure, in m; k = a mode shape power exponent ... Psi(z) = (z/h)^k;
#    f c = first mode natural frequency of the building/structure in across wind direction, in Hz."
#   "The across wind load distribution on the building/structure can be obtained from Mc using linear distribution
#    of loads as given below: F z,c = (3 M c / h^2)(z / h) where F z,c = across wind load per unit height at height z."
#   "C fs = across wind force spectrum coefficient generalized for a linear mode (see Fig. 10 and Fig. 11).
#    beta = damping coefficient of the building/structure (see Table 36)."
#   10.4 "The along wind and across wind loads have to be applied simultaneously on the building/structure during
#    design."
# Fig. 10 / Fig. 11 are images (not in the corpus text): Cfs is an EOR reading with its source (ruling R10).
# ---------------------------------------------------------------------------------------------------------------------
ACROSS_WIND_CITE = ("IS 875 (Part 3):2015 10.3: Mc = 0.5 gh ph b h^2 (1.06 - 0.06 k) sqrt(pi Cfs / beta); "
                    "Fz,c = (3 Mc / h^2)(z / h) per unit height; 10.4: along and across wind applied simultaneously")
ACROSS_WIND_GH_BASIS = ("gh = sqrt(2 ln(3600 fc)): the 10.3 gh line is OCR-broken in the corpus (legible: '2ln', "
                        "'36 00', 'c f'); read with the legible 10.2 form gR = sqrt(2 ln(3600 fa))")


def _num_ok(v):
    import math
    try:
        return v is not None and not isinstance(v, bool) and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def across_wind_peak_factor(fc_hz):
    """10.3 gh = sqrt(2 ln(3600 fc)) (see ACROSS_WIND_GH_BASIS)."""
    import math
    return math.sqrt(2.0 * math.log(3600.0 * float(fc_hz)))


def across_wind_Mc(*, Cfs, beta, fc_hz, b_m, h_m, k, ph_Pa, gh=None):
    """IS 875-3 10.3 across-wind design peak base bending moment (kN m):
    Mc = 0.5 gh ph b h^2 (1.06 - 0.06 k) sqrt(pi Cfs / beta), ph in Pa, b and h in m."""
    import math
    g = float(gh) if gh is not None else across_wind_peak_factor(fc_hz)
    Mc_Nm = 0.5 * g * float(ph_Pa) * float(b_m) * float(h_m) ** 2 * (1.06 - 0.06 * float(k)) * \
        math.sqrt(math.pi * float(Cfs) / float(beta))
    return {"Mc_kNm": Mc_Nm / 1000.0, "gh": g, "gh_basis": ("declared" if gh is not None else ACROSS_WIND_GH_BASIS),
            "cite": ACROSS_WIND_CITE}


def across_wind_level_forces(z_levels_m, Mc_kNm, h_m=None):
    """10.3 Fz,c = (3 Mc / h^2)(z / h) (kN/m) lumped to the floor levels by linear (statically equivalent) shape
    functions over each storey: the level forces reproduce the 10.3 overturning moment exactly (sum F_k z_k = Mc)
    and the base shear 1.5 Mc / h less the share of the lowest storey that goes straight into the supports.

    z_levels_m: elevations of levels 1..NF above the base (m).  Returns {F_kN: [..], F_ground_kN, V_kN (applied),
    V_total_kN (= 1.5 Mc / h), M_base_kNm (= sum F z), h_m, w_top_kN_per_m}."""
    zs = [float(z) for z in z_levels_m]
    h = float(h_m) if h_m is not None else zs[-1]
    a = 3.0 * float(Mc_kNm) / h ** 3                     # w(z) = a z  (kN/m)
    F = [0.0] * len(zs)
    F0 = 0.0
    zprev = 0.0
    for i, z1 in enumerate(zs):
        L = z1 - zprev
        if L <= 0:
            zprev = z1
            continue
        w0, w1 = a * zprev, a * z1
        bot = L * (2.0 * w0 + w1) / 6.0
        top = L * (w0 + 2.0 * w1) / 6.0
        if i == 0:
            F0 += bot
        else:
            F[i - 1] += bot
        F[i] += top
        zprev = z1
    return {"F_kN": F, "F_ground_kN": F0, "V_kN": sum(F), "V_total_kN": 1.5 * float(Mc_kNm) / h,
            "M_base_kNm": sum(f * z for f, z in zip(F, zs)), "h_m": h, "w_top_kN_per_m": a * h,
            "cite": ACROSS_WIND_CITE + "; linear shape-function lumping to the floor levels"}


def resolve_across_wind(aw, ws=None, *, h_m=None, b_m=None):
    """Across-wind record -> {found, reason, by_dir: {'X': {...}, 'Y': {...}}}; the keys are the ALONG-wind
    direction (the W_<d> pattern the across-wind load accompanies; the across-wind force acts normal to it).

    Accepted records (ruling R10, X05):
      * {found: True, Mc_kNm: <number>, cite}                     -- both directions
      * {found: True, Mc_kNm_X: <number>, Mc_kNm_Y: <number>}      -- per along-wind direction (override Mc_kNm)
      * {eor: {value, source, cite}}                               -- EOR Mc, both directions
      * {Cfs: {value, source, cite}, k, beta, fc_hz, ph_Pa | (Vb_mps, terrain_category[, k1, k3, k4]), b_m, h_m[, gh]}
        with any field overridable per along-wind direction in aw['X'] / aw['Y'] (b and fc differ by direction):
        Mc computed from the 10.3 formula; Cfs is an EOR reading of Fig. 10 / 11 with its source and cite.
    h_m / b_m (dict {'X': b normal to wind along X, 'Y': ...}) are defaults from the model when not in the record."""
    out = {"found": False, "by_dir": {}, "reason": None}
    if not isinstance(aw, dict) or not aw:
        out["reason"] = "wind_summary.across_wind missing"
        return out
    ws = ws or {}
    why = []
    for d in ("X", "Y"):
        sub = aw.get(d) if isinstance(aw.get(d), dict) else {}
        rec = dict(aw)
        rec.pop("X", None), rec.pop("Y", None)
        rec.update(sub)
        cfs = rec.get("Cfs")
        cfs_why = None
        if cfs is not None:
            cfs_d = cfs if isinstance(cfs, dict) else {"value": cfs, "source": rec.get("Cfs_source"),
                                                          "cite": rec.get("Cfs_cite")}
            miss = []
            if not _num_ok(cfs_d.get("value")):
                miss.append("Cfs.value")
            for kk in ("source", "cite"):
                if not str(cfs_d.get(kk) or "").strip():
                    miss.append("Cfs.%s" % kk)
            inp = {}
            for kk in ("k", "beta", "fc_hz"):
                if _num_ok(rec.get(kk)):
                    inp[kk] = float(rec[kk])
                else:
                    miss.append(kk)
            hh = rec.get("h_m", h_m)
            bb = rec.get("b_m", (b_m or {}).get(d) if isinstance(b_m, dict) else b_m)
            for kk, v in (("h_m", hh), ("b_m", bb)):
                if _num_ok(v):
                    inp[kk] = float(v)
                else:
                    miss.append(kk)
            ph = rec.get("ph_Pa")
            ph_basis = "declared ph_Pa"
            if not _num_ok(ph):
                Vb = rec.get("Vb_mps", ws.get("Vb_mps"))
                tc = rec.get("terrain_category", ws.get("terrain_category"))
                if _num_ok(Vb) and tc is not None and "h_m" in inp:
                    try:
                        k1 = float(rec.get("k1", ws.get("k1", 1.0)) or 1.0)
                        k3 = float(rec.get("k3", ws.get("k3", 1.0)) or 1.0)
                        k4 = float(rec.get("k4", ws.get("k4", 1.0)) or 1.0)
                        Vh = float(Vb) * k1 * k2_hourly(inp["h_m"], int(str(tc).strip()[-1])) * k3 * k4
                        ph = 0.6 * Vh ** 2
                        ph_basis = ("ph = 0.6 Vh,d^2, hourly mean Vh,d = Vb k1 k2,i(h) k3 k4 = %.2f m/s (6.4, 10.2)"
                                    % Vh)
                    except (TypeError, ValueError, KeyError):
                        ph = None
            if _num_ok(ph):
                inp["ph_Pa"] = float(ph)
            else:
                miss.append("ph_Pa (or Vb_mps + terrain_category)")
            if miss:
                cfs_why = "Cfs path incomplete (%s)" % ", ".join(miss)
            else:
                cfs_why = None
        if cfs is not None and cfs_why is None:
            gh = rec.get("gh") if _num_ok(rec.get("gh")) else None
            m = across_wind_Mc(Cfs=float(cfs_d["value"]), gh=gh, **inp)
            out["by_dir"][d] = {"Mc_kNm": m["Mc_kNm"], "found": True, "basis": "computed (10.3 formula, EOR Cfs)",
                                "source": "engine: IS 875-3 10.3 Mc from Cfs = %g (%s)" % (float(cfs_d["value"]),
                                                                                         cfs_d["source"]),
                                "cite": m["cite"] + "; Cfs: " + str(cfs_d["cite"]),
                                "Cfs": {"value": float(cfs_d["value"]), "source": cfs_d["source"],
                                        "cite": cfs_d["cite"]},
                                "gh": m["gh"], "gh_basis": m["gh_basis"], "ph_basis": ph_basis, "inputs": inp}
            continue
        v = rec.get("Mc_kNm_" + d, rec.get("Mc_kNm"))
        if rec.get("found") is True and _num_ok(v):
            out["by_dir"][d] = {"Mc_kNm": float(v), "found": True, "basis": "declared (found: true)",
                                "source": str(rec.get("source") or "wind_summary.across_wind"),
                                "cite": str(rec.get("cite") or ACROSS_WIND_CITE)}
            continue
        eor = rec.get("eor") or rec.get("EOR")
        if isinstance(eor, dict):
            ev = eor.get("value_" + d, eor.get("value"))
            if _num_ok(ev) and str(eor.get("source") or "").strip() and str(eor.get("cite") or "").strip():
                out["by_dir"][d] = {"Mc_kNm": float(ev), "found": True, "basis": "EOR record",
                                    "source": str(eor["source"]), "cite": str(eor["cite"])}
                continue
        why.append("%s: no numeric Mc (found %r, no EOR {value, source, cite}, %s)"
                   % (d, rec.get("found"), cfs_why or "no Cfs record"))
    out["found"] = set(out["by_dir"]) == {"X", "Y"}
    out["reason"] = "; ".join(why) or None
    return out


def dynamic_wind_required(h_m, b_min_m, f1_hz):
    """9.1: h / min lateral dimension > about 5.0, or first-mode frequency < 1.0 Hz."""
    why = []
    if b_min_m and float(h_m) / float(b_min_m) > 5.0:
        why.append("h/b = %.2f > 5 (9.1(a))" % (float(h_m) / float(b_min_m)))
    if f1_hz is not None and f1_hz < 1.0:
        why.append("f1 = %.2f Hz < 1.0 Hz (9.1(b))" % f1_hz)
    return bool(why), why


def wind_findings(cfg) -> list:
    """Preflight wind rules (WP1.11 items 1, 2, 3, 7, 8)."""
    out = []
    plan = cfg.get("load_plan") or {}
    ws = plan.get("wind_summary") or {}
    say = lambda s, m: out.append((s, m))
    # H47 / ruling R5: the seismic zone takes the same site-proxy policy as Vb (IS 1893 Annex E town list)
    ss = plan.get("seismic_summary") or {}
    zsrc = str(ss.get("zone_source") or "").lower()
    if zsrc == "site_proxy":
        out.extend(site_proxy_findings(ss, quantity="zone", cfg=cfg))
    elif "proxy" in zsrc or "nearest" in zsrc:
        say("ERROR", "seismic zone from a proxy / nearest town is not permitted: read IS 1893 Fig. 1 at the site "
                     "(zone_source='derived_from_map' with lat/long), or -- only when Annex E has no row for the "
                     "town -- zone_source='site_proxy' with proxy_town, distance_km, basis, verify: True (ruling R5)")
    if plan.get("no_wind") or not ws:
        return out
    cb = ws.get("cyclone_belt", cfg.get("cyclone_belt"))
    if cb is None:
        say("ERROR", "wind_summary.cyclone_belt (true/false, with cite) must be declared -- it sets Kd = 1.0 "
                     "(7.2.1) and k4 (6.3.4) together (decision D10)")
    k4 = ws.get("k4"); Kd = ws.get("Kd")
    if k4 is not None and float(k4) not in (1.0, 1.15, 1.30):
        say("ERROR", "k4 = %s not in {1.0, 1.15, 1.30} (IS 875-3 6.3.4)" % k4)
    if cb is True:
        if Kd is not None and abs(float(Kd) - 1.0) > 1e-9:
            say("ERROR", "cyclone_belt: Kd = %s but %s" % (Kd, KD_CITE))
        # H21 (E7): the 6.3.4 class is an explicit input inside the belt -- no silent 'other' (k4 1.00)
        wsc = ws.get("structure_class") or cfg.get("wind_structure_class")
        wsc_n = str(wsc or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not wsc_n:
            say("ERROR", "cyclone_belt: declare wind_structure_class in {post_cyclone, industrial, other} "
                         "(IS 875-3 6.3.4: post-cyclone importance 1.30, industrial 1.15, all other 1.00); "
                         "k4 is not defaulted")
        elif wsc_n not in WIND_STRUCTURE_CLASSES:
            say("ERROR", "cyclone_belt: wind_structure_class %r must be one of post_cyclone | industrial | other "
                         "(IS 875-3 6.3.4)" % (wsc,))
        else:
            req = {"k4": K4_BY_CLASS[wsc_n], "class": wsc_n}
            if k4 is not None and abs(float(k4) - req["k4"]) > 1e-9:
                say("ERROR", "cyclone_belt, class %s: k4 = %s but 6.3.4 gives %.2f" % (req["class"], k4, req["k4"]))
    elif cb is False and k4 is not None and float(k4) != 1.0:
        say("ERROR", "k4 = %s > 1.0 but cyclone_belt is false (k4 applies only in the 60 km belt, 6.3.4)" % k4)
    pz, pd = ws.get("pz_kNm2"), ws.get("pd_kNm2")
    if pz is not None and pd is not None and float(pd) < 0.70 * float(pz) - 1e-9:
        say("ERROR", "pd = %.4f < 0.70 pz = %.4f (IS 875-3 7.2: pd shall not be less than 0.70 pz)" % (pd, 0.7 * pz))
    if ws.get("Ka") is not None and ws.get("Ka_basis") not in ("frame_tributary", "element_tributary"):
        say("ERROR", "wind_summary.Ka_basis must state the 7.2.2.1 tributary area ('frame_tributary' = frame "
                     "spacing x panel dimension for frames, 'element_tributary' for purlins/girts)")
    if ws.get("Ka") is not None and ws.get("Ka_area_m2") is not None:
        ka = ka_for_area_m2(float(ws["Ka_area_m2"])).get("Ka")
        if ka is not None and abs(float(ws["Ka"]) - ka) > 0.005:
            say("ERROR", "Ka = %s but Table 4 gives %.3f for A = %s m2" % (ws["Ka"], ka, ws["Ka_area_m2"]))
    # RR-BUG-6: per-direction Ka (Ka_X / Ka_area_X_m2, Ka_Y / Ka_area_Y_m2) -- each direction against its own area;
    # a Ka below Table 4 at that direction's area is unconservative
    for d in ("X", "Y"):
        kd, ad = ws.get("Ka_%s" % d), ws.get("Ka_area_%s_m2" % d)
        if kd is None or ad is None:
            continue
        ka = ka_for_area_m2(float(ad)).get("Ka")
        if ka is not None and float(kd) < ka - 0.005:
            say("ERROR", "Ka_%s = %s but Table 4 gives %.3f for the wind-along-%s tributary area A = %s m2 "
                         "(7.2.2.1; a lower Ka is unconservative)" % (d, kd, ka, d, ad))
    # H21 (HR-A-12): IS 875-3 Table 1 iv) -- hospitals and other important buildings have a 100-year life, k1 > 1.0
    if _table1_iv_building(cfg, ws) and ws.get("k1") is not None and abs(float(ws["k1"]) - 1.0) < 1e-9:
        say("WARN", "k1 = 1.0 declared for a hospital / important building: IS 875-3 Table 1 iv) (important "
                    "buildings such as hospitals, communication buildings, power plant structures; 100 yr) gives "
                    "k1 = 1.05-1.08 by basic wind speed -- confirm the Table 1 class (6.3.1)")
    src = str(ws.get("Vb_source") or "").lower()
    if src == "site_proxy":
        for sev, msg in site_proxy_findings(ws, quantity="Vb", cfg=cfg):
            say(sev, msg)
    elif "proxy" in src or "nearest" in src:
        say("ERROR", "Vb from a proxy city is not permitted: read IS 875-3 Fig. 1 at the site coordinates and "
                     "record Vb_source='derived_from_map' with lat/long (WP1.11-8), or -- only when Annex A has no "
                     "row for the town -- Vb_source='site_proxy' with proxy_town, distance_km, basis, verify: True "
                     "(ruling R5)")
    if src == "derived_from_map" and not (ws.get("lat") and ws.get("long")):
        say("ERROR", "Vb_source derived_from_map needs the site lat/long")
    slope = cfg.get("terrain_upwind_slope_deg") or ws.get("upwind_slope_deg")
    if slope is not None and float(slope) > 3.0 and not ws.get("k3_basis"):
        say("ERROR", "upwind slope %.1f deg > 3 deg: k3 per 6.3.3 / Annex C required (k3_basis) (WP1.11-7)" % float(slope))
    if (cfg.get("roof_pitch_deg") is not None or len(cfg.get("heights") or []) == 1) and not plan.get("member_wind") \
            and not cfg.get("member_wind_not_required"):
        say("ERROR", "low-rise / portal building: member-level wind cases (Table 5 walls, Table 6 roof by pitch, "
                     "Cpi by opening ratio, uplift with 0.9DL) are required -- india_wind_tables.lowrise_member_wind")
    return out


def _table1_iv_building(cfg, ws) -> bool:
    """IS 875-3 Table 1 iv) class: declared k1_class 'iv' / 'important', or a hospital occupancy."""
    k1c = str(ws.get("k1_class") or cfg.get("k1_class") or "").strip().lower()
    if k1c in ("iv", "iv)", "table1_iv", "important"):
        return True
    occ = cfg.get("occupancy") or ((cfg.get("load_plan") or {}).get("seismic_summary") or {}).get("occupancy")
    occs = occ if isinstance(occ, (list, tuple)) else [occ]
    import re as _re
    for o in occs:
        if not isinstance(o, dict):
            continue
        if o.get("hospital") is True or o.get("lifeline") is True:
            return True
        use = " ".join(str(u) for u in ([o.get("use")] + list(o.get("uses") or [])) if u).lower()
        if _re.search(r"\bhospitals?\b", use):
            return True
    return False


def site_proxy_findings(rec, *, quantity="Vb", cfg=None) -> list:
    """H47 / ruling R5: one site-proxy policy.  A town not in IS 875-3 Annex A (Vb) or IS 1893 Annex E (zone) may
    use ``<q>_source = 'site_proxy'`` with the record {proxy_town, distance_km, basis, verify: True} and the corpus
    lookup stated as not tabulated.  The decision is india_loads.resolve_site_annex_proxy (the preflight and the
    helper agree).  Returns [(severity, message)]."""
    import india_loads as _IL
    r = _IL.resolve_site_annex_proxy(cfg or {}, quantity=quantity, record=rec)
    if r.get("found") and r.get("site_proxy"):
        return [("WARN", "%s from site_proxy %r (%s km, basis: %s) -- VERIFY against the %s map at the site "
                         "(ruling R5)" % (quantity, r.get("proxy_town"), r.get("distance_km"), r.get("cite"),
                                          "IS 875-3 Fig. 1" if quantity == "Vb" else "IS 1893 Fig. 1"))]
    return [("ERROR", "%s_source = 'site_proxy' refused (ruling R5): %s" % (
        "Vb" if quantity == "Vb" else "zone", "; ".join(r.get("required_inputs") or [r.get("note") or "incomplete"])))]


def _by_theta(x, theta):
    """{0: .., 90: ..} / {'theta_0': .., 'theta_90': ..} -> the entry for theta; a plain record -> theta 0 only."""
    if not isinstance(x, dict):
        return None
    for k in (theta, str(theta), "theta_%d" % theta):
        if k in x:
            return x[k]
    if any(k in x for k in (0, 90, "0", "90", "theta_0", "theta_90")):
        return None
    return x if theta == 0 else None


def lowrise_member_wind(pd_kNm2, h_eave_m, w_m, l_m, roof_pitch_deg, opening_ratio, *, theta_cases=(0, 90),
                        ridge_axis=None, corpus_hit=None, walls=None, roof=None, eor_cpe=None):
    """Member-level wind pressure sets for low-rise / portal buildings (7.3.1 F = (Cpe - Cpi) A pd):
    walls from Table 5, roof from Table 6 by pitch, Cpi +- from the opening ratio.  Returns a list of
    patterns {name, roof_windward_kNm2, roof_leeward_kNm2, wall_windward_kNm2, wall_leeward_kNm2,
    direction} (+ = towards the surface, i.e. roof downward / wall inward).

    H14 / L-15: ``corpus_hit`` = the retrieved Table 5 record(s) (exact_table 5; a plain record for theta 0 or
    {0: .., 90: ..}) is passed through (walls_source 'corpus'); ``walls`` = resolved wall records (same shapes) and
    ``roof`` = a resolved Table 6 record {EF, GH, EG, FH} override the in-repo tables; ``eor_cpe`` = EOR Cpe
    record(s) for geometry outside Table 5 (H15).  The along-ridge (WM90) patterns carry the gable-wall Table 5
    theta = 90 coefficients (C windward, D leeward).  india_combos applies every pattern from both sides."""
    cpi = cpi_from_openings(opening_ratio)["Cpi"]
    hw = float(h_eave_m) / float(w_m)
    lw = float(l_m) / float(w_m)

    def _walls(theta):
        ov = _by_theta(walls, theta)
        if isinstance(ov, dict) and ov.get("Cpe"):
            return dict(ov, found=True, resolved_via=ov.get("resolved_via") or "override")
        hit = _by_theta(corpus_hit, theta)
        return resolve_cpe_walls(hw, lw, float(theta), corpus_hit=hit, eor_cpe=_by_theta(eor_cpe, theta))

    walls0, walls90 = _walls(0), _walls(90)
    if isinstance(roof, dict) and all(roof.get(k) is not None for k in ("EF", "GH", "EG", "FH")):
        roof = dict(roof, found=True)
    else:
        roof = roof_cpe_pitched(hw, roof_pitch_deg)
    if not roof.get("found"):
        return {"found": False, "note": roof.get("note")}
    wc = (walls0.get("Cpe") or {}) if isinstance(walls0, dict) and walls0.get("found") else {}
    Aw, Bw = wc.get("A"), wc.get("B")
    if Aw is None or Bw is None:
        return {"found": False, "note": "IS 875-3 Table 5 wall Cpe not resolved for h/w=%.3f l/w=%.3f; "
                                        "no default coefficients are substituted" % (hw, lw),
                "walls": walls0}
    wc90 = (walls90.get("Cpe") or {}) if isinstance(walls90, dict) and walls90.get("found") else {}
    Cw, Dw = wc90.get("C"), wc90.get("D")
    if Cw is None or Dw is None:
        return {"found": False, "note": "IS 875-3 Table 5 theta = 90 (gable wall) Cpe not resolved for h/w=%.3f "
                                        "l/w=%.3f; no default coefficients are substituted" % (hw, lw),
                "walls": walls90}
    src0 = walls0.get("resolved_via") if isinstance(walls0, dict) else None
    src90 = walls90.get("resolved_via") if isinstance(walls90, dict) else None
    pats = []
    for s_cpi in (+cpi, -cpi):
        # theta = 0: wind normal to the ridge (E/F windward slope, G/H leeward)
        pats.append({"name": "WM0%s" % ("+" if s_cpi > 0 else "-"), "direction": "across_ridge",
                     "roof_windward_kNm2": (roof["EF"] - s_cpi) * pd_kNm2,
                     "roof_leeward_kNm2": (roof["GH"] - s_cpi) * pd_kNm2,
                     "wall_windward_kNm2": (Aw - s_cpi) * pd_kNm2,
                     "wall_leeward_kNm2": (Bw - s_cpi) * pd_kNm2,
                     "Cpi": s_cpi, "roof": roof, "walls_source": src0})
        # theta = 90: wind along the ridge -- roof E/G windward, F/H leeward; gable walls C (windward) / D (leeward)
        pats.append({"name": "WM90%s" % ("+" if s_cpi > 0 else "-"), "direction": "along_ridge",
                     "roof_windward_kNm2": (roof["EG"] - s_cpi) * pd_kNm2,
                     "roof_leeward_kNm2": (roof["FH"] - s_cpi) * pd_kNm2,
                     "wall_windward_kNm2": (Cw - s_cpi) * pd_kNm2,
                     "wall_leeward_kNm2": (Dw - s_cpi) * pd_kNm2,
                     "Cpi": s_cpi, "roof": roof, "walls_source": src90})
    if ridge_axis in ("X", "Y"):
        across = "Y" if ridge_axis == "X" else "X"
        for p in pats:
            p["wind_axis"] = across if p["direction"] == "across_ridge" else ridge_axis
    return {"found": True, "patterns": pats, "Cpi": cpi, "h_over_w": hw,
            "walls_source": {"theta_0": src0, "theta_90": src90},
            "cite": "IS 875 (Part 3):2015 7.3.1, 7.3.2, Table 5, Table 6"}
