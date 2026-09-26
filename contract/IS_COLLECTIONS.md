# India NL RAG collection → corpus stem map

Canonical map: `snl/india_collections.py` (+ `snl/india_collection_stems.json`, regenerated from it; a test keeps
them equal).

Corpus root: `$INDIA_CORPUS_ROOT` (or `$ENGINEERING_RAG_INDIA`), else a sibling `engineering_rag_india` checkout
next to this repo, else `/workspace/engineering_rag_india` -- the same resolution as steltic_india (L-08).
The aliases file is `$RAG_ALIASES_FILE`, else `<corpus root>/indexes/aliases.json`. Live retrieval goes through
`RAG_API_URL` (the corpus's `scripts/serve_http.py`, e.g. `http://127.0.0.1:8765/query`).

| collection= (either `engineering_standards_` or `engineering_standard_` prefix) | stem |
|---|---|
| `…_IS800` | `IS_800_2007` |
| `…_IS808` | `IS_808_2021` |
| `…_IS1161` | `IS_1161_2014` |
| `…_IS2062` | `IS_2062_Part_1_2025` |
| `…_IS18168` | `IS_18168_2023` (owner ruling D2: Table 1 Ry / Ru, 12.3.3.1 link rotation, 5.5 Ω) |
| `…_IS875_P1` … `…_IS875_P5` | `IS_875_Part_1_2026` … `IS_875_Part_5_1987` |
| `…_IS1893` / `…_IS1893_P1` | `IS_1893_Part_1_2016` |

**NL collections** (`NL_COLLECTIONS`: collect / review / revise): IS 1893, IS 800, IS 18168, IS 2062, IS 808.
**Mandatory every NL job:** `IS1893` (6.4.2 / Table 3 / Table 8 / 7.2.4 / 7.7.4 / 7.11.1) before quoting any value.
Load stems remain the HR package's responsibility via `load_plan`.

Never point this agent at the USA corpus (`/workspace/engineering_rag`).
