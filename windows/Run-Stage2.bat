@echo off
rem Steltic nonlinear stage 2 on this PC (see RUN_STAGE2.md):
rem   Run-Stage2.bat <gold bundle .zip>          run or continue, then write the results zip
rem   Run-Stage2.bat <gold bundle .zip> -Plan    what would run, and how long
rem   Run-Stage2.bat -Status                     where the run stands
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Stage2.ps1" %*
set RC=%ERRORLEVEL%
echo.
echo Finished with code %RC%.
pause
exit /b %RC%
