@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM [호환] 숏츠 단어 TTS (topic) → batch_tts.bat 1 topic
if "%~1"=="" (
  call "%~dp0batch_tts.bat" 1 topic
) else (
  call "%~dp0batch_tts.bat" 1 topic %*
)
