@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [단어 뜻 TTS 배치] topic -^> words.csv 뜻 (한국어 TTS)
echo   word_id 출처: shorts_vocabulary_clips 우선, 없으면 vocabulary_word_rows
echo   산출: resource\sound\shorts\ko_word_{word_id}_0.mp3
echo         resource\sound\shorts\ko_word_{word_id}_timeline.json
echo.
set "TOPIC=%~1"
set "EXTRA_ARGS="
if not "%TOPIC%"=="" shift
:parse_args
if "%~1"=="" goto args_done
set "EXTRA_ARGS=%EXTRA_ARGS% %1"
shift
goto parse_args
:args_done
if "%TOPIC%"=="" set /p TOPIC=topic 입력 (예: fruit_store): 
if "%TOPIC%"=="" (
  echo [오류] topic 이 필요합니다.
  echo   예: batch_vocab_ko_tts.bat fruit_store
  if not "%SKIP_PAUSE%"=="1" pause
  exit /b 1
)
echo   ^> topic=%TOPIC%
echo.
set PYTHONPATH=%CD%
set _PY=
where py >nul 2>nul && set _PY=py -3
if not defined _PY set _PY=python
%_PY% -m pip install -q gtts mutagen edge-tts 2>nul
%_PY% -m tools.tts_gen.build_vocab_meaning_ko --topic "%TOPIC%" %EXTRA_ARGS%
set _ERR=%ERRORLEVEL%
if not "%_ERR%"=="0" (
  echo.
  echo 종료 코드 %_ERR%. edge-tts: pip install edge-tts
)
if not "%SKIP_PAUSE%"=="1" pause
exit /b %_ERR%
