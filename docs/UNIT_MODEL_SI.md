# India NL unit model (SI wave 4 — Stages C + partial D)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)

## Current state

| Layer | Unit system | Notes |
|-------|-------------|-------|
| Shared `snl/india_units.py` factors | Dual | `g_accel`, `steel_E`/`steel_G`, `set_analysis_units` |
| Stage A display | SI or kip labels | `display_scale(cfg)` |
| Stage B package ingest | Bridge (default) | N-mm HR → kip-in once unless native |
| Stage C fibre | Twin | `units='N-mm'` → MPa / mm² / IS 808 |
| Stage D analysis | Opt-in N-mm | `ANALYSIS_UNITS` / `cfg['_nl_analysis_units']` / `native_nmm` |
| Default OpenSees | **kip-in** | USA archetypes + suite default |
| HR / CFS India engines | **N-mm-sec** | Native since wave 1 |

## Feature flags

- `cfg['units']='N-mm'` → SI display + SI package field names (Stages A–B).
- `cfg['native_nmm']=True` or `cfg['_nl_analysis_units']='N-mm'` or `cfg['analysis_si']=True` → **native** N-mm analysis (skip kip bridge; fibre SI; g=9810).
- `cfg['units']='kip-in'` / `force_kip_in=True` → legacy kip path.
- Module default `ANALYSIS_UNITS = "kip-in"` until a future default flip.

## Wave 4 deliverable

Stage C complete + Stage D partial. 146 tests passing (8 new in `test_si_wave4_nl_units.py`).
