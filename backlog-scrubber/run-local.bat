@echo off
rem Backlog Scrubber - run on your own computer. Double-click this file.
cd /d "%~dp0"
set "PY=py"
where py >nul 2>nul || set "PY=python"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this file again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Setting up, first time only...
  %PY% -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing what the app needs...
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo.
  echo The install failed. Copy the message above and send it to the person helping you.
  pause
  exit /b 1
)
set "DATABRICKS_HOST=https://dbc-6fe372b1-7eae.cloud.databricks.com"
set "DISCONTINUED_CODES=D"
if "%DATABRICKS_WAREHOUSE_ID%"=="" (
  echo.
  echo In Databricks open Compute, then SQL warehouses, click your warehouse and copy its ID.
  set /p DATABRICKS_WAREHOUSE_ID=Paste the warehouse ID and press Enter: 
)
echo.
echo Starting. A browser window will ask you to sign in to Databricks the first time you run a scrub.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
python app.py
echo.
echo The app stopped. If you see an error above, copy it and send it over.
pause
