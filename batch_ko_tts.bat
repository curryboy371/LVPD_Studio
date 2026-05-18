@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [한국어 TTS 배치] ko_narration_sets/lines - set_id 단위 생성
echo   해당 set_id 파일만 삭제 후 재생성:
echo     resource\sound\shorts\ko_set_{id}_*.mp3
echo     resource\sound\shorts\ko_set_{id}_adjusted.srt
echo     resource\sound\shorts\ko_set_{id}_timeline.json
echo   (follow_along.mp3 는 전체 배치 시에만 갱신)
echo.
set "KO_SET_ID="
set "EXTRA_ARGS="
if not "%~1"=="" (
  echo %~1| findstr /r "^[0-9][0-9]*$" >nul
  if not errorlevel 1 (
    set "KO_SET_ID=%~1"
    shift
  )
)
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--set-id" (
  if not "%~2"=="" (
    set "KO_SET_ID=%~2"
    shift
    shift
    goto parse_args
  )
)
set "EXTRA_ARGS=%EXTRA_ARGS% %1"
shift
goto parse_args
:args_done
if "%KO_SET_ID%"=="" (
  set /p KO_SET_ID=ko_narration set_id 입력: 
)
if "%KO_SET_ID%"=="" (
  echo [오류] set_id 가 필요합니다.
  echo   예: batch_ko_tts.bat 1
  echo       batch_ko_tts.bat --set-id 1 --force
  if not "%SKIP_PAUSE%"=="1" pause
  exit /b 1
)
echo   ^> set_id=%KO_SET_ID%
echo.
set PYTHONPATH=%CD%
set _KO_TTS_PY=
where py >nul 2>nul && set _KO_TTS_PY=py -3
if not defined _KO_TTS_PY set _KO_TTS_PY=python
%_KO_TTS_PY% -m pip install -q pysrt gtts mutagen edge-tts 2>nul
%_KO_TTS_PY% -m tools.tts_gen.build_shorts_ko_narration --set-id %KO_SET_ID% %EXTRA_ARGS%
set _KO_TTS_ERR=%ERRORLEVEL%
if not "%_KO_TTS_ERR%"=="0" (
    echo.
    echo 종료 코드 %_KO_TTS_ERR%. edge-tts: pip install edge-tts ^& --tts edge
)
if not "%SKIP_PAUSE%"=="1" pause
exit /b %_KO_TTS_ERR%
