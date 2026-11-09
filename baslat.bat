@echo off
rem ============================================
rem  YouTube Arsiv - Baslatici (betik modu)
rem  Python kurulu makinelerde calisir.
rem ============================================
set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if exist "%PYW%" goto :run_local
where py >nul 2>nul && (start "" py "%~dp0main.py" & goto :eof)
where python >nul 2>nul && (start "" python "%~dp0main.py" & goto :eof)
echo Python bulunamadi! python.org adresinden kurun.
pause
goto :eof

:run_local
start "" "%PYW%" "%~dp0main.py"
