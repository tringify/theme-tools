@echo off
setlocal
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%~dp0theme.py" %*
) else (
  python "%~dp0theme.py" %*
)
exit /b %ERRORLEVEL%
