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
- The DDM writes its own block into `design/calc_package.json` (`ddm_analysis`), rewriting the whole file in its own
  indentation, and leaves a `.pre_ddm.bak` backup beside it. The digest and `sync` therefore compare this file as
  canonical JSON without the block, whether the block is there or not, and leave the backup out. The DDM's own write
  is thus not counted as an input change. The first real end-to-end check showed that normalising only the copy that
  has the block reset finished steps.
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
  - removes a file only when the previous sync of the job brought it in (`.nl_sync.json` lists it) and the source no
    longer has it. NL files under names the list does not know (a log, a "before" copy) are therefore never removed.
    A dry run against the sandbox copies found such files, for example `pushover_before/` and `regress_*.log`;
  - never copies, replaces or removes NL outputs (`NL_OUTPUTS`, matched at any depth, so a unit's own outputs are kept
    too);
  - handles `design/calc_package.json` by HR content. If only the DDM block differs, the work copy is kept. If the HR
    content changed, the gold copy replaces it, and the stale `.pre_ddm.bak` beside it is removed;
  - leaves alone any job folder that exists only in the work tree;
  - writes `.nl_sync.json` (source, time, changes, input digest).
  The source is only read. `--dry-run` lists the changes. Run `refresh` after a `sync`.

## The PC runner (`scripts/run_stage2.py`, `windows/Run-Stage2.ps1` / `.bat`, `RUN_STAGE2.md`)

The owner runs every stage-2 production analysis on his PC (Windows, 12 workers). The runner does it in one command
and can be resumed.

- **`run --gold <bundle .zip or folder>`:**
  - extracts the bundle (once);
  - syncs it into `<work>/jobs`, taking the HR files and the bundle's NL inputs (`hinge_params_collected.json`,
    `nl_plan.json`);
  - builds or updates `<work>/stage2_queue.json`, in the orchestrator's format, so `refresh`, the fingerprints and
    `unstall` all apply;
  - runs the steps side by side.
- **The steps** are those of the stage-2 plan:
  - the HR gravity record;
  - the pushover (X and Y, journaled);
  - the NLRHA (11 pairs, DBE + MCE, record cache, `--parallel` up to the workers);
  - the DDM (journaled, `--workers` up to the workers, `--speed-factor 1`: 2,400 s for the first step size);
  - the report (`nlrha criteria`, then `snl report`).
- **Scheduling:**
  - a step starts within `--workers` processes and a memory budget (80 % of the RAM by default; per-step estimates
    from the October measurements);
  - the longest jobs go first;
  - an NLRHA waits for its pushover, which `snl run` also does (its report reads the pushover), even when the
    pushover failed;
  - a failed gravity record skips the job's analyses.
- **The NL-21 yield check after a pushover or an NLRHA.** Elastic gravity members above first yield are promoted to
  fibre and the analysis runs again, two rounds at most, as `snl run` does. The orchestrator on the box does not do
  this; for a production run there it would be a gap.
- **Resume.** A step that was running when the runner stopped (a restart, a closed window, Ctrl+C) continues from its
  journal or record cache. A step whose process outlived its runner is waited for, never run twice at once. One
  runner per work folder (a lock file). On Windows the runner keeps the PC awake while it works. `--retry-failed`
  runs failed steps again.
- **The results.** ONE zip, `<results>/stage2_results_<date>.zip` (default `%USERPROFILE%\india\_claude_stage`),
  holds every job folder (journals and record caches left out), `STAGE2_RUN.log` and `STAGE2_MANIFEST.json`. The
  manifest records:
  - per step: the state, the skip, failure or promotion reasons, every run (start, end, seconds, workers, peak
    memory) and the input fingerprint;
  - per job: the input digest and the gate status;
  - the host, the settings (workers, memory, speed factor, DDM limit), the gold source and its sha256;
  - the NL code key and commit, and the HR engine fingerprint, commit and section tables;
  - the sha256 of every file.
  `verify --zip` checks a zip against its manifest.
- **`plan`** (dry run) lists every job and step, with the commands (`--verbose`) and the skips. It estimates the wall
  time on `--workers` by simulating the same scheduler with the October PC times (`scripts/stage2_estimates.json`;
  box runs divided by 1.6; a new job scaled by its element count). For the 24 current gold jobs on 12 workers it
  gives about 23 h. `status` shows where a run stands.
- **`windows/Run-Stage2.ps1`:**
  - makes a Python 3.12 environment in `%USERPROFILE%\india\stage2\env` with uv (the Steltic Hub's, or its own,
    as the hub's launcher does);
  - installs this checkout and psutil, and checks that OpenSees loads;
  - finds the HR engine in `%USERPROFILE%\india\steltic_india`, or else the hub's module;
  - calls the runner.
  `Run-Stage2.bat` wraps it. `RUN_STAGE2.md` holds the owner's instructions. The PowerShell script has not been run:
  no Windows machine here.
- **`nl_promote_fibre.json` is in the pushover journal key and the NLRHA record key** (`NL_DERIVED_INPUTS`). Without
  it, the re-run after a promotion would have reused the cached records and the finished journal of the model before
  the promotion.
- **`sync`:**
  - takes `inputs` (NL input files taken from the source) and `quiet`;
  - `NL_OUTPUTS` adds `stage2_*.log` (the runner's step logs) and `*.before_refresh_*`.

## Tests

`tests/test_stage2_2026_11.py`, 15 tests:
- the compute budget and how it is resolved, rescaled, recorded per result and per retry, reported and gated;
- each input file changing every key, including the site hazard for the NLRHA and the section tables;
- the DDM's own write into the calc package not changing any key;
- the peak memory of a real 120 MB child process, and the peak in the chunk record and the log;
- `--job-args` and `--speed-factor`;
- `refresh` after an HR change, an engine change (states the same, then different), a code change, and a partly run
  step;
- `sync` (dry run, NL outputs kept, unknown NL files kept, the calc package, removals only of files a sync brought
  in, the gold left unchanged), and `sync` followed by
  `refresh`.

`tests/test_run_stage2.py`, 7 tests, using stand-in analyses (`tests/stage2_stubs`, no OpenSees):
- the scheduler (order, widths, the memory budget, the NLRHA after its pushover, a failed gravity);
- the plan estimate, the estimates, the zip root, plan from a folder and from a zip;
- end to end:
  - the PC restarting during an NLRHA (the runner and its analyses killed), then the same command again;
  - nothing run twice and no record computed twice;
  - the promotion and its re-run;
  - the skip of a job without collected values;
  - the zip, the manifest and `verify`;
- a closed window (only the runner killed): the next run waits;
- the lock.

**Real end-to-end check on this box** (Linux, one heavy slot, 2 workers). The job was IN_Ex12 unitC_gym (20
elements) from the HR gold, with its October collected values. The NLRHA was cut to records 1–2 at DBE and MCE, and
the DDM to 1.5DL+1.5LL (`--job-args`).
- **Run 1** was killed after 100 s, together with every analysis it had started, as a restart would. By then the
  gravity, pushover and DDM had finished, and the NLRHA had cached one of its four records.
- **Run 2, the same command,** found every step current, and the one record cached. It ran the other three and the
  report in 153 s.
- **The results zip:** 60 files; `verify` found no problem. The DDM options record speed factor 1.0 and 2,400 s.
- **Peak memory:** pushover 125 MB, DDM 89 MB, NLRHA (2 workers) 308 MB.
- **Two faults it found, both fixed** and covered by the tests:
  - a bundle folder named `stage2_*` was taken for a runner log;
  - the calc-package comparison (above).

Full suite, with `STELTIC_ENGINE_DIR` set to the HR engine: 537 passed, 6 skipped. On `main` it was 515 passed,
6 skipped.
