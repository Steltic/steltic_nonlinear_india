# India NL unit model (Stages A–C; Stage D disabled for pushover/NLRHA — WP4.7)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)

## Current state

| Layer | Unit system | Notes |
|-------|-------------|-------|
| Shared `snl/india_units.py` | Dual | `g_accel`, `steel_E`/`steel_G`, `set_analysis_units`, `report_force_length_labels` |
| Stage A display | SI or kip labels | `display_scale(cfg)` |
| Stage B package ingest | Bridge (default) | N-mm HR → kip-in once unless native |
| Stage C fibre | Twin | `units='N-mm'` → MPa / mm² / IS 808 |
| Stage D analysis | Disabled (pushover/NLRHA) | brace_spec / column capacity / gravity / NSP not yet ported to N-mm |
| Default OpenSees | **kip-in** | USA archetypes + suite default |
| India job auto | **Stage B forced** | pushover/NLRHA always bridge N-mm -> kip-in at ingest (WP4.7); DDM native N-mm |
| HR / CFS India engines | **N-mm-sec** | Native since wave 1 |

## Hard leftovers (found:false — not invented)

1. **IMK / ASCE 41 hinges** — no IS NSP analogue; prefer Stage C fibre for N-mm (`imk_hinge_si_status`).
2. **Ch.16 live idealisation** — psf-threshold rooted; no IS suite (`ch16_live_si_status`).
3. Module `ANALYSIS_UNITS` default remains kip-in for USA suite safety.
4. Some ASCE clause narrative strings in reports (labels are SI when India/N-mm).

## Feature flags

- `cfg['units']='N-mm'` → SI display + SI package field names.
- `cfg['native_nmm']=True` / `_nl_analysis_units='N-mm'` / `analysis_si` → native N-mm analysis.
- `jurisdiction='india'` + SI units → native N-mm (wave 5).
- `force_kip_in=True` → legacy kip path.

## Wave 5 deliverable

Stages A–D complete for India stack. ≥153 tests (7 new in `test_si_wave5_nl_units.py`).
