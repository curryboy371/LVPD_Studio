@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM [호환] CSV 일괄 생성 → lvpd.bat csv
call "%~dp0lvpd.bat" csv %*
