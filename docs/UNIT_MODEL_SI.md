# India NL unit model (SI wave 3 — Stages A–B)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)

## Current state

| Layer | Unit system | Notes |
|-------|-------------|-------|
| Shared `snl/india_units.py` factors | Dual | `apply_si_geometry` → mm for stubs / HR handoff |
| Stage A display | SI or kip labels | `display_scale(cfg)` — SI display from kip-in engine when `units='N-mm'` |
| Stage B package ingest | Bridge | N-mm HR → kip-in once; `calc['_nl_unit_bridge']` |
| Pushover / NLRHA / DDM OpenSees | **kip-in** | `ANALYSIS_UNITS = "kip-in"` until Stage D |
| HR / CFS India engines | **N-mm-sec** | Native since wave 1 |

## Feature flag

- `cfg['units']='N-mm'` (or `si_native` / metric) → SI **display** + SI package field names at HR boundary.
- `cfg['units']='kip-in'` / `force_kip_in=True` → legacy kip path.
- Analysis remains kip-in for both until Stage D.

## Wave 3 deliverable

Stages A–B of `docs/SI_NL_MIGRATION_PLAN.md`. Analysis units unchanged; 138 tests passing.
