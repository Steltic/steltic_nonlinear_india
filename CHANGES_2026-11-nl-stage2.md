# steltic-nonlinear-india — 2026-11: stage 2, step 0 (re-run tooling)

Branch `fix/2026-11-nl-stage2` from `main` (9c1b656). Code, tests and this file only; no result files. Nothing here
changes how an analysis model is built or solved. Two things change what is recorded: the DDM time limit (below) and
the journal / cache keys, which now cover more input files. Journals and record caches written before this branch
therefore do not match any more, and stage 2 starts every analysis afresh.

## DDM sweep time limit as a compute budget (`steltic_ddm/cli.py`, `report_ddm.py`, `nlrha/india_authority.py`)

- The time limit for a sweep is now 2,400 s on the reference machine (the owner's PC) multiplied by the machine's speed
  factor:
  - the owner's PC: factor 1.0, limit 2,400 s;
  - the 2-core box: factor 1.6, limit 3,840 s.
  The NL-30 smaller-step retries get 2× and 4× that, as before.
- The factor comes from `--speed-factor` on `run` and `retry`, or from `$SNL_SPEED_FACTOR`; without either it is 1.0.
  An explicit `--time-limit` is used as given, and its reference-machine equivalent (the limit divided by the factor)
  is recorded with it.
- `ddm_results.json` options record:
  - `speed_factor`;
  - `time_limit` (the limit used);
  - `time_limit_base` (the reference-machine budget);
  - `time_limit_basis` (the same in words).
  Every sweep result also records `time_limit_s`, the limit of the step size that produced it, and `speed_factor`.
  Every retry row records its own `time_limit_s`.
- When a `retry` or a B-1.2 refresh re-runs stored sweeps, it rescales the stored budget to the current machine. An
  October output has no factor, so it counts as 1.0. Its 2,400 s therefore becomes 3,840 s on the box. A sweep that
  stops on its time limit ("no limit point") can then be compared with October.
- The report shows the limit, the reference-machine budget and the factor. The completeness gate checks the
  reference-machine budget against 2,400 s. Before, it compared the raw limit, which flagged a short budget on a fast
  machine and missed one on a slow machine.
- `SNL_SPEED_FACTOR` is a scheduling setting, not a model setting, so it is not in the pushover or NLRHA keys. The
  DDM journal key holds the sweep options, the limit among them.

## Every input file in the journal and cache keys (`snl/checkpoint.py`, `pushover/cli.py`, `steltic_ddm/cli.py`, `nlrha/cli.py`)

- `snl.checkpoint.hr_digest` covers every input file of a job:
  - `model_opensees.py`, `cfg.py` and `load_plan.json`;
  - `seismic_calc.json` and `design_of_record.json`;
  - every file under `design/`;
  - the NL plan (the job's, and the parent folder's as `../nl_plan.json`, as the fy reading takes them);
  - `hinge_params_collected.json`.
  A file that appears or disappears also changes the digest.
- The pushover journal, the DDM journal and the NLRHA record cache all use this digest together with the HR gravity
  states. The NLRHA key also covers `nlrha/site_hazard.json`.
- The DDM writes its own block into `design/calc_package.json` (`ddm_analysis`), with a `.pre_ddm.bak` backup beside
  it. The digest leaves both out, so the DDM's own write is not counted as an input change.
- Every key now also covers the section tables the NL reads: `is808_shapes.csv`, `is1161_tubes.csv` and
  `aisc_shapes.csv`, taken from `$IS808_CSV` / `$AISC_CSV`, the engine's copies and the NL's own copies.

## Orchestrator (`scripts/nl_orchestrate.py`)

- **Input fingerprint and `refresh`.**
  - A finished step stores the fingerprint of what it read:
    - the job's input digest;
    - the HR engine;
    - the analysis code;
    - for analysis and report steps, also the HR gravity states (their content, not their provenance fields) and the
      section tables.
  - A started step also stores the fingerprint it began with.
  - `refresh` compares these fingerprints with the files now on disk:
    - **Input change:** the step and every step after it go back to pending.
    - **Engine change only:**
      - gravity and the DDM go back to pending, because the DDM reads the engine's load combinations directly;
      - the pushover, NLRHA and report steps go to `recheck`. After gravity runs again, each is done again without a
        run if its gravity states and section tables are unchanged; otherwise it is pending.
    - **Gravity states or section tables changed** under a finished analysis: that analysis goes back to pending.
    - **Analysis code changed:** reported only, unless `--include-code` is given.
    - **No fingerprint** (the step finished before this branch): the step goes back to pending.
  - Other options: `--engine` points the queue at another engine, and `--dry-run` shows the changes without making them.
  - Before a step re-runs, its old journals or record cache are moved to `<dir>.before_refresh_<time>`, not deleted.
    This way a fresh journal's counters are not read as lost progress.
- **Peak memory per chunk.** `_exec` records the peak resident memory of the analysis and every process it waited
  for, including a command killed at the timeout. The value appears in:
  - the chunk record (`peak_rss_mb`);
  - the runtime log (`peak_rss=…MB`);
  - `status` (the peak over the step's chunks).
- **Per-job options.** `plan --job-args "JOB:KIND=ARGS"` adds options to one analysis of one job. JOB and KIND accept
  `*` wildcards. An option already in the command is replaced, not repeated. A spec that matches no step is an error.
  Example: `--job-args "IN_Ex19*:pushover=--dirs Y --tail none"`.
- **`plan --speed-factor F`** writes `SNL_SPEED_FACTOR` into the queue's environment, so the DDM steps get the
  compute-budget limit. `plan` prints the resulting limit.
- **`sync --from <gold jobs> --to <work jobs>`** is pure Python; rsync is not on the box. For each job it:
  - copies HR files that are new or changed at the source, keeping their file times;
  - removes HR files that are no longer at the source;
  - never copies, replaces or removes NL outputs (`NL_OUTPUTS`, matched at any depth, so a unit's own outputs are kept
    too);
  - handles `design/calc_package.json` by HR content. If only the DDM block differs, the work copy is kept. If the HR
    content changed, the gold copy replaces it, and the stale `.pre_ddm.bak` beside it is removed;
  - leaves alone any job folder that exists only in the work tree;
  - writes `.nl_sync.json` (source, time, changes, input digest).
  The source is only read. `--dry-run` lists the changes. Run `refresh` after a `sync`.

## Tests

`tests/test_stage2_2026_11.py`, 15 tests:
- the compute budget and how it is resolved, rescaled, recorded per result and per retry, reported and gated;
- each input file changing every key, including the site hazard for the NLRHA and the section tables;
- the DDM's own write into the calc package not changing any key;
- the peak memory of a real 120 MB child process, and the peak in the chunk record and the log;
- `--job-args` and `--speed-factor`;
- `refresh` after an HR change, an engine change (states the same, then different), a code change, and a partly run
  step;
- `sync` (dry run, NL outputs kept, the calc package, removals, the gold left unchanged), and `sync` followed by
  `refresh`.

Full suite, with `STELTIC_ENGINE_DIR` set to the HR engine: 530 passed, 6 skipped. On `main` it was 515 passed,
6 skipped.
