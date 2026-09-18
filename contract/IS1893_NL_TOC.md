# IS 1893 (Part 1) : 2016 — NL-relevant anchors (India RAG)

Corpus stem: `IS_1893_Part_1_2016` under `/workspace/engineering_rag_india`.

These ids resolve in the India index (titles verified). **Always re-retrieve LIVE** before
quoting body text in a deliverable — Docling page merges can pollute neighbouring body text.

| Clause | Title / topic | Role vs USA SNL |
|--------|---------------|-----------------|
| 7.2.3 | Importance Factor (I) | Not ASCE Risk Category / Ie — do not invent RC↔I maps |
| 7.2.5 | Design Acceleration Spectrum | Site / spectrum basis (with zone factor Z etc. via RAG) |
| 7.6 | Equivalent Static Method | Linear ELF analogue (HR load_plan) |
| 7.7 | Dynamic Analysis Method | Parent of RSA / time history |
| 7.7.3 | Dynamic analysis may be performed by either… | Method choice |
| 7.7.4 | Time History Method | Closest NLRHA-style hook — **not** ASCE 7 Ch.16 suite code |
| 7.7.5 | Response Spectrum Method | RSA |
| 7.8.2 | Design Eccentricity | Accidental torsion (no ASCE Ax) |
| 7.11.1 | Storey Drift Limitation | Parent |
| 7.11.1.1 | (via india_seismic) ≤ 0.004 h under VB, γ=1.0 | Replaces Table 12.12-1 / Cd·δe/Ie |
| 7.11.1.2 | Dynamic displacements not scaled as 7.7.3 | Dynamic drift handling |

## Explicit found:false (do not fabricate)

- ASCE/SEI 41-23 NSP + AISC 342 hinge tables
- ASCE 7-22 §§16.2–16.4 suite acceptance numerics (11 motions, RotD100 floor, 2×12.12-1, RC unacceptable counts)
- ASCE 7-22 §16.1.2 drift relief after NLRHA
- USGS MCE_R / NSHM disaggregation as India authority

See `nlrha/india_authority.py`.
