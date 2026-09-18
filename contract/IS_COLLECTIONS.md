# India NL RAG collection → corpus stem map

Canonical map: `snl/india_collections.py` (+ `snl/india_collection_stems.json`).
Corpus: `/workspace/engineering_rag_india`.

| collection= (either `engineering_standards_` or `engineering_standard_` prefix) | stem |
|---|---|
| `…_IS800` | `IS_800_2007` |
| `…_IS808` | `IS_808_2021` |
| `…_IS875_P1` … `…_IS875_P5` | `IS_875_Part_1_2026` … `IS_875_Part_5_1987` |
| `…_IS1893` / `…_IS1893_P1` | `IS_1893_Part_1_2016` |

**Mandatory every NL job:** `IS1893` (§7.7 / 7.7.4 / 7.11.1) before quoting acceptance.
Load stems remain the HR package's responsibility via `load_plan`.

Never point this agent at the USA corpus (`/workspace/engineering_rag`).
