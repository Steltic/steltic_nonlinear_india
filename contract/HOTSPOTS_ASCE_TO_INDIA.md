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

## NL polish Wave E (honesty emitters — confirm)

On tip after Ex1 partial merge (`c689de0`+), COMPLETE gate disclosures are durable:

- `nlrha.india_authority.nsp_acceptance_tables_status()` → **found:false**; prefer fibre; hinge_params UNVERIFIED
- `nlrha.india_authority.complete_gate_disclosures()` / `write_complete_gate_disclosures(out_dir)` → writes `complete_gate_disclosures.json` (pushover + nlrha out dirs)
- `asce_16_1_2_drift_relief_analogue` → **found:false**; `feedback_drift_loop: ineligible` (`snl/feedback.py` `drift_plan`)
- **No invent:** do not fabricate IS NSP IO/LS/CP tables or an IS waiver of 7.11.1.1 after time-history

## Modal pattern T-floor (IN_Ex3 Y)

`pushover.nonlinear_model.modal_pattern` applies a **numerical** min period
`DEFAULT_MIN_T_S = 0.02` s (~50 Hz) plus the Ex1 ≥5% mass / alignment pick.
This is an engineering sanity filter for spurious stiff eigenmodes — **not** an
IS 1893 / ASCE approximate-period provision. IN_Ex3 Chennai Y previously selected
mode 10 at T≈0.0007 s with ~100% mass; re-run Y pushover after this tip.

## COMPLETE gate (Michael 2026-09-20)

`nlrha.india_authority.complete_allowed` / `design_status` / `admin_notify`:

- **COMPLETE** when fibre preferred/used **and** durable disclosures show
  `india_nsp_acceptance_tables` + `asce_16_1_2_drift_relief_analogue` as **found:false**
  (feedback drift loop **ineligible**; IS 1893 §7.11.1 remains the India drift check).
- Disclosed found:false **does not** force PARTIAL.
- **PARTIAL** if fibre not used and hinges UNVERIFIED without EOR, or disclosures missing.
- Do **not** invent NSP IO/LS/CP tables or a fake §16.1.2 waiver. Optional EOR hinge
  fixture is not required when fibre is used.
- `write_complete_gate_disclosures` persists `complete_allowed` / `design_status` /
  `admin_notify` beside the honesty rows.

