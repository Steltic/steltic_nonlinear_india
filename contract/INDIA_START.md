# START HERE — Steltic Nonlinear India (SNL-IN)

You take a finished **steltic_india** HR design package and run the three nonlinear checks
(pushover scaffolding · IS 1893-oriented NLRHA · DDM GMNIA), then the four-analyses comparison.

> **Not for construction.** Every result must be checked and sealed by a licensed PE.
> India corpus only: your IS corpus, built in the Steltic hub from your own licensed BIS PDFs
> (see CORPUS_FIX_LLM_INSTRUCTIONS.md). Never invent ASCE→IS mappings;
> `found:false` is honest.

## Authority

| Topic | USA (steltic_nonlinear) | India (this fork) |
|--|--|--|
| Linear design package | steltic (AISC 360/341, ASCE 7) | **steltic_india** (IS 800, IS 808, `load_plan`) |
| Pushover / NSP | ASCE 41-23 + AISC 342 | **found:false** in India corpus — scaffolding + UNVERIFIED hinge_params until AHJ-accepted source retrieved |
| Response-history | ASCE 7-22 Ch.16 | **IS 1893 Part 1:2016 §7.7 / 7.7.4** (LIVE RAG → `nl_plan`); `ch16_params.json` = ASCE scaffolding only |
| Drift limit | Table 12.12-1 × 2 (Ch.16) | **IS 1893 §7.11.1.1** (0.004 h); no Cd/Ie |
| Drift relief (§16.1.2) | RC I–III may waive 12.12.1 | **found:false** — feedback drift loop ineligible unless `nl_plan.drift_relief_analogue` retrieved |
| DDM combinations | ASCE 7 §2.3 via `design_pipeline.combos` | **`cfg['load_plan']`** via steltic_india `india_loads` |
| Corpus | the USA corpus (ASCE / AISC) | **your IS corpus** (BIS documents, built in the Steltic hub) |

Canonical gates: `nlrha/india_authority.py`, `snl/india_collections.py`.
Collection map: `contract/IS_COLLECTIONS.md`.

## Interfaces (consume India HR packages)

Required in the package (same filenames as USA; contents from steltic_india):

- `cfg.py` — with `load_plan` (IS 875 + IS 1893 RAG evidence) and metric-or-kip geometry as produced by steltic_india
- `model_opensees.py`, `design/calc_package.json`, `design/member_schedule.csv`, `report.html`

Set:

```bash
export STELTIC_ENGINE_DIR=/path/to/steltic_india/steel_engine
export RAG_API_URL=http://127.0.0.1:<port>/query       # your IS corpus server (the hub sets it)
export INDIA_CORPUS_ROOT=/path/to/your/is_corpus
```

Do **not** assume AISC shape labels forever — India packages may use IS 808 designations
(MB/WB/…); fibre/section mapping must tolerate dual-path sections (see steltic_india Ipack).

## Per-job protocol (wave-1 minimum)

1. `python -m snl inspect <package.zip>`
2. One retrieval wave against your IS corpus (`search_engineering_standards`), written as
   `contract/QUERYING_IS_CORPUS.md` says: one document per call, the exact id when known, `fts` only to navigate.
   - `IS_1893_Part_1_2016`: exact_section `7.7`, `7.7.4`, `7.11.1`, `7.11.1.2`; `fts` "time history method" to navigate
   - `IS_800_2007`: exact_table `Table 4` (combinations: confirm the load_plan cites), exact_section `12.2.3`
   - Component / hinge sources: no IS document tabulates them → `found:false`, leave the red UNVERIFIED banner
   - The IS values the analyses use (IS 2062 Table 3, IS 18168 Table 1, IS 1893 Table 3 / Table 8 / 6.4.2 / 7.2.4,
     IS 800 Section 12) are fetched by `snl collect` itself (section 9 of that file); its transcriber only copies
3. Write `nl_plan.json` (job root or `nlrha/`) with `jurisdiction`, `retrieval[]`, optional `rules{}`
4. `python -m snl run … --steltic-engine $STELTIC_ENGINE_DIR`
5. Judge with retrieved clauses only; never quote ASCE Ch.16 numbers as India law

## Hard rules

1. Never invent a clause, drift-relief waiver, or hinge table from memory.
2. Never treat `nlrha/ch16_params.json` as India-authoritative (`india_authoritative=false`).
3. Never enable ASCE §16.1.2 drift relief without a retrieved India analogue.
4. Prefer live RAG every job (same philosophy as steltic_india `load_plan` / `india_seismic`).

## Hazard (do not assume USGS)

```bash
python -m nlrha hazard <steltic_india_package> --zone III --soil-type II \
  --importance 1.0 --R-factor 5.0 [--t1 1.0]
# writes nlrha/site_hazard.json from IS 1893 Table 3 + 6.4.2 Ah(T)
python -m nlrha scale <package> --target is1893
```

USGS path: `python -m nlrha hazard … --usgs --lat … --lon …` (scaffolding only).

## Package stub

`examples/India_package_stub/` — cfg / nl_plan / interface notes for steltic_india packages.
Metric helpers: `snl.india_units.apply_metric_geometry`.
