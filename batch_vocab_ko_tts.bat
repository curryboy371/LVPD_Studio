@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (call "%~dp0lvpd.bat" tts 1 topic) else (call "%~dp0lvpd.bat" tts 1 topic %*)
