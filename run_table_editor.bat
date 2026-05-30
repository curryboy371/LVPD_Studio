@echo off
setlocal
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "PYTHONPATH=%CD%"
set "PYTHONUNBUFFERED=1"

REM Table editor (extra.table_editor) - same as: lvpd.bat editor

set "_PY="
where py >nul 2>&1 && set "_PY=py -3"
if not defined _PY set "_PY=python"

echo.
echo [Table Editor] LVPD Table Editor
echo   %_PY% -m extra.table_editor
echo.
%_PY% -m extra.table_editor
set "TE_ERR=%ERRORLEVEL%"
if not "%TE_ERR%"=="0" (
  echo.
  echo [ERROR] Failed to start (exit %TE_ERR%).
  echo   %_PY% -m pip install -r extra\table_editor\requirements.txt
  pause
  exit /b %TE_ERR%
)
exit /b 0
