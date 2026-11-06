<#
  Steltic nonlinear (SNL-IN) stage 2 on this PC -- one command, resumable. See RUN_STAGE2.md.

    Run-Stage2.bat <gold bundle .zip>            run (or continue) every stage-2 analysis, then write the results zip
    Run-Stage2.bat <gold bundle .zip> -Plan      only print what would run and how long it should take
    Run-Stage2.bat -Status                       where a run stands
    Run-Stage2.bat                               continue the last run (the same bundle)

  Everything lives under %USERPROFILE%\india:
    stage2\env           the Python 3.12 environment of this repository (made on the first run)
    stage2_work          the job folders and the queue (keep it until the results are collected)
    _claude_stage        the results zip, for the lead to collect
  The HR engine: -Engine, else %USERPROFILE%\india\steltic_india\steel_engine.
#>
param(
  [Parameter(Position = 0)] [string]$Gold = '',
  [int]$Workers = 0,
  [double]$MemoryGB = 0,
  [switch]$Plan,
  [switch]$Status,
  [switch]$Bundle,
  [switch]$RetryFailed,
  [string]$Engine = '',
  [string]$Work = '',
  [string]$Results = '',
  [switch]$Reinstall
)

$ErrorActionPreference = 'Stop'
$Repo    = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$India   = Join-Path $env:USERPROFILE 'india'
$Stage   = Join-Path $India 'stage2'
$EnvDir  = Join-Path $Stage 'env'
$Py      = Join-Path $EnvDir 'Scripts\python.exe'
$LogFile = Join-Path $Stage 'Run-Stage2.log'
if (-not $Work)    { $Work    = Join-Path $India 'stage2_work' }
if (-not $Results) { $Results = Join-Path $India '_claude_stage' }
New-Item -ItemType Directory -Force -Path $Stage, (Join-Path $Stage 'bin') | Out-Null

function Say($msg, $colour = 'Gray') {
  Write-Host $msg -ForegroundColor $colour
  Add-Content -Path $LogFile -Value ("[{0}] {1}" -f (Get-Date -Format s), $msg)
}
function Fail($msg) { Say $msg 'Red'; Say "Log: $LogFile"; exit 1 }

# ---------------------------------------------------------------- 1. uv (the Steltic Hub's, or a private copy)
$Uv = Join-Path $env:LOCALAPPDATA 'steltic_hub_india\bin\uv.exe'
if (-not (Test-Path $Uv)) {
  $Uv = Join-Path $Stage 'bin\uv.exe'
  if (-not (Test-Path $Uv)) {
    Say 'First run: fetching uv (one time, about 15 MB)...' 'Cyan'
    try {
      $env:UV_INSTALL_DIR = (Join-Path $Stage 'bin'); $env:UV_NO_MODIFY_PATH = '1'
      Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch { Fail "Could not download uv: $_" }
    if (-not (Test-Path $Uv)) {
      $found = Get-ChildItem -Path (Join-Path $Stage 'bin') -Filter uv.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($found) { Copy-Item $found.FullName $Uv -Force } else { Fail 'uv did not install.' }
    }
  }
}

# ---------------------------------------------------------------- 2. the environment (Python 3.12: openseespy has no 3.13 wheels)
if ($Reinstall -and (Test-Path $EnvDir)) { Say 'Removing the stage-2 environment...'; Remove-Item -Recurse -Force $EnvDir }
if (-not (Test-Path $Py)) {
  Say 'Creating the stage-2 Python environment (downloads Python 3.12 if needed)...' 'Cyan'
  & $Uv venv --python 3.12 $EnvDir
  if ($LASTEXITCODE -ne 0) { Fail 'Could not create the Python environment.' }
}
$Stamp  = Join-Path $EnvDir 'stage2.installed'
$PyProj = Join-Path $Repo 'pyproject.toml'
if (-not (Test-Path $Stamp) -or ((Get-Item $PyProj).LastWriteTimeUtc -gt (Get-Item $Stamp).LastWriteTimeUtc)) {
  Say 'Installing the nonlinear tools into the environment...' 'Cyan'
  & $Uv pip install --python $Py -e $Repo psutil
  if ($LASTEXITCODE -ne 0) { Fail 'Could not install the nonlinear tools.' }
  Set-Content -Path $Stamp -Value (Get-Date -Format s)
}
# OpenSees prints its banner on stderr: in Windows PowerShell 5.1 a redirected stderr line is an error record, so the
# check runs with errors not stopping the script
$prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $Py -c "import openseespy.opensees" *> $null
$ok = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prev
if (-not $ok) { Fail 'OpenSees (openseespy) does not load in the stage-2 environment. Run again with -Reinstall.' }

# ---------------------------------------------------------------- 3. the HR engine
if (-not $Engine) {
  foreach ($c in @((Join-Path $India 'steltic_india\steel_engine'),
                   (Join-Path $env:LOCALAPPDATA 'steltic_hub_india\modules\steltic_india\steel_engine'))) {
    if (Test-Path (Join-Path $c 'engine3d.py')) { $Engine = $c; break }
  }
}

# ---------------------------------------------------------------- 4. run
$cmd = if ($Plan) { 'plan' } elseif ($Status) { 'status' } elseif ($Bundle) { 'bundle' } else { 'run' }
$a = @((Join-Path $Repo 'scripts\run_stage2.py'), $cmd, '--work', $Work, '--results', $Results)
if ($Workers -gt 0)  { $a += @('--workers', "$Workers") }
if ($MemoryGB -gt 0) { $a += @('--memory-gb', "$MemoryGB") }
if ($cmd -in @('plan', 'run') -and $Gold) { $a += @('--gold', (Resolve-Path $Gold).Path) }
if ($cmd -eq 'plan' -and -not $Gold) { Fail 'Give the gold bundle: Run-Stage2.bat <bundle .zip> -Plan' }
if ($cmd -eq 'run') {
  if (-not $Engine) { Fail 'The HR engine was not found: clone steltic_india into %USERPROFILE%\india\steltic_india (RUN_STAGE2.md) or give -Engine <folder>.' }
  $a += @('--engine', $Engine)
  if ($RetryFailed) { $a += '--retry-failed' }
  Say "Stage 2: results go to $Results (engine $Engine)" 'Cyan'
}
$env:PYTHONUTF8 = '1'
& $Py @a
$rc = $LASTEXITCODE
if ($cmd -eq 'run') {
  switch ($rc) {
    0  { Say "Done. The results zip is in $Results" 'Green' }
    3  { Say "Done, but some steps failed (listed in the manifest beside the zip in $Results)." 'Yellow' }
    75 { Say 'Not finished: run the same command again to continue.' 'Yellow' }
    default { Say "Stopped (code $rc). Run the same command again to continue; the log is in $Work\stage2_run.log" 'Yellow' }
  }
}
exit $rc
