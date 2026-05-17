@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [한국어 TTS 배치] ko_narration_sets/lines + shorts ko_narration_id
echo   -^> resource\sound\ko_set_{id}_{n}.mp3
echo   -^> resource\sound\ko_set_{id}_timeline.json
echo.
echo 옵션 예: batch_ko_tts.bat --topic where
echo         batch_ko_tts.bat --set-id 1 --force
echo.
set PYTHONPATH=%CD%
set _KO_TTS_PY=
where py >nul 2>nul && set _KO_TTS_PY=py -3
if not defined _KO_TTS_PY set _KO_TTS_PY=python
%_KO_TTS_PY% -m pip install -q pysrt gtts mutagen 2>nul
%_KO_TTS_PY% -m tools.tts_gen.build_shorts_ko_narration %*
set _KO_TTS_ERR=%ERRORLEVEL%
if not "%_KO_TTS_ERR%"=="0" (
    echo.
    echo 종료 코드 %_KO_TTS_ERR%. edge-tts: pip install edge-tts ^& --tts edge
)
if not "%SKIP_PAUSE%"=="1" pause
exit /b %_KO_TTS_ERR%
