# IS 1893 (Part 1) : 2016 — NL-relevant anchors (India RAG)

Corpus stem: `IS_1893_Part_1_2016` in your IS corpus, built in the Steltic hub from your own licensed BIS PDFs (see CORPUS_FIX_LLM_INSTRUCTIONS.md).

These ids resolve in the India index. **Always re-retrieve LIVE** before quoting body text
in a deliverable — Docling page merges can pollute neighbouring body text.

| Clause | Title / topic | Role vs USA SNL |
|--------|---------------|-----------------|
| Table 3 | Seismic Zone Factor Z | II=0.10 … V=0.36 — `india_hazard.ZONE_FACTOR_Z` |
| 6.4.2 | Design Ah + Sa/g spectrum | Ah=(Z/2)·(Sa/g)/(R/I); NLRHA target via `build_india_site_hazard` |
| 6.4.2.1 | Soil types I / II / III | Rock-hard / medium-stiff / soft |
| 6.4.7 | Site-specific spectrum | Allowed if ≥ 6.4.2 |
| 7.2.3 / Table 8 | Importance Factor (I) | Not ASCE Risk Category / Ie |
| 7.2.5 | Design Acceleration Spectrum | Points at 6.4.2 Sa/g |
| 7.6 | Equivalent Static Method | Linear ELF analogue (HR load_plan) |
| 7.7 | Dynamic Analysis Method | Parent of RSA / time history |
| 7.7.3 | Method choice + VB scale floor | Force scale when VB < V̄B; displacements: see 7.11.1.2 |
| 7.7.4 | Time History Method | Spectrum-compatible GM — **not** Ch.16 suite code |
| 7.7.5 | Response Spectrum Method | RSA |
| 7.8.2 | Design Eccentricity | Accidental torsion (no ASCE Ax) |
| 7.11.1 | Storey Drift Limitation | Parent |
| 7.11.1.1 | ≤ 0.004 h under VB, γ=1.0 | Replaces Table 12.12-1 / Cd·δe/Ie / Ch.16 2× limits |
| 7.11.1.2 | Dynamic disp. not scaled as 7.7.3 | Dynamic drift handling |

## Honest Ch.16 replacements (from excerpts only)

See `nlrha.india_authority.india_acceptance_rules()`:

- Drift limit **0.004 h** (7.11.1.1)
- Time-history **spectrum compatibility** (7.7.4) → `india_hazard` Ah target
- **Not** replaced: suite size 11, RotD100 floor, RC unacceptable counts, §16.1.2 relief

## Explicit found:false (do not fabricate)

- ASCE/SEI 41-23 NSP + AISC 342 hinge / IO-LS-CP tables (IS 800 §4.5 ≠ analogue)
- ASCE 7-22 §§16.2–16.4 suite acceptance numerics
- ASCE 7-22 §16.1.2 drift relief after NLRHA
- USGS MCE_R / NSHM disaggregation as India authority

See `nlrha/india_authority.py`, `nlrha/india_hazard.py`.
