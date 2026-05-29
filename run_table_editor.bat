@echo off
setlocal
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "PYTHONPATH=%CD%"
set "PYTHONUNBUFFERED=1"

REM 테이블 편집기 (extra.table_editor) — words / base_sentences / sub_sentences
REM 동일 기능: lvpd.bat editor  또는  lvpd.bat 메뉴 E

set "_PY="
where py >nul 2>&1 && set "_PY=py -3"
if not defined _PY set "_PY=python"

echo.
echo [테이블 편집기] LVPD Table Editor
echo   %_PY% -m extra.table_editor
echo.
%_PY% -m extra.table_editor
if errorlevel 1 (
  echo.
  echo [오류] 실행 실패.
  echo   %_PY% -m pip install -r extra\table_editor\requirements.txt
  pause
  exit /b 1
)
exit /b 0
