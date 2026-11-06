# Running the stage-2 nonlinear analyses on your PC

One command runs every stage-2 analysis on the gold designs: the pushover, the NLRHA and the DDM of each building,
then their reports. You can stop it and start it again at any time. When it finishes it writes one results zip for
the lead.

You need:
- Windows 10 or 11, with Git (already installed with the Steltic Hub);
- about 20 GB of free disk space;
- the gold bundle (a .zip) from the lead, and the two versions (commits) the lead names with it.

Type every command below into a Command Prompt exactly as written, quotes included. The quotes matter when your user
name has a space in it.

## 1. Install, or update

The lead's message gives two commits: one for the nonlinear tools and one for the HR engine. The run checks that both
checkouts are at those commits, and stops with the commands to type if they are not.

**First time** (when the folder `%USERPROFILE%\india\steltic_nonlinear_india` does not exist yet):
```
mkdir "%USERPROFILE%\india"
cd /d "%USERPROFILE%\india"
git clone https://github.com/Steltic/steltic_nonlinear_india
git clone https://github.com/Steltic/steltic_india
```

**If the folders are already there** (an earlier stage 2, or a clone you made yourself), update them instead:
```
cd /d "%USERPROFILE%\india\steltic_nonlinear_india"
git fetch
git checkout <the nonlinear commit from the lead>
cd /d "%USERPROFILE%\india\steltic_india"
git fetch
git checkout <the HR commit from the lead>
```

Two cases need a step first:
- **`git fetch` says "not a git repository".** The folder is a plain copy. Rename it (for example to
  `steltic_india_old`) and clone it again as above.
- **`git checkout` complains about local changes.** Throw the changes away with `git checkout -- .`, then run the
  checkout again.

The first run sets up its own Python (3.12, with OpenSees, at fixed versions) in `%USERPROFILE%\india\stage2`. It
downloads Python and the analysis libraries once, a few hundred MB. There is nothing else to install.

## 2. Put the gold bundle in place

Copy the lead's zip into `%USERPROFILE%\india`, for example as `%USERPROFILE%\india\stage2_gold.zip`.

## 3. See what will run (optional)

```
"%USERPROFILE%\india\steltic_nonlinear_india\windows\Run-Stage2.bat" "%USERPROFILE%\india\stage2_gold.zip" -Plan
```

This runs nothing. It lists:
- the two versions it checked;
- every building and analysis;
- an estimate of the time, for this PC's processors and memory. More memory lets more analyses run side by side.

A building without its collected IS values is listed as skipped; tell the lead.

## 4. Run

```
"%USERPROFILE%\india\steltic_nonlinear_india\windows\Run-Stage2.bat" "%USERPROFILE%\india\stage2_gold.zip"
```

- **Workers.** By default the run uses the number of processors less 2. To choose, add `-Workers 12`, for example.
- **The window.** Leave it open; it shows each analysis as it starts and ends. The PC can still be used for light
  work. While the run is working, Windows will not go to sleep.
- **How long.** About a day; the `-Plan` line gives the estimate for this PC.

## 5. If the PC restarts, sleeps, or the window is closed

**Sleep.** If the PC sleeps anyway, the analyses simply carry on when it wakes. The DDM counts processor time, not
clock time, so a sleep does not change its results.

**A restart or a closed window.** Closing the window stops the analyses as well. Run the same command again, or just
`Run-Stage2.bat` with no bundle, which continues the last run:
- finished analyses are kept;
- a pushover or a DDM continues from its last save (at most about 5 minutes of its work is lost);
- an NLRHA keeps every finished record, but the records that were running start again from their beginning. The
  longest takes up to about an hour.

To see where the run stands:
```
"%USERPROFILE%\india\steltic_nonlinear_india\windows\Run-Stage2.bat" -Status
```

## 6. When it says "Done"

The results are in `%USERPROFILE%\india\_claude_stage`:
- `stage2_results_<date>_<time>.zip`;
- a `.manifest.json` beside it, which lists what ran, what was skipped and why, the times and the versions.

Leave them there for the lead to collect, or send the zip. Keep `%USERPROFILE%\india\stage2_work` until the lead
confirms the results are in.

**If it ends with "some steps failed or were skipped".** The zip is written anyway, and the failed analyses are
listed in the manifest. Send it to the lead. The lead may ask you to run again with `-RetryFailed` added: that runs
the failed analyses, and the ones skipped because of them, once more.

**If it stops with a message.** It says what is wrong, for example a version that does not match. Do what it says,
then run the same command again. If it stops with "an unexpected error", send `%USERPROFILE%\india\stage2_work\stage2_run.log`
to the lead.

## For the lead

**The runner.** `scripts/run_stage2.py` (`bundle`, `plan`, `run`, `status`, `results`, `verify`) runs the same way on
Linux:
```
python scripts/run_stage2.py run --gold <bundle.zip> --engine <steltic_india/steel_engine>
```

**The gold bundle.**
- Make it with:
  ```
  python scripts/run_stage2.py bundle --jobs-root <gold jobs_hr> --hr <steltic_india> --out <bundle.zip> [--nl-inputs <folder>]
  ```
  `--nl-inputs` is a folder with the same layout that holds `hinge_params_collected.json` and `nl_plan.json`.
- It writes `STAGE2_BUNDLE.json`: the HR and NL commits, the jobs, and the sha256 of every file. Both checkouts must
  be clean git clones.
- Each job needs its `hinge_params_collected.json`; the bundle lists the jobs without one.
- Send the owner the two commits with the bundle.

**Checking a results zip.** `python scripts/run_stage2.py verify --zip <zip>` checks every file against the
manifest's sha256 and prints whether the versions matched. It also checks that every DDM output records speed factor
1.0 and the 2,400 CPU-second budget (each sweep at 2,400, 4,800 or 9,600 s), and fails otherwise.

**A bundle without commits.** A bundle made from a folder that is not a clean git clone (`bundle --accept-versions`)
records no commit, so `plan` and `run` refuse it. Only `--accept-versions` runs it.

**Moved-aside outputs.** When a new bundle changes a job, that job's earlier outputs and saves are renamed
`*.before_refresh_<time>` in the work folder. They are never in the zip, and they are deleted once the analysis has
run again successfully. The earlier design's `nl_promote_fibre.json.before_refresh_*` is kept; it is a few kB.

**Testing only.** `--accept-versions` runs past a version mismatch and records it in the manifest. The owner never
uses it.
