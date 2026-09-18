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
git clone <this repo> Steltic_nonlinear && cd Steltic_nonlinear
python3.12 -m venv .venv && . .venv/bin/activate        # openseespy: Python 3.10–3.12 only
pip install -e .                                        # openseespy, numpy, scipy, matplotlib; ground motions ship in records/
export STELTIC_ENGINE_DIR=/path/to/steltic_india/steel_engine  # India: load_plan combos via india_loads
python -m snl inspect examples/Ex22_SMF                 # read the design basis
python -m snl report  examples/Ex22_SMF                 # rebuild the four-analyses sheet from the shipped outputs (no analysis)
```

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

## Feedback loops back to HR Steel

Once the Chapter 16 run is complete, the **Feedback** tab (hub) or `python -m snl feedback <job>` offers three
re-design loops — design drift to the measured response (16.1.2 relief, RC I–III), resize by system role, mechanism
shaping through SCWB and panel zones — each with a reviewed change set, the brief HR Steel's agent applies, a
verification with the same analyses, and one button to make a verified candidate the design of record. See
`docs/README_feedback.md`.

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

`snl/` orchestrator + comparison · `pushover/`, `nlrha/`, `steltic_ddm/` the three engines (unchanged import names) ·
`records/` FEMA P-695 far-field set · `skills/` the SNL skill and the three constituent skills · `prompts/` Grok Bot set-up ·
`contract/DDM_START.md` · `docs/` engine READMEs, scoping documents, φ<sub>s</sub> sources, the two example narratives ·
`examples/Ex22_SMF` (6-storey RC IV SMF, all outputs, the AISC 342-verified job parameter file) and `examples/Ex18_R3`
(8-storey R = 3 X-braced, all outputs) · `tests/`.

## Tests

`python -m pytest tests -q` from the repo root (a few minutes; needs openseespy). `test_feedback.py`, `test_loop.py`
(against `tests/fake_hr.py`, a stand-in HR Steel server), `test_site_hazard.py` (canned USGS responses, no network) and
`test_design_criteria.py` cover the feedback loops, the site-specific hazard and the 16.1.4 document. `test_snl.py` covers packaging, the
identical viewer cores, zip unpacking, `snl report`, the `snl run` step selection with stubbed engines, and the
four-analyses sheet regenerated from both examples; `test_pushover.py`, `test_nlrha.py` and `test_ddm.py` are the three
engines' own smoke tests pointed at the packaged examples (the DDM Ex18 ingest/gate test needs `STELTIC_ENGINE_DIR`);
`test_viewer_core_*.py` renders a small frame through each engine's copy of the viewer core.

## License

MIT (see `LICENSE`, `NOTICE.md`). No specification text is included; clause and table numbers are retrieval targets for
Query file manager.

## Fibre mesh-convergence

Fibre is the default plasticity for NSP and NLRHA (`--plasticity fibre --member-nseg 4`).
DDM remains fibre GMNIA. Run a mesh ladder with a **10%** relative stop band:

```bash
python -m snl mesh-converge <job> --analyses nsp nlrha ddm --tol 0.10
```

See [`docs/FIBRE_MESH_CONVERGENCE.md`](docs/FIBRE_MESH_CONVERGENCE.md).
