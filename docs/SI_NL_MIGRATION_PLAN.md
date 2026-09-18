# NL → N-mm migration plan (India)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)  
**Constraint:** Prefer not to break the ~138+ test suite. Default analysis stays kip-in until a job opts into N-mm.

## Exact kip islands (inventory)

| Area | Files (representative) | Quantity / hardcode |
|------|------------------------|---------------------|
| Unit module default | `snl/india_units.py` | `ANALYSIS_UNITS = "kip-in"` default; `set_analysis_units('N-mm')` for India jobs |
| Package geometry | `pushover/package_reader.py`, `steltic_ddm/ingest.py` | Stage B bridge → kip-in; **Stage D** skips bridge when `native_nmm` / `_nl_analysis_units='N-mm'` |
| Fibre / hinge models | `pushover/fibre_model.py`, `pushover/hinge_models.py`, `steltic_ddm/sections_fiber.py` | **Stage C** fibre twin E=2e5 MPa / mm² / IS 808; IMK hinges still ksi |
| Pushover analysis | `pushover/nonlinear_model.py`, `pushover/cli.py`, `pushover/postprocess.py` | V in kip unless native N-mm package |
| NLRHA | `nlrha/model.py`, `nlrha/run.py`, `nlrha/cli.py` | **Stage D** Path accel uses `g_accel` (9810 mm/s²); ch16 live still psf-rooted |
| DDM / GMNIA | `steltic_ddm/portal_adapter.py`, `steltic_ddm/loads.py` | **Stage D** portal `_seis_V` / `_wind_H` / `portal_beam_udl` dual-path; grid `beam_udl` still kip/in |
| Hazard | `nlrha/site_hazard.py`, `nlrha/india_hazard.py` | Sa/g; India zone path exists |
| Viewers / reports | `*/viewer3d.py`, `*/report*.py` | Stage A display; many kip HTML strings remain |

## Staged flip

1. **Stage A — dual display only** ✅ (wave 3): `display_scale` / `fmt_force` / `fmt_moment` / `demand_field_names`; pushover viewer `unit_labels`. Engine kip-in.
2. **Stage B — package boundary** ✅ (wave 3): N-mm HR package → kip-in once at ingest (`apply_nl_unit_bridge`); `calc['_nl_unit_bridge']`. Tests green.
3. **Stage C — fibre/E/Fy SI twin** ✅ (wave 4): `FiberSectionBuilder(units='N-mm')` → E=2e5 MPa, dims×25.4 / IS 808 preferred; wired from `fibre_model` / GMNIA when analysis N-mm.
4. **Stage D — OpenSees N-mm path** 🟡 **partial** (wave 4): `ANALYSIS_UNITS` can be N-mm; portal seismic/UDL N-mm twin; NLRHA `g_accel`=9810; native package skips kip bridge. **Remaining:** grid `beam_udl`, IMK/hinge ksi, ch16 live psf idealisation, report HTML sweep, default flip.

## Gate

- load_plan / IS 1893 RAG gate remains mandatory for India jobs (unchanged).
- Do not invent IS analogues for ASCE Ch.16 / S400 Ω stacks — `found:false` stays honest.
