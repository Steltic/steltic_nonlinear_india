"""shed.py -- is this run a shed? (second wave, review E_NL item 15: on sheds Vmax/W, not Vmax/VB, is the headline).

VB is the R-reduced IS 1893 design base shear. On a light, wind- or stiffness-governed shed it is only tens of kN, so the
pushover Vmax/VB reads 20-130 although the ratio is physically right (review E_NL item 5: Ex8 Chennai VB 35.5 kN,
Vmax 4 554 kN). The headline there is the strength coefficient Vmax/W. A run is a shed when the HR package says so:

  * single-storey: one floor level in the HR seismic weight table (load_plan.json seismic_summary.W_by_floor_kN), or
  * an industrial building: the HR cfg's building_type or occupancy use names industrial / warehouse / shed / workshop
    / crane use.

Nothing is typed in: the basis sentence names the field it came from.
"""
from __future__ import annotations

import json
import os
import re

INDUSTRIAL_WORDS = ("industrial", "warehouse", "shed", "workshop", "crane")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                                  # noqa: BLE001
        return None


def _cfg_text(job):
    p = os.path.join(job, "cfg.py")
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except Exception:                                                  # noqa: BLE001
        return ""


def shed_basis(job):
    """dict(shed=bool, basis=str or None, W_kN=float or None, floors=int or None) for one run folder."""
    ss = ((_load(os.path.join(job, "load_plan.json")) or {}).get("seismic_summary") or {})
    wf = ss.get("W_by_floor_kN") if isinstance(ss.get("W_by_floor_kN"), list) else None
    po = (_load(os.path.join(job, "pushover", "pushover_package.json")) or {}).get("basis") or {}
    W = po.get("W_kN") or ss.get("W_kN")
    out = dict(shed=False, basis=None, W_kN=(float(W) if isinstance(W, (int, float)) else None),
               floors=(len(wf) if wf else None))
    if wf and len(wf) == 1:
        out.update(shed=True, basis="Single-storey building (one floor level in the HR seismic weight table)")
        return out
    src = _cfg_text(job)
    for key, rx in (("building_type", r"building_type\s*=\s*[\"']([^\"']+)[\"']"),
                    ("occupancy use", r"[\"']use[\"']\s*:\s*[\"']([^\"']+)[\"']")):
        m = re.search(rx, src)
        if m and any(w in m.group(1).lower() for w in INDUSTRIAL_WORDS):
            out.update(shed=True, basis="Industrial building (%s '%s' in the HR design input)" % (
                "building type" if key == "building_type" else key.replace("_", " "), m.group(1)))
            return out
    return out
