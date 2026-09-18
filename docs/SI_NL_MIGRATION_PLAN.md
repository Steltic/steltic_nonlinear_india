# NL → N-mm migration plan (India)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)  
**Constraint:** Prefer not to break ~132 tests this wave. Analysis stays kip-in until stages C–D land.

## Exact kip islands (inventory)

| Area | Files (representative) | Quantity / hardcode |
|------|------------------------|---------------------|
| Unit module default | `snl/india_units.py` | `ANALYSIS_UNITS = "kip-in"`; `activate_kip_in()` |
| Package geometry | `pushover/package_reader.py`, `steltic_ddm/ingest.py` | inches / kip demands (**Stage B bridge** converts N-mm HR once) |
| Fibre / hinge models | `pushover/fibre_model.py`, `pushover/hinge_models.py`, `steltic_ddm/sections_fiber.py` | E=29000 ksi, Fy ksi, areas in² |
| Pushover analysis | `pushover/nonlinear_model.py`, `pushover/cli.py`, `pushover/postprocess.py` | V in kip, Ω, drift |
| NLRHA | `nlrha/model.py`, `nlrha/run.py`, `nlrha/cli.py`, `nlrha/report.py` | gravity kip, records scaled for g=386.4 |
| DDM / GMNIA | `steltic_ddm/solver.py`, `steltic_ddm/loads.py`, `steltic_ddm/portal_adapter.py`, `steltic_ddm/model_gmnia.py` | `_seis_V_kip`, `w` kip/in, portal wind kip |
| Hazard | `nlrha/site_hazard.py`, `nlrha/india_hazard.py` | Sa/g; India zone path exists but mass/force still kip-in model |
| Viewers / reports | `*/viewer3d.py`, `*/report*.py` | **Stage A** `display_scale` / `unit_labels` (SI display OK); many kip strings remain |

## Staged flip

1. **Stage A — dual display only** ✅ (wave 3): `display_scale` / `fmt_force` / `fmt_moment` / `demand_field_names`; pushover viewer `unit_labels`. Engine kip-in.
2. **Stage B — package boundary** ✅ (wave 3): N-mm HR package → kip-in once at ingest (`apply_nl_unit_bridge`); `calc['_nl_unit_bridge']`. Tests green.
3. **Stage C — fibre/E/Fy SI twin**: build fibre sections from IS 808 mm props + E=2e5 MPa behind `units='N-mm'` flag; add golden tests before default flip.
4. **Stage D — OpenSees N-mm default**: g=9810, mass tonne, rewrite portal/DDM load helpers; migrate tests to SI fixtures; retire kip default.

## Gate

- load_plan / IS 1893 RAG gate remains mandatory for India jobs (unchanged).
- Do not invent IS analogues for ASCE Ch.16 / S400 Ω stacks — `found:false` stays honest.
