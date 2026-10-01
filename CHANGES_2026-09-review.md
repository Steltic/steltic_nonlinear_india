# steltic-nonlinear-india 0.3.1: USA sync and first-pass India review (2026-09-27)

Branch `fix/2026-09-review`, based on the delivered zip (India 0.2.0, fork of USA 9607577). NL-24..NL-27 (gold-batch
findings, section 3) are on `review-fix-2026-09`.

## 1. USA updates ported (USA-SYNC commits; full table in `docs/USA_SYNC_REPORT.md`)
- **Review:** `snl review` with review.md and the Feedback reasoning box.
- **Standards search:** `/healthz` handling, corpus-gap answers, the miss ladder, the shared retrieval policy (exact id first, top_k 20) and whole exact passages.
- **`snl revise`** with grounded reports.
- **NLRHA viewer:** per-frame hinges.
- **Collect-before-Run:** deterministic retrieval, transcript, quote/value checks, gate file and three strikes.

**Adapted to IS only (owner rulings D3/D6/D7):**
- Retrieval uses the India collections only.
- Collect gathers only IS values:
  - IS 2062 fy/fu;
  - IS 18168 Ry/Ru, as reference;
  - IS 800 §12 rotations, as reference only;
  - IS 1893 Z, Sa/g and I;
  - 7.2.4 damping.
- Hinge backbones are labelled as modelling assumptions.
- Reviews give no verdict and open with the D7 sentence.
- The ASCE 41 / AISC 341/342 lookups and the RBS guide were skipped as US-only.

## 2. First-pass review and fixes (NL-1..NL-23; full list in `docs/NL_REVIEW.md`)
**Critical:**
- BOX columns crashed every box job, and fy was a single value. Now fy is per member, by IS 2062 thickness band (NL-4).
- Replayed HR elements carried N-mm values into the kip-in model (NL-5).
- EBF links were elastic in all analyses. They are now nonlinear, using the IS 18168 11.2 shear yield (NL-10).
- DDM earthquake combinations had no lateral load (NL-13).
- NL gravity was a private idealisation. It now replays the HR engine's own load states, and the gate checks against the HR member forces (NL-14).
- Gold-set smoke-run failures (NL-15):
  - roof springs;
  - partial-snow and crane patterns;
  - the Corotational gate.

**High:**
- Re-vendored the India modules, with a path-resolving check (NL-1).
- Added IS 18168 to the collections and resolved the corpus root (NL-3).
- V̄B, R and W are now taken per direction from the HR package (NL-6).
- Replaced the USA default parameter file with an India file (NL-7).
- Collect covers every grade and system part (NL-8).
- Added an agent-as-transcriber mode, `snl collect --prepare / --answers` (NL-9).
- The COMPLETE gate is more honest (NL-17).
- Fixed the spurious-mode false positive (NL-18).

**Medium/Low:**
- India NLRHA viewer (NL-11).
- Pushover stops at 0.8 Vmax (NL-12).
- DDM gate noise floor (NL-16).
- `snl run` India options (NL-19).
- Test-order fix (NL-20).
- Collect accepts trailing-zero decimals (NL-22).

**Runtime methods, disclosed in every report (NL-21):**
- Gravity-only members are elastic, with a P-M yield check. Flagged members are promoted to fibre, and the gate refuses while any flagged member stays elastic.
- NLRHA records are trimmed to the 5–95 % Arias window.
- Validated against full-fidelity runs:

  | Check | Difference |
  |---|---|
  | Ex3 NLRHA drift | +0.3 % |
  | Ex3 NLRHA base shear | +0.7 % |
  | Ex1 pushover Vmax | 0 % |
  | Ex1 NLRHA drift, two records | ≤ 1 % |

**Batch tooling:** `scripts/run_gold_batch.sh`, a resumable batch for the 15 India HR gold buildings (NL-23).

## 3. Gold-batch findings (NL-24..NL-27; docs/NL_REVIEW.md #38-42)
**Critical:**
- DDM deck beams were Corotational inside the rigid diaphragm. The sag of a pinned girder became catenary tension:
  - IN_Ex11 stopped at λ 0.977;
  - the gym girder B-1.2 was 1.018, and Ex14's 1.08;
  - after yield, lateral-case λ values were inflated (gym 4-8.8).

  Those beams now use P-Delta, like the HR design and the NL pushover and NLRHA (NL-24). This changes every India DDM result.

**High:**
- DDM solver: an algorithm ladder, a tolerance fallback, step cuts and an arc-length rescue. A numerical stop with stiffness left is SOLVER_FAILURE and blocks COMPLETE; the old behaviour reported it as NO_LIMIT_POINT (NL-24). This closes the former open item "DDM solver robustness near first yield".
- The B-1.2 member forces are now interpolated to λ = 1 exactly. Before, they came from the first step past 1, up to 5 % beyond it (NL-25).
- GMNIA fibre I-sections now carry the root fillets, so A, Ix and Zp match IS 808 within 0.4 %. The plate model was 2-6 % low. IN_Ex5's DDM transfer gate goes from 1.053 (refused) to 1.001. This is DDM only; the pushover and NLRHA sections are unchanged (NL-26).

**Batch:** step markers now record DDM_CODE. The batch re-runs any DDM that predates it: inline for unfinished jobs, and in a refresh pass at the end for finished ones. `STOP_BATCH` stops the batch cleanly (NL-27).

**Checked:** the GMNIA fy is characteristic IS 2062 by thickness band, and γm0 is applied only in B-1.2.

## Open (see docs/NL_REVIEW.md)
- Ground-motion selection and scaling use the ASCE 7 Ch.16 method, labelled as information. This is an EOR decision.
- The NL model is rigid-diaphragm where HR declared the diaphragm flexible.
- There is no India pushover 3-D viewer.
- g is 386.4 vs 386.09 (0.08 %).

## IS corpus (not distributed)

The BIS standards corpus is not published with this repo, because the standards are copyright BIS. Build your own from your licensed PDFs in the Steltic hub (first pass, Docling). Then have a frontier LLM fix it using `CORPUS_FIX_LLM_INSTRUCTIONS.md`, and import the result back into the hub. See README, "IS corpus (standards grounding)". Without a corpus the engine still runs: retrievals return found:false, and COMPLETE needs EOR records.

## Commits (oldest first; subjects only — hashes change when the branch is replayed onto GitHub)
- USA-SYNC bd8ba3a: snl review + Feedback-tab reasoning box, 0.3.0, adapted for India: IS corpus, no verdict
- USA-SYNC 402c61a: search reads /healthz, corpus gap, ladder, 0.3.1, adapted for India: IS stems
- USA-SYNC 41a3e4d: NLRHA viewer paints hinges at the current frame, ported as-is
- USA-SYNC c15237e: snl revise, grounded reports from review.md, adapted for India: IS clauses, hinge groups as modelling assumptions
- USA-SYNC f22d16b: shared retrieval policy (exact id first), no default search cap, top_k 20, adapted for India
- USA-SYNC deb858f+51a089f+de7e281: Collect specification values before Run, adapted for India: IS values from the IS corpus, hinge backbones as modelling assumptions
- USA-SYNC 3629a4b: Collect passes exact lookups whole (EXACT_MAX_CHARS 60k), absent row asked once more, adapted for India
- NL-1: re-vendor the shared India modules from steltic_india 3ec586a; check_vendored resolves the HR checkout like HR/CFS
- NL-2: DDM load_plan tests follow the current steltic_india contract; Ex18 USA fixture tests need the USA engine
- NL-3: IS 18168 in the India collection map; corpus root resolves like steltic_india (env, sibling checkout, fallback)
- NL-4: read the HR package's sections and steel -- built-up BOX columns and per-member grade / fy
- NL-5: convert the raw replayed elements of an N-mm HR model in the Stage-B bridge (EBF links, trusses, roof springs)
- NL-6: India basis per direction (V-bar_B, R_x / R_y, Ta) and mass = the HR engine's W
- NL-7: India parameter file -- IS values or labelled modelling assumptions, no US defaults; damping reference IS 1893 7.2.4
- NL-8: collect every grade the design uses (IS 2062 and IS 1161 tube grades) and every IS 800 / IS 18168 rotation reference
- NL-9: SCRIPTED transcriber for snl collect -- an agent (or a person) supplies each value with its quote, same checks
- NL-10: EBF links are nonlinear -- IS 18168 11.2 shear yielding on the fibre link; link rotation vs 12.3.3.1 as reference
- NL-11: India NLRHA viewer (nlrha/nlrha_viewer_3d.html) -- DBE / MCE suites, no IO/LS/CP, no verdict
- NL-12: India pushover stops once the descending branch is captured (0.8 Vmax, beyond 2 x the target estimate)
- NL-13: DDM earthquake sweeps get the static IS 1893 storey-force pattern; India combination set for the GMNIA
- NL-14: gravity from the HR engine's own load states for the pushover, NLRHA and DDM; DDM gravity gate against the HR forces
- NL-15: zeroLength springs, patterned snow/crane/vertical-EQ gravity, P-Delta gate
- NL-16: DDM gravity gate noise floor (2 % of member plastic capacity)
- NL-17: COMPLETE gate honesty (collected IS values, HR gravity, EBF links); India report wording
- NL-18: modal asks for no more modes than the model has real mass DOFs
- NL-19: snl run passes India options (no ASCE site class, fibre NLRHA)
- NL-20: panel-zone pushover test independent of test order
- NL-21: elastic gravity members with a yield check, NLRHA records trimmed to 5-95 % Arias
- NL-22: snl collect accepts decimals with trailing zeros (zone II Z = 0.10)
- NL-23: scripts/run_gold_batch.sh -- resumable India gold NL batch, smallest job first
- NL-24: DDM deck beams P-Delta (no catenary against the rigid diaphragm); solver ladder, arc-length rescue, SOLVER_FAILURE
- Docs: NL-24 findings, gold NL status for IN_Ex11 (3 units COMPLETE), DDM re-run instructions, IN_Ex5 fillet decision
- NL-25: IS 800 B-1.2 member forces interpolated to lambda = 1 exactly
- NL-26: DDM fibre I-sections with root-fillet fibres -- A, Ix, Zp = IS 808 catalogue (IN_Ex5 transfer gate)
- NL-27: gold batch re-runs DDM results that predate DDM_CODE (NL-26), refresh pass at the end, STOP_BATCH file
- Docs: NL-25..NL-27, IN_Ex5 fillet decision closed, batch switch to run_repo2 @ aa3009b, CHANGES closes the DDM robustness item
- NL-28 (Windows): NLRHA index package paths use '/' separators
- NL-28: gold batch honours $GOLD_NL/SKIP_JOBS (jobs offloaded to another machine are never started or DDM-refreshed)
- NL-29: NLRHA pools the DBE + MCE records (22 tasks, per-record progress); gold batch STEPS / NL_REV / empty RAG_API_URL -- owner's PC package
- Corpus: the IS corpus is the user's own; users build it in the Steltic hub
- CORPUS_FIX_LLM_INSTRUCTIONS.md: the owner's instructions for the corpus fix pass (replaces the placeholder)
- CORPUS_FIX_LLM_INSTRUCTIONS.md: final version (matches the hub's bundled corpus module: validate probes, optional scripts/*.json, Import fixed corpus tab)
- Query instructions: contract/QUERYING_IS_CORPUS.md in the Review prompt; the tool takes the canonical stems; INDIA_START / bootstrap / DDM notes point to it
- NL-30: DDM sweeps that stop numerically (SOLVER_FAILURE) are re-run with dlam/2 then dlam/4 before they can block the gate; `steltic_ddm retry <job>` re-runs only those combinations in an existing ddm_results.json
