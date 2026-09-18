# India NL unit model (SI wave 2 — boundary + migration plan)

**Date:** 2026-09-18 Asia/Bangkok (UTC+7)

## Current state

| Layer | Unit system | Notes |
|-------|-------------|-------|
| Shared `snl/india_units.py` factors | Dual | `apply_si_geometry` → mm for stubs / HR package handoff |
| Pushover / NLRHA / DDM OpenSees | **kip-in** | Default `UNIT_SYSTEM = "kip-in"`; `activate_kip_in()` before analysis |
| HR / CFS India engines | **N-mm-sec** | Native since wave 1 |

**Why deferred:** 130+ NL tests assume kip-in fibre sections, hinge rotations, USGS/ASCE hazard scaffolding, and report strings. Flipping OpenSees mid-wave without a full fibre/hinge/mass rewrite would break the suite.

## Wave 2 deliverable

See `docs/SI_NL_MIGRATION_PLAN.md` for exact kip islands and a staged flip plan. This wave does **not** change analysis units.
