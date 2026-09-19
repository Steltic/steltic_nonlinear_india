# Hotspot map — ASCE 41 / ASCE 7 Ch.16 → India

| USA hotspot | Path | India action |
|-------------|------|---------------------|
| ASCE 41 NSP authority | `skills/Skill_pushover_*`, `pushover/hinge_params.json`, `docs/README_pushover.md` | **found:false** — hinge_params UNVERIFIED; IS 800 §4.5 ≠ NSP acceptance (`hinge_analogue_status`) |
| ASCE 7 Ch.16 rules | `nlrha/ch16_params.json`, `nlrha/acceptance.py`, `nlrha/cli.py` | Scaffolding (`india_authoritative=false`); honest replacements via `india_acceptance_rules()` (drift 0.004, 7.7.4 spectrum compat) |
| §16.1.2 drift relief | `snl/feedback.py` `drift_plan`, `docs/README_feedback.md` | **ineligible** unless `nl_plan.drift_relief_analogue` found:true |
| §16.1.4 design criteria | `nlrha/design_criteria.py` | Drafts from scaffolding; India must replace governing docs via RAG |
| USGS MCE_R / CS | `nlrha/site_hazard.py`, `nlrha/cli.py hazard` | **Stop assuming USGS** — `nlrha/india_hazard.py` + `nlrha hazard --zone …`; USGS only with `--usgs` |
| DDM ASCE §2.3 combos | `steltic_ddm/loads.py`, `portal_adapter.py` | Prefer `load_plan` / steltic_india `india_loads`; RuntimeError if India without plan |
| Risk Category / Ie | `nlrha/acceptance.py`, `steltic_ddm/phi_s.py` | Use IS Importance Factor I (Table 8) — no invented RC↔I map |
| Metric / SI | `snl/india_units.py` | Boundary helpers (m→in, kN→kip); full N-mm rewrite **deferred** |
| Contract / skills / README | `contract/*`, `skills/*`, `README.md`, `pyproject.toml` | Retarget to IS 1893 + steltic_india interfaces |
| Examples Ex18/Ex22 | `examples/Ex*` | USA regression fixtures — not India authority |
| India package stub | `examples/India_package_stub/` | Interface docs + `nl_plan` / cfg / hazard shape for steltic_india packages |

Deferred: full Ch.16-suite-numeric replacement (no IS analogue), full SI engine rewrite, live E2E with hosted RAG, push/PR.


## DDM λu < 1 on wind/EQ (capacity finding, not a missing feature)

IN_Ex1 SCBF Delhi NL reported governing **λu = 0.651** on `1.2DL+1.2LL+1.2W_X` after India combo
prune + transfer-gate EQ_X/Y + CHS brace fibre patches. Treat as a **capacity finding** when the
engine/transfer gate is correct — do **not** invent λu≥1 or silently drop the governing combo.
Disclose φs·λu < 1.0 and hand back to HR for resize if the brief requires pass.
