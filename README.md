# steltic_nonlinear_india (SNL-IN) — India nonlinear checks on a steltic_india design package

India fork of [`Steltic/steltic_nonlinear`](https://github.com/Steltic/steltic_nonlinear) (USA ASCE 41 / ASCE 7 Ch.16).
**Do not modify the USA repo from this worktree.** Target publish: `Steltic/steltic_nonlinear_india` (bundle → Git manager).

| step | engine | India authority | outputs |
|---|---|---|---|
| **Pushover** | `pushover/` | **found:false** for IS NSP/hinge tables — ASCE 41/AISC 342 scaffolding + UNVERIFIED params until RAG/AHJ source | `pushover/*` viewers |
| **NLRHA** | `nlrha/` | **IS 1893 Part 1:2016 §7.7 / 7.7.4** via LIVE RAG → `nl_plan`; `ch16_params.json` = ASCE scaffolding only (`india_authoritative=false`) | `nlrha/*` |
| **DDM** | `steltic_ddm/` | Combinations from **steltic_india `load_plan`** (IS 875 / IS 1893 RAG), not hardcoded ASCE 7 §2.3 | `ddm_*` |
| **Comparison** | `snl/compare.py` | Same three-analysis + viewers architecture | `four_analyses.html`, hub |

Corpus: **`/workspace/engineering_rag_india`** only. Gates: `nlrha/india_authority.py`, `contract/INDIA_START.md`.

> **Prototype. Not for construction.** ASCE §16.1.2 drift relief is **found:false** on this fork (feedback drift loop ineligible unless `nl_plan.drift_relief_analogue` is retrieved). Every result must be sealed by a licensed PE.

## Critical difference from USA steltic_nonlinear

| | USA | India (this fork) |
|--|--|--|
| HR package | steltic (AISC / ASCE 7) | **steltic_india** (IS 800 / IS 808 / `load_plan`) |
| NLRHA code | ASCE 7-22 Ch.16 authoritative in `ch16_params.json` | IS 1893 via **live RAG**; Ch.16 file is scaffolding |
| Drift relief | §16.1.2 RC I–III | **found:false** — do not fabricate |
| STELTIC_ENGINE_DIR | `steltic/steel_engine` | **`steltic_india/steel_engine`** |


## Install

```bash
git clone <this repo> steltic_nonlinear_india && cd steltic_nonlinear_india
python3.12 -m venv .venv && . .venv/bin/activate        # openseespy: Python 3.10–3.12 only
pip install -e .                                        # openseespy, numpy, scipy, matplotlib; ground motions ship in records/
export STELTIC_ENGINE_DIR=/path/to/steltic_india/steel_engine  # India: load_plan combos via india_loads
# First India job: start from examples/India_package_stub (interface) or a real steltic_india package zip
python -m snl inspect examples/Ex22_SMF                 # USA regression fixture only (not India authority)
python -m snl report  examples/Ex22_SMF                 # rebuild the four-analyses sheet from the shipped outputs (no analysis)
```

## Engineering-standards RAG (required for India)

Point every retrieval at **`/workspace/engineering_rag_india`** (never USA `/workspace/engineering_rag`).
`nl_plan` / acceptance / hazard gates live in `nlrha/india_authority.py` and `contract/INDIA_START.md`.
DDM combinations come from the HR package `cfg['load_plan']` (IS 875 + IS 1893 LIVE RAG).

Local search / QFM JSON plans:

```bash
cd /workspace/engineering_rag_india
export PYTHONPATH=scripts
.venv/bin/python scripts/search.py exact_section 7.7.4 --doc IS_1893_Part_1_2016 --limit 2
.venv/bin/python scripts/search.py fts "Seismic Zone Factor" --doc IS_1893_Part_1_2016 --limit 2
.venv/bin/python scripts/search.py exact_section 5.4 --doc IS_800_2007 --limit 1
```

Set `RAG_API_URL` / `RAG_API_TOKEN` (and optionally `RAG_ALIASES_FILE=/workspace/engineering_rag_india/indexes/aliases.json`) to the India corpus server.

## Command line

    python -m nlrha hazard <package> --lat .. --lon ..   # site hazard -> nlrha/site_hazard.json
    python -m nlrha library <folder>                    # index a folder of .AT2 / CSV pairs
    python -m nlrha criteria <package>                  # 16.1.4 design criteria (docx + html)
    python -m snl feedback <job> [--loop ...] [--run]   # the three loops back to HR Steel

```
python -m snl run <package.zip | folder> [--out DIR] [--steltic-engine DIR] [--params job_hinge_params.json]
                  [--only pushover nlrha ddm] [--skip ...] [--parallel 2]
                  [--site-class D] [--risk-category IV] [--n-records 11] [--dt 0.01] [--integrator hht|newmark]
                  [--tail auto|fine_step|arclength|none] [--post-cap-ratio 0.5] [--no-block]
python -m snl report  <job folder>        # four_analyses.html + snl_summary.json + the viewer hub from what exists
python -m snl inspect <package.zip | folder>
python -m snl review  <job folder> [--focus "..."] [--no-standards] [--max-searches 8]   # the model's review (below)
```

`run` unpacks the zip next to itself (or into `--out`), then runs the three engines **in sequence, each in its own
process** (openseespy is a process singleton), logging to `<job>/snl_run.log` and `<job>/snl_run.json`. A failing step does
not stop the others. The individual engines remain callable on their own (`python -m pushover run …`, `python -m nlrha run
… / report …`, `python -m steltic_ddm run … / report … / viewer …`) with the options documented in `docs/README_pushover.md`,
`docs/README_nlrha.md` and `docs/README_ddm.md`. Typical times for a 250–700-member building on two cores: pushover 5–15 min,
NLRHA 30–90 min (dt 0.01 s), DDM 30–70 min.

## Site-specific ground motions (16.2)

`python -m nlrha hazard <package> --lat 34.05 --lon -118.25 --site-class D [--cs-period 1.0 0.3] [--t1 1.1]` pulls the
USA-scaffolding USGS ASCE 7-22 multi-period MCE<sub>R</sub> (not India authority) spectrum from the USGS design-maps service and the mean M / R / ε (with the
contributing faults) from the USGS NSHM disaggregation at the conditioning period, builds conditional (mean) spectra
(Baker 2011 form, Baker & Jayaram 2008 correlation), screens the site for near-fault sources and the pulse share that
implies, and writes `nlrha/site_hazard.json` + `site_hazard.html`. `nlrha run --target mcer|cs` then selects and
scales against the site-specific target, ranking records by spectral shape **and** M / R consistency with the
disaggregation (16.2.2), reserving the pulse share for records flagged `pulse` in their index. The library grows
beyond the shipped FEMA P-695 far-field set with `--records-set <folder> ...`: folders of PEER `.AT2` pairs (NGA-West2
downloads with their `_SearchResults.csv`) or two-column CSVs are indexed on the fly (`python -m nlrha library <folder>`).
See `docs/README_nlrha.md`.
**India:** prefer `python -m nlrha hazard <package> --zone III --soil-type II` (IS 1893 Ah via `nlrha.india_hazard`). USGS only with `--usgs --lat --lon` (scaffolding). Scale with `--target is1893`.


## Design criteria document (16.1.4)

`python -m nlrha criteria <package> [--project ...] [--engineer ...] [--reviewer ...]` — and every `snl run` — drafts
the Section 16.1.4 design criteria document from the package, `ch16_params.json`, the hinge parameters, the site
hazard, the selected suite and any results on file: scope, governing documents, hazard, ground motions, modelling,
acceptance criteria, the linear basis (16.1.2, including any drift relief), the 16.5 review scope, open items, the
retrieval log. Written as `design_criteria_16_1_4.docx` (for mark-up; no python-docx needed) and `.html`.

## The review (the model reads the run)

`python -m snl review <job>` — the **Review** tab in the hub — hands the model what the run measured and gets the
engineer's review back: a summary that opens with "IS 1893 (Part 1):2016 provides no acceptance criteria for
nonlinear analysis; results are for information.", what was measured, the DBE and MCE response (storey drifts with
the IS 1893 7.11.1.1 0.004 h linear-analysis limit for comparison only, base shear against VB and the elastic
Sa(T1)·W, ductility, member chord rotations against the IS 800 Section 12 joint-rotation capacity as reference,
column axial force against IS 800 7.1.2 Pd), the pushover, the DDM capacity, the design basis against the
design-criteria draft, what to change and why (ranked), open items. No pass/fail verdict (D7), no foreign design
basis (D3). `snl/review.py` gathers the evidence from the files in the job folder (`snl_summary.json`,
`nlrha/nlrha_package.json` and the per-level `nlrha/<DBE|MCE>/nlrha_package.json`, `pushover/pushover_package.json`,
`ddm_results.json`, `design/calc_package.json`, `seismic_calc.json`, `load_plan.json`, the criteria draft, the
COMPLETE gate's disclosures, any feedback loops) into one bounded document — every number from a file, nothing
invented — and the model may call one tool, `search_engineering_standards`, which posts to `RAG_API_URL` (in the
hub: the IS corpus bridge of `engineering_rag_india`, started for the run) with the `engineering_standards_IS*`
collections (IS 1893, IS 800, IS 18168, IS 2062, IS 808, IS 875), so the clauses it cites are read from the corpus
and cited with their page; a clause it could not find is marked UNVERIFIED. Outputs: `review.md`, `review.html`,
`review_transcript.json` (the evidence and every passage read).

The connection comes from the environment the hub sets for the run — `STELTIC_LLM_BASE_URL`, `_API_KEY`, `_MODEL`,
`_PROVIDER`, `_REASONING`, `_MAX_TOKENS` (OpenAI-compatible chat completions; OpenRouter reasoning control and
provider pinning when the base URL is OpenRouter; `<think>` spans and `reasoning_content` deltas both land in the
reasoning stream). Model `MOCK` writes the review offline from the evidence alone, still running the same standards
searches. While it works the step prints one JSON event per line — `reasoning`, `token`, `tool`, `tool_result`,
`milestone`, `status`, `usage` — which the hub shows the way it shows HR Steel and CFS: the model's text on the run
line, its reasoning in the separate box, one line per search. `--focus` puts the engineer's question first;
`--no-standards` skips the corpus; `--max-searches` caps the tool calls (8 by default).

The search carries the retrieval skill HR Steel's tool has (`snl/rag.py`), so a zero-hit answer is never left
for the model to interpret. Before the first search the server's `/healthz` says which documents the corpus on
this PC actually holds; that list goes into the model's instructions (*DOCUMENTS IN THE CORPUS — present … ;
ABSENT …*) and into the run log, and a search for an absent document is answered at once as a **corpus gap**
(install / update the IS corpus module, `engineering_rag_india`, or convert the document on its Convert tab under its
canonical stem — `IS_1893_Part_1_2016`, `IS_800_2007`, `IS_18168_2023` … — then Rebuild index), is not counted
against the budget, and makes one wide search across the IS documents that are present instead. A miss climbs a ladder before it may be a miss — as asked; without the
clause / chapter filter; the id as an exact lookup; any IS document — and the result says which rung and which
document supplied the passages, so the model cites the document the text is from. `review_transcript.json`
records every rung of every search.

## Feedback loops back to HR Steel

Once the Chapter 16 run is complete, the **Feedback** tab (hub) or `python -m snl feedback <job>` offers three
re-design loops — design drift to the measured response (16.1.2 relief, RC I–III), resize by system role, mechanism
shaping through SCWB and panel zones — each with a reviewed change set, the brief HR Steel's agent applies, a
verification with the same analyses, and one button to make a verified candidate the design of record. See
`docs/README_feedback.md`. The tab shows the re-design as the hub shows a design run: HR Steel's streamed text in
**Model output** and its reasoning stream in its own **Model reasoning** box (the loop relays the agent's
`reasoning` events as `hr_reason`, as it relays `token` as `hr_text`).

## The comparison sheet

`four_analyses.html` is data-driven: it reads `report.html` (design drift table, base shears), `design/calc_package.json`
(D/C), the three package files, and writes five sheets — the four verdicts, what each package answers, the same quantities
four ways (periods; design force vs effective yield strength; Ω vs Ω<sub>0</sub> vs λ<sub>u</sub>; MCE<sub>R</sub> roof
displacement δ<sub>t</sub> vs the record mean; storey drift design vs NSP vs suite mean/max against both limits;
deformation- and force-controlled components), the records / element checks / sweeps in full, and the disclosures read from
the outputs (tail status, post-capping ratio, integrator and time step, retried records, φ<sub>s</sub> statuses). Packages
that were not run are shown as *not run*. `snl_summary.json` carries the same numbers for the bot. The engineering
interpretation is the bot's narrative; `docs/ex18_four_analyses.html` and `docs/ex22_four_analyses.html` show what that
narrative looks like for a wind-governed R = 3 braced frame and a Risk Category IV SMF.

## Viewers

Every engine writes its 3-D viewer (three.js vendored, MIT; opens from disk) in the style of Steltic's `viewer_3d.html`:
same geometry, orbit controls, palette (grey elastic · yellow yielded · purple buckled brace · amber > IO/LS · red > CP ·
dark red beyond b), plastic-hinge dots and panel layout. The strip Steltic · Pushover · NLRHA · DDM in each viewer is a
module selector (greyed where the sibling file is missing) and `steltic_viewer_bundle.html` in the job root shows the four
in one page. One viewer core (`viewer_core.py/.html`) is kept as identical copies inside the three engines so each can still
be shipped alone; `tests/test_snl.py` asserts they match.

## Repo map

`snl/` orchestrator, comparison, the review (`review.py`, `llm.py`, `rag.py`) and the feedback loops · `pushover/`, `nlrha/`, `steltic_ddm/` the three engines (unchanged import names) ·
`records/` FEMA P-695 far-field set · `skills/` the SNL skill and the three constituent skills · `prompts/` Grok Bot set-up ·
`contract/DDM_START.md` · `docs/` engine READMEs, scoping documents, φ<sub>s</sub> sources, the two example narratives ·
`examples/Ex22_SMF` / `examples/Ex18_R3` (USA regression fixtures only) ·
`examples/India_package_stub/` (steltic_india interface + `nl_plan`) · `tests/`.

## Tests

`python -m pytest tests -q` from the repo root (a few minutes; needs openseespy). `test_feedback.py`, `test_loop.py`
(against `tests/fake_hr.py`, a stand-in HR Steel server), `test_site_hazard.py` (canned USGS responses, no network) and
`test_design_criteria.py` cover the feedback loops, the site-specific hazard and the 16.1.4 document; `test_review.py` drives the
review against a fake OpenAI-compatible server and a fake IS standards server (stdlib, no network, no model) on
`tests/india_nl_job.py`, the IN_Ex1 package with synthetic outputs in the India package shapes. `test_snl.py` covers packaging, the
identical viewer cores, zip unpacking, `snl report`, the `snl run` step selection with stubbed engines, and the
four-analyses sheet regenerated from both examples; `test_pushover.py`, `test_nlrha.py` and `test_ddm.py` are the three
engines' own smoke tests pointed at the packaged examples (the DDM Ex18 ingest/gate test needs `STELTIC_ENGINE_DIR`);
`test_viewer_core_*.py` renders a small frame through each engine's copy of the viewer core.

## License

MIT (see `LICENSE`, `NOTICE.md`). No specification text is included; clause and table numbers are retrieval targets for
Query file manager.

## Fibre mesh-convergence

Fibre is the plasticity for India NSP and NLRHA (always; member strains and chord rotations are recorded). For the USA regression fixtures the NSP default is fibre and the NLRHA default is ModIMK (`--plasticity imk`).
DDM remains fibre GMNIA. Run a mesh ladder with a **10%** relative stop band:

```bash
python -m snl mesh-converge <job> --analyses nsp nlrha ddm --tol 0.10
```

See [`docs/FIBRE_MESH_CONVERGENCE.md`](docs/FIBRE_MESH_CONVERGENCE.md).
