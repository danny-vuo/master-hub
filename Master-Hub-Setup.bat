@echo off
echo ===== Master Hub setup =====
echo.
set "HUB=https://danny-vuo.github.io/master-hub/"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
set "BROWSER="
if exist "%EDGE%" set "BROWSER=%EDGE%"
if not defined BROWSER if exist "%CHROME%" set "BROWSER=%CHROME%"
if not defined BROWSER goto nobrowser

echo Step 1 of 2: putting the Master Hub shortcut on your desktop ...
set "VBS=%TEMP%\master_hub_setup.vbs"
> "%VBS%" echo Set s = CreateObject("WScript.Shell")
>> "%VBS%" echo Set l = s.CreateShortcut(s.SpecialFolders("Desktop") ^& "\Master Hub.lnk")
>> "%VBS%" echo l.TargetPath = "%BROWSER%"
>> "%VBS%" echo l.Arguments = "--app=%HUB%"
>> "%VBS%" echo l.Description = "Master Hub"
>> "%VBS%" echo l.Save
cscript //nologo "%VBS%"
del "%VBS%" >nul 2>&1

:merp
echo Step 2 of 2: setting the MERP tile to open MERP 2026 ...
reg add "HKCU\Software\Classes\merp" /ve /t REG_SZ /d "URL:MERP Protocol" /f >nul
reg add "HKCU\Software\Classes\merp" /v "URL Protocol" /t REG_SZ /d "" /f >nul
reg add "HKCU\Software\Classes\merp\shell\open\command" /ve /t REG_SZ /d "cmd.exe /c start \"\" \"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\MERP 2026\MERP 2026.lnk\"" /f >nul
if errorlevel 1 goto failed
echo.
echo Done. Use the new Master Hub icon on your desktop.
echo Please close your browser and open it again before using the MERP tile.
goto end

:nobrowser
echo Could not find Microsoft Edge or Google Chrome, so the desktop shortcut was skipped.
echo You can still open the Hub at %HUB%
echo.
goto merp

:failed
echo.
echo Something went wrong. Please send a screenshot of this window to Danny.

:end
echo.
pause
