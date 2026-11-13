@echo off
echo Setting up MERP 2026 for the Master Hub ...
echo.
reg add "HKCU\Software\Classes\merp" /ve /t REG_SZ /d "URL:MERP Protocol" /f >nul
reg add "HKCU\Software\Classes\merp" /v "URL Protocol" /t REG_SZ /d "" /f >nul
reg add "HKCU\Software\Classes\merp\shell\open\command" /ve /t REG_SZ /d "cmd.exe /c start \"\" \"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\MERP 2026\MERP 2026.lnk\"" /f >nul
if errorlevel 1 goto failed
echo Done. The MERP tile in the Master Hub will now open MERP 2026.
echo Please close your browser and open it again.
goto end
:failed
echo Something went wrong. Please send a screenshot of this window to Danny.
:end
echo.
pause
