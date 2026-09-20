> **CORRECTION (WP4.7, 2026-09-20): Stage D is NOT complete.** `brace_spec`, the force-controlled column capacity,
> the pushover gravity and the NSP delta_t still mixed inch/kip with mm/N (NLREPO-09: at L = 5000 mm a brace came out
> 4448x weak). Until each routine is ported and tested in N-mm, `pushover.package_reader.apply_nl_unit_bridge`
> **forces Stage B** (N-mm HR package -> kip-in analysis at ingest) for pushover and NLRHA and logs the refusal.
> India material (IS 2062 fy per section) and IS 800 capacities are computed in N/mm/MPa (pushover/india_materials.py)
> and converted once at the kip-in model boundary. The DDM (steltic_ddm) runs natively in N-mm.

# NL → N-mm migration plan (India)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)  
**Constraint:** Prefer not to break the suite (≥146). Default analysis stays kip-in until a job opts into N-mm.

## Exact kip islands (inventory)

| Area | Files (representative) | Quantity / hardcode |
|------|------------------------|---------------------|
| Unit module default | `snl/india_units.py` | `ANALYSIS_UNITS = "kip-in"` default; India jurisdiction+units → native N-mm (wave 5) |
| Package geometry | `pushover/package_reader.py`, `steltic_ddm/ingest.py` | Stage B bridge → kip-in; **Stage D** skips when `native_nmm` / `_nl_analysis_units='N-mm'` |
| Fibre / hinge models | `pushover/fibre_model.py`, `pushover/hinge_models.py`, `steltic_ddm/sections_fiber.py` | **Stage C** fibre twin; **IMK found:false** (no IS NSP analogue — prefer fibre for N-mm) |
| Pushover analysis | `pushover/nonlinear_model.py`, `pushover/cli.py` | V in analysis units when native N-mm |
| NLRHA | `nlrha/model.py`, `nlrha/run.py` | Path accel `g_accel`=9810; **Ch.16 live found:false** (psf thresholds gated) |
| DDM / GMNIA | `steltic_ddm/portal_adapter.py`, `steltic_ddm/loads.py` | Portal + **grid `beam_udl` dual-path** (wave 5) |
| Hazard | `nlrha/site_hazard.py`, `nlrha/india_hazard.py` | Sa/g; India zone path |
| Viewers / reports | `*/viewer3d.py`, `*/report*.py` | Stage A + **wave 5 SI HTML labels** when India/N-mm |

## Staged flip

1. **Stage A — dual display** ✅ (wave 3)
2. **Stage B — package boundary** ✅ (wave 3)
3. **Stage C — fibre/E/Fy SI twin** ✅ (wave 4)
4. **Stage D — OpenSees N-mm path** — DISABLED for pushover/NLRHA (WP4.7) until ported
   - Grid `beam_udl` N/mm twin
   - Report HTML SI labels via `report_force_length_labels`
   - India jurisdiction + units N-mm → `wants_native_nmm_analysis`
   - IMK / Ch.16 live: **found:false** (do not invent IS analogues)

## Gate

- load_plan / IS 1893 RAG gate remains mandatory for India jobs (unchanged).
- Do not invent IS analogues for ASCE Ch.16 / S400 Ω / ASCE 41 hinges — `found:false` stays honest.

## Wave 5 outcome

**SI rewrite NOT complete (see correction at the top)** (hard leftovers listed in `KIP_ISLANDS` / `imk_hinge_si_status` / `ch16_live_si_status`).
