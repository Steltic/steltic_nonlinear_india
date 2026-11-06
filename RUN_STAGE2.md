# Running the stage-2 nonlinear analyses on your PC

One command runs every stage-2 analysis on the gold designs: the pushover, the NLRHA and the DDM of each building,
then their reports. You can stop it and start it again at any time. When it finishes it writes one results zip for
the lead.

You need:
- Windows 10 or 11, with Git (already installed with the Steltic Hub);
- about 20 GB of free disk space;
- the gold bundle (a .zip) from the lead.

## 1. Install, or update (once, and again whenever the lead names new versions)

Open a Command Prompt.

**First time:**
```
mkdir %USERPROFILE%\india
cd %USERPROFILE%\india
git clone https://github.com/Steltic/steltic_nonlinear_india
git clone https://github.com/Steltic/steltic_india
```

**Each update.** The lead tells you which version (commit) of each to use:
```
cd %USERPROFILE%\india\steltic_nonlinear_india
git fetch
git checkout <the nonlinear version from the lead>
cd %USERPROFILE%\india\steltic_india
git fetch
git checkout <the HR version from the lead>
```

The first run sets up its own Python (3.12, with OpenSees) in `%USERPROFILE%\india\stage2`. It downloads Python
and the analysis libraries once, a few hundred MB. There is nothing else to install.

## 2. Put the gold bundle in place

Copy the lead's zip into `%USERPROFILE%\india`, for example as `%USERPROFILE%\india\stage2_gold.zip`.

## 3. See what will run (optional)

```
%USERPROFILE%\india\steltic_nonlinear_india\windows\Run-Stage2.bat %USERPROFILE%\india\stage2_gold.zip -Plan
```

This lists every building and analysis, and estimates the time on 12 workers. It runs nothing. A building without its
collected IS values is listed as skipped; tell the lead.

## 4. Run

```
%USERPROFILE%\india\steltic_nonlinear_india\windows\Run-Stage2.bat %USERPROFILE%\india\stage2_gold.zip
```

- **Workers.** By default the run uses the number of CPU cores less 2, which is 12 on your PC. To choose, add
  `-Workers 10`, for example.
- **The window.** Leave it open; it shows each analysis as it starts and ends. The PC can still be used for light
  work. While the run is working, Windows will not go to sleep.
- **How long.** It takes about a day; the `-Plan` line gives the estimate.

## 5. If the PC restarts, sleeps, or the window is closed

Run the same command again, or just `Run-Stage2.bat` with no bundle: it continues the last run.
- Finished analyses are kept.
- An interrupted analysis continues from its last save, so at most about 5 minutes of its work are lost.
- If an analysis from the closed window is still running, the new run waits for it first.

To see where the run stands: `Run-Stage2.bat -Status`.

## 6. When it says "Done"

The results are in `%USERPROFILE%\india\_claude_stage`:
- `stage2_results_<date>_<time>.zip`;
- a `.manifest.json` beside it, which lists what ran, what was skipped and why, the times and the versions.

Leave them there for the lead to collect, or send the zip. Keep `%USERPROFILE%\india\stage2_work` until the lead
confirms the results are in.

**If it ends with "some steps failed".** The zip is written anyway, and the failed analyses are listed in the
manifest. Send it to the lead. Running again with `-RetryFailed` tries them once more.

## For the lead

- **The runner.** `scripts/run_stage2.py` (`plan`, `run`, `status`, `bundle`, `verify`) runs the same way on Linux:
  `python scripts/run_stage2.py run --gold <bundle> --engine <steltic_india/steel_engine>`.
- **The gold bundle.** A zip or folder of job folders, in the `jobs_hr` layout; the units sit inside their buildings.
  Each job needs `hinge_params_collected.json` (the collected IS values). An `nl_plan.json` is taken when present.
- **Checking a results zip.** `python scripts/run_stage2.py verify --zip <zip>` checks every file against the
  manifest's sha256.
