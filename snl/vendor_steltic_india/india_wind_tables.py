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
        _row("<=0.5", "1.5<l/w<=4", 0, +0.7, -0.25, -0.6, -0.6, -1.0),
        _row("<=0.5", "1.5<l/w<=4", 90, -0.5, -0.5, +0.7, -0.1, -1.0),
        # 1/2 < h/w ≤ 3/2
        _row("0.5<h/w<=1.5", "1<=l/w<=1.5", 0, +0.7, -0.25, -0.6, -0.6, -1.1),
        _row("0.5<h/w<=1.5", "1<=l/w<=1.5", 90, -0.6, -0.6, +0.7, -0.25, -1.1),
        _row("0.5<h/w<=1.5", "1.5<=l/w<4", 0, +0.7, -0.3, -0.7, -0.7, -1.1),
        _row("0.5<h/w<=1.5", "1.5<=l/w<4", 90, -0.5, -0.5, +0.7, -0.1, -1.1),
        # 3/2 < h/w ≤ 6
        _row("1.5<h/w<=6", "1<l/w<=1.5", 0, +0.8, -0.25, -0.8, -0.8, -1.2),
        _row("1.5<h/w<=6", "1<l/w<=1.5", 90, -0.8, -0.8, +0.8, -0.25, -1.2),
        _row("1.5<h/w<=6", "1.5<=l/w<=4", 0, +0.7, -0.4, -0.7, -0.7, -1.2),
        _row("1.5<h/w<=6", "1.5<=l/w<=4", 90, -0.5, -0.5, +0.8, -0.1, -1.2),
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
    r = float(h_over_w)
    if r <= 0.5:
        return "<=0.5"
    if r <= 1.5:
        return "0.5<h/w<=1.5"
    if r <= 6.0:
        return "1.5<h/w<=6"
    return ">=6"


def _lw_band(h_band: str, l_over_w: float) -> str | None:
    """Map plan ratio into the printed Table 5 band for the given height band."""
    r = float(l_over_w)
    if h_band == "<=0.5":
        if 1.0 < r <= 1.5:
            return "1<l/w<=1.5"
        if 1.5 < r <= 4.0:
            return "1.5<l/w<=4"
        return None
    if h_band == "0.5<h/w<=1.5":
        if 1.0 <= r <= 1.5:
            return "1<=l/w<=1.5"
        if 1.5 <= r < 4.0:
            return "1.5<=l/w<4"
        return None
    if h_band == "1.5<h/w<=6":
        if 1.0 < r <= 1.5:
            return "1<l/w<=1.5"
        if 1.5 <= r <= 4.0:
            return "1.5<=l/w<=4"
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


def resolve_ka(A_m2: float, corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 4; demote in-repo Ka to fallback when corpus found:false."""
    if _corpus_found(corpus_hit):
        out = dict(corpus_hit)
        out.setdefault("found", True)
        out.setdefault("source", "corpus_exact_table_4")
        out.setdefault(
            "cite",
            out.get("cite") or "IS 875 (Part 3) : 2015 Table 4 (corpus exact_table 4)",
        )
        out["A_m2"] = float(A_m2)
        out["resolved_via"] = "corpus"
        return out
    fb = ka_for_area_m2(A_m2, allow_fallback=allow_fallback)
    fb["resolved_via"] = "fallback" if fb.get("found") else "refused"
    fb["corpus_found"] = False
    return fb


def resolve_cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float = 0.0,
                      corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 5; demote in-repo wall Cpe to fallback when corpus found:false."""
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
# read from the PDF p.16 scan (400 dpi); the mid band rows 45/60 (+0.2/-0.5/-0.8/-0.8, +0.6/-0.5/-0.8/-0.6) and
# the bottom band rows 30/40/50/60 (-1.0/-0.5/-0.8/-0.7, -0.2/-0.5/-0.8/-0.7, +0.2/-0.5/-0.8/-0.7,
# +0.5/-0.5/-0.8/-0.7) were re-read from a 300 dpi crop on 2026-09-20 (HR-INTEGRATE) and match the values below.
TABLE_6_CPE_PITCHED = {
    "le_0.5": {0: (-0.8, -0.4, -0.8, -0.4), 5: (-0.9, -0.4, -0.8, -0.4), 10: (-1.2, -0.4, -0.8, -0.6),
               20: (-0.4, -0.4, -0.7, -0.6), 30: (0.0, -0.4, -0.7, -0.6), 45: (0.3, -0.5, -0.7, -0.6),
               60: (0.7, -0.6, -0.7, -0.6)},
    "0.5_1.5": {0: (-0.8, -0.6, -1.0, -0.6), 5: (-0.9, -0.6, -0.9, -0.6), 10: (-1.1, -0.6, -0.8, -0.6),
                20: (-0.7, -0.5, -0.8, -0.6), 30: (-0.2, -0.5, -0.8, -0.6), 45: (0.2, -0.5, -0.8, -0.8),
                60: (0.6, -0.5, -0.8, -0.6)},
    "1.5_6": {0: (-0.7, -0.6, -0.9, -0.7), 5: (-0.7, -0.6, -0.8, -0.8), 10: (-0.7, -0.6, -0.8, -0.8),
              20: (-0.8, -0.6, -0.8, -0.8), 30: (-1.0, -0.5, -0.8, -0.7), 40: (-0.2, -0.5, -0.8, -0.7),
              50: (0.2, -0.5, -0.8, -0.7), 60: (0.5, -0.5, -0.8, -0.7)},
}


def k4_required(cyclone_belt, structure_class="other"):
    """6.3.4 + decision D10: k4 and Kd come from the same cyclone_belt flag."""
    if not cyclone_belt:
        return {"k4": 1.0, "Kd": None, "cite": K4_CITE + " (outside the belt: k4 = 1.0)"}
    cls = str(structure_class or "other").lower()
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
    if plan.get("no_wind") or not ws:
        return out
    say = lambda s, m: out.append((s, m))
    cb = ws.get("cyclone_belt", cfg.get("cyclone_belt"))
    if cb is None:
        say("ERROR", "wind_summary.cyclone_belt (true/false, with cite) must be declared -- it sets Kd = 1.0 "
                     "(7.2.1) and k4 (6.3.4) together (decision D10)")
    k4 = ws.get("k4"); Kd = ws.get("Kd")
    if k4 is not None and float(k4) not in (1.0, 1.15, 1.30):
        say("ERROR", "k4 = %s not in {1.0, 1.15, 1.30} (IS 875-3 6.3.4)" % k4)
    if cb is True:
        req = k4_required(True, ws.get("structure_class") or cfg.get("wind_structure_class"))
        if Kd is not None and abs(float(Kd) - 1.0) > 1e-9:
            say("ERROR", "cyclone_belt: Kd = %s but %s" % (Kd, KD_CITE))
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
    src = str(ws.get("Vb_source") or "").lower()
    if "proxy" in src or "nearest" in src:
        say("ERROR", "Vb from a proxy city is not permitted: read IS 875-3 Fig. 1 at the site coordinates and "
                     "record Vb_source='derived_from_map' with lat/long (WP1.11-8)")
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


def lowrise_member_wind(pd_kNm2, h_eave_m, w_m, l_m, roof_pitch_deg, opening_ratio, *, theta_cases=(0, 90),
                        ridge_axis=None):
    """Member-level wind pressure sets for low-rise / portal buildings (7.3.1 F = (Cpe - Cpi) A pd):
    walls from Table 5, roof from Table 6 by pitch, Cpi +- from the opening ratio.  Returns a list of
    patterns {name, roof_windward_kNm2, roof_leeward_kNm2, wall_windward_kNm2, wall_leeward_kNm2,
    direction} (+ = towards the surface, i.e. roof downward / wall inward)."""
    cpi = cpi_from_openings(opening_ratio)["Cpi"]
    hw = float(h_eave_m) / float(w_m)
    lw = float(l_m) / float(w_m)
    walls = resolve_cpe_walls(hw, lw, 0.0, corpus_hit=None)
    roof = roof_cpe_pitched(hw, roof_pitch_deg)
    if not roof.get("found"):
        return {"found": False, "note": roof.get("note")}
    wc = (walls.get("Cpe") or {}) if isinstance(walls, dict) and walls.get("found") else {}
    Aw, Bw = wc.get("A"), wc.get("B")
    if Aw is None or Bw is None:
        return {"found": False, "note": "IS 875-3 Table 5 wall Cpe not resolved for h/w=%.3f l/w=%.3f; "
                                        "no default coefficients are substituted" % (hw, lw)}
    pats = []
    for s_cpi in (+cpi, -cpi):
        # theta = 0: wind normal to the ridge (E/F windward slope, G/H leeward)
        pats.append({"name": "WM0%s" % ("+" if s_cpi > 0 else "-"), "direction": "across_ridge",
                     "roof_windward_kNm2": (roof["EF"] - s_cpi) * pd_kNm2,
                     "roof_leeward_kNm2": (roof["GH"] - s_cpi) * pd_kNm2,
                     "wall_windward_kNm2": (Aw - s_cpi) * pd_kNm2,
                     "wall_leeward_kNm2": (Bw - s_cpi) * pd_kNm2,
                     "Cpi": s_cpi, "roof": roof, "walls_source": walls.get("resolved_via") if isinstance(walls, dict) else None})
        pats.append({"name": "WM90%s" % ("+" if s_cpi > 0 else "-"), "direction": "along_ridge",
                     "roof_windward_kNm2": (roof["EG"] - s_cpi) * pd_kNm2,
                     "roof_leeward_kNm2": (roof["FH"] - s_cpi) * pd_kNm2,
                     "Cpi": s_cpi, "roof": roof})
    if ridge_axis in ("X", "Y"):
        across = "Y" if ridge_axis == "X" else "X"
        for p in pats:
            p["wind_axis"] = across if p["direction"] == "across_ridge" else ridge_axis
    return {"found": True, "patterns": pats, "Cpi": cpi, "h_over_w": hw,
            "cite": "IS 875 (Part 3):2015 7.3.1, 7.3.2, Table 5, Table 6"}
