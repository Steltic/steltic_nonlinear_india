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

**CPU time beside wall time** in each NLRHA record (`cpu_seconds`), the orchestrator chunks, the runner steps and STAGE2_MANIFEST (`cpu_s`, `nlrha_records`): a pause shows as wall time far above CPU time.

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

**Full suite**, with `STELTIC_ENGINE_DIR` set to HR main e927f35 (the engine the new IN_Ex21 gold needs): **539
passed, 4 skipped**. On `main`, with the engine of the time, it was 515 passed and 6 skipped.
- The two extra passes are the IN_Ex21 gold tests: the gold arrived on 2026-11-06, and these tests skip without it.
- With the older HR engine 44b74de, those two fail on `main` too (`sections.double_angle_label` missing), so the
  failure comes from the engine version, not from this branch.

## Fixes from the independent review (`briefs/NL_STAGE2_REVIEW.md`)

Every journal and record-cache key changes again: the code key covers more files, the library versions are in it, and
the journal keeps a CPU clock. Stage 2 starts fresh anyway. One decision differs from the review's suggestion (L3).

**Blocking:**
- **B1. Windows import.** `import fcntl` moved into `next_steps` (the box only). A test imports and plans with `fcntl`,
  `resource`, `termios`, `pwd` and `grp` blocked.
- **B2. Engine and code versions.**
  - `run_stage2.py bundle` (the lead) writes the gold bundle with `STAGE2_BUNDLE.json`: the HR and NL commits, the
    jobs (and those without collected values), and the sha256 of every file. It refuses unclean checkouts. The old
    `bundle` command, which re-writes the results zip, is now `results`.
  - `plan` and `run` compare the bundle's commits with `git rev-parse HEAD` of the engine's clone and of this
    checkout. They refuse (exit 2) with the exact `git fetch` / `git checkout` to type when:
    - a commit differs;
    - a folder is not a git clone;
    - tracked files have local changes;
    - the bundle has no manifest.
  - The manifest records the versions, `code_changed`, and `mixed_versions` when finished steps carry more than one
    engine or code fingerprint.
  - `Run-Stage2.ps1` no longer falls back to the Steltic Hub's engine.
  - `engine_fingerprint` hashes every module and section table in the engine folder (it was 5 files), and
    `code_key` / `section_tables_key` do the same, all with CRLF made LF. A Windows checkout of the same commit
    therefore fingerprints the same.
- **B3. Pids after a restart.** A step's pid and the lock's pid are stored with the process's start token (psutil's
  start time, or the Linux boot id with the start ticks). A pid counts as the recorded process only when both match,
  so a pid reused after a restart never makes the runner wait or refuse.

**Before the PC run:**
- **M1. Old outputs.** When `refresh` (or a recheck) puts a step back to pending, its outputs are set aside as
  `*.before_refresh_<time>`, together with its journals:
  - gravity: `nl_hr_gravity.json`;
  - pushover: `pushover/`;
  - NLRHA: `nlrha/`;
  - DDM: `ddm_results.json`, its pages and `model_gmnia.py`, with its block taken out of `design/calc_package.json`;
  - report: the gate files, the pages and the design criteria.

  A failed re-run can no longer leave the earlier design's results in the zip or in front of the gate.
- **M2 / L13. Promotion rounds.** The NL-21 rounds are counted from `nl_promote_fibre.json` itself (one history entry
  per round), and that file is set aside on a design change. `_reset` also drops the queue's round fields. A new
  design therefore starts at zero rounds, and a kill between promotion and save loses no round.
- **M3. Recheck.** A `recheck` step whose gravity record failed ends `skipped`, with the reason. The run then ends
  (rc 3) with the zip written.
- **M4. Retry after a gravity failure.** `--retry-failed` also puts back the analyses skipped because of a failed
  gravity record. A skip made while scheduling is saved at once.
- **M5. Start fingerprints.** A step that goes back to pending loses its old start fingerprint, and a fresh start takes
  a new one.
- **M6. The DDM compute budget.**
  - The sweep's time limit is now CPU time of the sweep's process (`time.process_time`; a sweep starts no child
    processes). The journal records it beside the wall clock, so a replay repeats it, and a pause or other load no
    longer moves a DDM result.
  - Each sweep, run row and retry rung records `cpu_seconds`, and each run row its `time_limit_s`.
  - Each DDM output, and every retry or B-1.2 refresh record, carries the speed factor and `calibration_s`: the CPU
    time of a fixed small OpenSees run, best of 3 (about 0.5 s on this box). The manifest gives the host's calibration and each job's DDM
    settings. A wrong factor thus shows as a calibration time that does not fit it.
  - The gate requires the limit to equal 2,400 × the recorded factor. The PC uses 1.0.
- **M7. Queue robustness.**
  - The queue is written with flush and fsync, and the previous one is kept as `.bak`; an unreadable queue falls
    back to it.
  - `os.replace` is retried on a PermissionError.
  - An error in one step's bookkeeping, or when starting a step, marks that step failed and the others carry on.
- **M8. Library versions.**
  - `windows/constraints.txt` pins the box's versions: openseespy / openseespywin / openseespylinux 3.8.0.0, numpy
    2.5.4, scipy 1.18.1, psutil 7.0.0. Each was checked on PyPI to have a CPython 3.12 Windows x64 wheel;
    openseespy itself is pure Python.
  - The launcher installs with `-c`.
  - The versions are in `run_key()` and in the manifest.
- **M9. Nested units.** `sync` matches `design/calc_package.json` by its tail, so a nested unit's file is compared
  without the DDM block too, and never overwritten because of the DDM's own write. When the HR content of a calc
  package really changes, the gold's copy still comes in; the DDM then runs again and writes its block anew.

**Low:**
- **L1.** RUN_STAGE2.md quotes every path.
- **L2.** RUN_STAGE2.md now says what a restart really loses: up to 5 minutes for a pushover or DDM, and the running
  NLRHA records from their beginning. Closing the window ends the analyses too.
- **L3.** `plan` states this PC's CPUs and RAM; the estimate uses 80 % of the RAM. For the current 25 jobs on 12
  workers it gives 27.1 h with 16 GB and 15.9 h with 32 GB.
  - Not done: reserving memory for a held-back longest job. Simulated, it made the whole run 30 % longer (34.9 h at
    16 GB).
- **L4.** RUN_STAGE2.md covers existing clones, plain-copy folders and local changes.
- **L5.** The launcher gives a plain message for a missing bundle. Exit code 2 now means "put it right and run again",
  distinct from an unexpected error.
- **L6.** `.gitattributes`: `*.bat` and `*.ps1` are checked out with CRLF.
- **L7.** uv is installed with `UV_UNMANAGED_INSTALL`, so nothing is written outside the stage-2 folder.
- **L8.** `report_ddm.write_block` writes atomically.
- **L9.** `pushover/fbc_concentrated.py` and `rbs_remesh.py` are in the code key.
- **L10.** A watchdog stops a step whose processes gain no CPU time for 30 minutes (`--watchdog-minutes`). Gaps
  between polls longer than a minute, such as a sleep, are not counted. The step is marked failed with the reason.
- **L11.**
  - A half-written results zip is removed.
  - The side manifest is written atomically.
  - The gold extraction folder is `gold\<sha12>`.
- **L12.**
  - `sync` across two drives no longer raises.
  - A malformed `--job-args` gets a plain message.
  - The bundle manifest fixes the gold root, so a bundle holding only a unit keeps the unit's full id.
- **L14. The pushover's Y curve after a restart.**
  - **Cause.** The eigen solver's start vector depends on the eigen solves made earlier in the process. The second
    direction's period differed by 1e-11, which changed the step schedule and the curve.
  - **Fix.** The pushover CLI now computes each direction in a process of its own (`--dirs <d> --direction-child`, on
    the same journal), and the parent only assembles. A direction is always the first analysis in its process, with
    or without a restart.
  - The journal key no longer holds the direction list.
  - `SNL_PUSHOVER_ONE_PROCESS=1` keeps the old in-process path; the tests use it for the CLI's journal path.
- **L15.** CPU time that could not be measured is recorded as null, not 0.

**Tests.** `tests/test_stage2_review_2026_11.py`, 18 tests, one or more per finding. They include end-to-end runs
with stand-ins that:
- change the design and then fail the pushover (M1);
- change the engine, then fail and retry the gravity record (M3, M4);
- raise in a step's bookkeeping (M7).

The earlier stage-2 tests were adapted:
- the version check is accepted for the stand-ins;
- the lock with a start token;
- the CPU-seconds wording;
- the gate's factor rule;
- the journal tests' fake clock now has `process_time`.

**Real end-to-end check after the fixes** (Linux, one heavy slot, 2 workers).
- **The bundle**, made by `bundle` from the HR gold, holds the whole IN_Ex12 building with its two nested units, at
  HR e927f35 and NL 1f40a61. Only unitC_gym has collected values: the building and unitB_link are skipped, with the
  reason. The NLRHA was cut to 2 records per level and the DDM to 1.5DL+1.5LL.
- **Run 1** checked the versions (both matched). It was killed after 22 s with all its analyses, while the NLRHA ran;
  gravity, pushover (each direction in its own process) and DDM were done.
- **Run 2, the same command,** found every step current and finished the NLRHA and the report in 3 min.
- **Run 3** found nothing to do. Both resumes reported `0 updated`: the unit's calc package kept its DDM block (M9).
- **The zip:** 213 files; `verify` found 0 problems, with versions ok.
- **What the manifest records:**
  - the libraries: openseespy 3.8.0.0, numpy 2.5.4, scipy 1.18.1;
  - the DDM's factor 1.0, its limit of 2,400 CPU seconds and the calibration time;
  - per sweep and per record, the CPU time beside the wall time. With the other slot loaded, the NLRHA records got
    about 50 % of the wall time as CPU.
- **Peak memory:** pushover 218 MB (two direction processes), DDM 94 MB, NLRHA ×2 312 MB.
- **One adjustment it led to:** the first calibration run took only 0.016 s, too short to time reliably. It is now
  about 0.5 s.

**Full suite** with HR main e927f35 as the engine: **558 passed, 4 skipped** (540 / 4 before the review fixes).
