@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM [호환] 숏츠 단어 TTS (clips id) → batch_tts.bat 1 id
if "%~1"=="" (
  call "%~dp0batch_tts.bat" 1 id
) else (
  call "%~dp0batch_tts.bat" 1 id %*
)
