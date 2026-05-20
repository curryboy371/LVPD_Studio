@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM [호환] 숏츠 회화 TTS → batch_tts.bat 2
call "%~dp0batch_tts.bat" 2 %*
