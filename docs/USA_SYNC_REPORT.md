# USA → India sync, 2026-09-26

Branches `usa-sync-2026-09` in `work/steltic_nonlinear_india` (8 commits) and `work/steltic_hub_india` (4 commits).
Every commit message is `USA-SYNC <sha>: <what>, adapted for India: <how>`, with the requested trailer.

## Fork points (verified by diffing trees)

| India repo | Stated base | Found |
|---|---|---|
| steltic_nonlinear_india 0.2.0 | USA 0.2.0 (8e83ff3 / 9e83ff3 / 9607577) | **9607577**: `snl/loop_ui/styles.css` is byte-identical to 9607577 (Brand Orange) and `snl/loop.py` carries b94e4e4 (differs by one India line). 181/226 USA files identical. The rest are India WP4 / D6 / D7 changes (nlrha, pushover, steltic_ddm, snl/feedback, compare, tests) plus India-only files (snl/vendor_steltic_india/, india_* modules, usa_reference/, contract/*). |
| steltic_hub_india 0.1.0 | USA c33c5c2 | **9997de4** in substance, not c33c5c2: `runners.py` and `admin/plans.py` are identical to 9997de4, `manifest.py` has `run.continues`, the bundled servers have the no-cache middleware. f1b1708 and 9997de4 were already in, except the Nonlinear Review tab. Other differences are India identity (port 8301, data dir, catalog ids, private repos) and India variations / probabilistic. |

## Port table: steltic_nonlinear

| USA | What | Result | Why / how | India commit |
|---|---|---|---|---|
| 9607577 | Feedback tab, Brand Orange palette | already in | styles.css identical at the fork | none |
| b94e4e4 | Windows loop state.json retry | already in | loop.py carries it | none |
| bd8ba3a | `snl review`, llm.py, rag.py, Feedback reasoning box, 0.3.0 | **adapted** | IS collections only (IS1893 / IS800 / IS18168 / IS2062 / IS808 / IS875); reviewer prompt IS-only with **no verdict**; opens with the D7 sentence; drift vs 7.11.1.1 for comparison only; IS 800 §12 rotations as reference; gather() reads the India package shapes (DBE / MCE level packages, seismic_calc, load_plan, complete_gate); India MOCK. New tests/india_nl_job.py fixture. | 3a62bf6 |
| 402c61a | /healthz, corpus gap, miss ladder, 0.3.1 | **adapted** | IS corpus stems and titles; gap note points at engineering_rag_india; policy text with IS ids | f4ebe36 |
| 41a3e4d | NLRHA viewer per-frame hinges | **ported as-is** | Applied with offsets over the India run.py additions. The India NLRHA path writes no nlrha_viewer_3d.html, so the change only shows on the US-scaffolding path. | 62f0098 |
| c15237e | `snl revise` | **adapted** | Grounds the IS clauses (1893 7.7.4 / 7.11.1.1 / 6.4.2, plus the system's IS 800 §12 clause). Hinge groups are **not searched** and are recorded as modelling assumptions; the ASCE 41 / AISC 342 searches were skipped. `_first_real_hit` now checks the source document, which the USA code did not. | bbddf25 |
| f22d16b | Shared retrieval policy, exact id first, no search cap, top_k 20 | **adapted** | India RETRIEVAL POLICY (which IS document governs what); `_DOCNAME_RE` strips IS designations; a bare "Table 3" is treated as an id | 729a20e |
| deb858f + 51a089f + de7e281 | Collect before Run (3 cuts) | **adapted, one commit** | The third cut replaced the first two within 30 h, so the de7e281 design was ported directly. The machinery is kept: deterministic prefetch, rows decided from the building, transcribe-only model, quote/value checks, transcript, evidence, three strikes, gate file / .partial. It collects **IS values only**: IS 2062 T3 fy/fu, IS 18168 T1 Ry/Ru (reference), IS 800 §12 rotation (reference only), IS 1893 T3 Z / 6.4.2 Sa/g / T8 I, 7.2.4 damping. Each value is cross-checked against the India engine constants and the package. Hinge backbones are labelled modelling assumptions and `verified` stays false. The AISC 341 / 342 / ASCE 41 PLAN, the RBS reading guide and the IO/LS/CP validation were skipped as US-only. Also: standards.py, grounding.py (+ `collected` state, IS wording), pushover `_copy_params`, and provenance blocks on the India report pages. | e795838 |
| 3629a4b | Exact lookups whole (60k), absent row re-asked | **adapted** | IS 2062 Table 3 is 57,071 chars and the E 250 row sits past the old 2,500 cap. Material is now transcribed from it. | 88fbb58 |

## Port table: steltic_hub

| USA | What | Result | Why / how | India commit |
|---|---|---|---|---|
| f1b1708 | One port per module, Stop grace, CLI events, run.llm, NL Review tab, 0.2.1 | **partly already in; Review tab adapted** | Everything except the Review tab was in the baseline. The Review tab uses `{server.engineering_rag_india}` with IS wording and no verdict. | fd1b3fe |
| 9997de4 | Admin batch resume, run.continues, QFM bridge, 0.2.2 | already in | plans.py and manifest are identical; the India bridge already accepts any indexed stem | none |
| fbb5508, 30dbaa3 | HR Revise tab added, then removed | skipped | Net effect is a JSON re-escape of the US HR catalog. Their surviving hub tests are in cf81db7's port. | (7d6ba3a) |
| cf81db7 | Tab actions, Revise on NL Run, running rail, unix launcher | **adapted** | Revise action queries the IS corpus. Hazard / criteria / mesh tabs stage `{out.steltic_india}`. Added `unix/steltic_india.sh` (+ .desktop, install.sh): India data dir, port 8301, India names, and `logs/` created first (the US script misses this). | 7d6ba3a |
| b97999a | Actions declare fields; no 8-search default | **adapted** | Revise takes `["job"]`; test uses the India Run flags | c9a2cc3 |
| 9e0f596 | Collect-before-Run gate | **adapted** | `run.requires hinge_params_collected.json`. The Collect action (IS corpus, job + package) replaces Revise. Its note lists the IS values and says hinge backbones are modelling assumptions. | 70f075c |

## Tests

| Repo | Baseline | Final |
|---|---|---|
| steltic_nonlinear_india | 196 passed, 4 skipped | **274 passed, 4 skipped** |
| steltic_hub_india | 114 passed (after `pip install fastapi`; it failed to import before) | **124 passed** |

The 4 NL skips need `STELTIC_ENGINE_DIR` / a steltic_india checkout. With the current `/home/claude/work/steltic_india`, the same 4 tests **fail identically on the baseline and the branch**:
- `LoadPlanError` on the fixture load_plans;
- `check_vendored`: 8 vendored files have drifted.

So these failures predate the sync.

## Checked live (India corpus, 127.0.0.1:8765)

- **rag search:** policy lookups resolve (Table 3, 7.11.1.1, 12.11.1, IS 18168 Table 1). IS 2062 Table 3 comes back whole at 57,071 characters.
- **`snl revise`:** grounded 4 of 4 IS clauses on the IN_Ex1 job.
- **`snl collect` (MOCK):** fetched all five IS groups and wrote the gate file.
- **Not checked:** no LLM provider is available here. Transcription is tested with a scripted model quoting real converted IS cells (tests/fixtures/collect_tables_india.json).

## For the next review (India NL)

1. **No NLRHA viewer for India jobs.** The India NLRHA path (`_run_india` / `_finish_india`) writes no `nlrha/nlrha_viewer_3d.html`, but the hub catalog's Viewers and compare.py's file list point to it.
2. **Hinge path still uses US steel.** The repo `pushover/hinge_params.json` material is still A992 (Fy_ksi 50, Ry 1.1), and hinge_models uses it for the hinge-only path and panel-zone Vy. Only a collected file replaces it with the IS 2062 fy.
3. **Vendored modules have drifted.** `snl/vendor_steltic_india` differs in 8 files from the current steltic_india, and the engine-dependent DDM tests fail with LoadPlanError.
4. **Collection map is incomplete.** `snl/india_collections.py` and `contract/IS_COLLECTIONS.md` lack IS 18168 and hard-code `/workspace/engineering_rag_india`.
5. **Hub launcher installs the US package.** Not an NL issue: the India hub's `windows/Steltic.ps1` installs the PyPI `steltic-hub` (the US package) when not run from a checkout.
