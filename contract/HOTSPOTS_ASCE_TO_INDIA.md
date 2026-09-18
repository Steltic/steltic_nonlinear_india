# Wave 1 hotspot map — ASCE 41 / ASCE 7 Ch.16 → India

| USA hotspot | Path | India wave-1 action |
|-------------|------|---------------------|
| ASCE 41 NSP authority | `skills/Skill_pushover_*`, `pushover/hinge_params.json`, `docs/README_pushover.md` | Retarget docs; leave engine; **found:false** for IS NSP/hinge tables |
| ASCE 7 Ch.16 rules | `nlrha/ch16_params.json`, `nlrha/acceptance.py`, `nlrha/cli.py` | Stamp `india_authoritative=false`; load via `india_authority.load_ch16_params`; require `nl_plan` RAG evidence for India claims |
| §16.1.2 drift relief | `snl/feedback.py` `drift_plan`, `docs/README_feedback.md` | Gate: **ineligible** unless `nl_plan.drift_relief_analogue` found:true |
| §16.1.4 design criteria | `nlrha/design_criteria.py` | Still drafts from scaffolding; banner that India must replace governing docs via RAG |
| USGS MCE_R / CS | `nlrha/site_hazard.py`, `nlrha/cli.py hazard` | Document as USA scaffolding; India spectrum from IS 1893 RAG / HR seis |
| DDM ASCE §2.3 combos | `steltic_ddm/loads.py`, `portal_adapter.py` | Prefer `load_plan` / steltic_india `india_loads`; RuntimeError if India without plan |
| Risk Category / Ie | `nlrha/acceptance.py`, `steltic_ddm/phi_s.py` | Keep engine wiring; docs: use IS Importance Factor — no invented RC map |
| Contract / skills / README | `contract/*`, `skills/*`, `README.md`, `pyproject.toml` | Retarget to IS 1893 + steltic_india interfaces |
| Examples Ex18/Ex22 | `examples/*` | Keep as USA regression fixtures; not India authority |

Deferred (wave 2+): full IS time-history acceptance implementation, India hinge sources, metric N-mm engine, India example package, USGS→IS hazard replacement.
