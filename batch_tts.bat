@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal EnableDelayedExpansion

REM ---------------------------------------------------------------------------
REM  TTS 배치 (lvpd.bat 2번 / lvpd.bat tts 로도 호출)
REM    1  숏츠 단어 모드  — words.csv 뜻 → ko_word_{word_id}_*
REM    2  숏츠 회화 모드  — ko_narration set → ko_set_{id}_*
REM    3  단어 자체       — words.csv word_id 직접 (동일 산출 경로)
REM ---------------------------------------------------------------------------

set "MODE=%~1"
set "ARG2=%~2"
set "ARG3=%~3"
set "EXTRA_ARGS="

if /I "%MODE%"=="conversation" set "MODE=2"
if /I "%MODE%"=="shorts-conversation" set "MODE=2"
if /I "%MODE%"=="ko" set "MODE=2"
if /I "%MODE%"=="set" set "MODE=2"
if /I "%MODE%"=="narration" set "MODE=2"
if /I "%MODE%"=="vocab" set "MODE=1"
if /I "%MODE%"=="shorts-vocab" set "MODE=1"
if /I "%MODE%"=="shorts-vocabulary" set "MODE=1"
if /I "%MODE%"=="word" set "MODE=3"
if /I "%MODE%"=="words" set "MODE=3"

REM lvpd.bat tts 1001 처럼 set_id만 넘긴 경우 → 모드 2
if "%ARG2%"=="" (
  echo %MODE%| findstr /r "^100[0-9]$" >nul
  if not errorlevel 1 (
    set "ARG2=%MODE%"
    set "MODE=2"
  )
)

if not "%MODE%"=="" shift

if "%MODE%"=="" goto menu
if "%MODE%"=="1" goto mode_vocab
if "%MODE%"=="2" goto mode_conversation
if "%MODE%"=="3" goto mode_word
echo [오류] 모드는 1^|2^|3 입니다.
echo        1=단어 뜻  2=ko set_id^(1001 등^)  3=word_id
echo        ko set: lvpd.bat tts set 1001
goto fail

:menu
echo.
echo ========================================
echo   TTS 배치
echo ========================================
echo   1  숏츠 단어 모드
echo      1-1 clips id / 1-2 topic -^> 단어 뜻 ko_word_{word_id}_*
echo      1-3 ko set_id -^> 인트로 ko_set_{set_id}_* ^(예 1001^)
echo.
echo   2  ko_narration set_id ^(내레이션 문장 TTS^)
echo      예: 1000 푸바오 인트로 / 1001 한시 인트로
echo      산출: resource\sound\shorts\ko_set_{set_id}_*
echo      lvpd.bat tts set 1001  또는  lvpd.bat tts 2 1001
echo.
echo   3  단어 자체 (words.csv)
echo      word_id 직접 (숏츠 CSV 없이 동일 ko_word_* 산출)
echo.
set /p MODE=선택 1-3: 
if "%MODE%"=="1" goto mode_vocab
if "%MODE%"=="2" goto mode_conversation
if "%MODE%"=="3" goto mode_word
echo [오류] 1~3 중 선택하세요.
goto fail

:mode_vocab
set "VOCAB_KIND="
set "VOCAB_KEY="

if /I "%ARG2%"=="id" (
  set "VOCAB_KIND=id"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto vocab_parse_extra
)
if /I "%ARG2%"=="topic" (
  set "VOCAB_KIND=topic"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto vocab_parse_extra
)
if /I "%ARG2%"=="set" (
  set "VOCAB_KIND=set"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto vocab_parse_extra
)
if /I "%ARG2%"=="ko" (
  set "VOCAB_KIND=set"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto vocab_parse_extra
)

if not "%ARG2%"=="" (
  echo %ARG2%| findstr /r "^100[0-9]$" >nul
  if not errorlevel 1 (
    set "VOCAB_KIND=set"
    set "VOCAB_KEY=%ARG2%"
    goto vocab_parse_extra
  )
  echo %ARG2%| findstr /r "^[0-9][0-9]*$" >nul
  if not errorlevel 1 (
    set "VOCAB_KIND=id"
    set "VOCAB_KEY=%ARG2%"
    goto vocab_parse_extra
  )
  set "VOCAB_KIND=topic"
  set "VOCAB_KEY=%ARG2%"
  goto vocab_parse_extra
)

echo.
echo [숏츠 단어 모드]
echo   1-1  shorts_vocabulary_clips 행 id -^> 단어 뜻 TTS
echo   1-2  topic -^> 단어 뜻 TTS
echo   1-3  ko_narration set_id -^> 인트로 TTS ^(예 1000 1001^)
echo.
set /p VOCAB_SUB=선택 1-1 / 1-2 / 1-3: 
if /I "%VOCAB_SUB%"=="1" set "VOCAB_KIND=id"
if /I "%VOCAB_SUB%"=="1-1" set "VOCAB_KIND=id"
if /I "%VOCAB_SUB%"=="2" set "VOCAB_KIND=topic"
if /I "%VOCAB_SUB%"=="1-2" set "VOCAB_KIND=topic"
if /I "%VOCAB_SUB%"=="3" set "VOCAB_KIND=set"
if /I "%VOCAB_SUB%"=="1-3" set "VOCAB_KIND=set"
if "!VOCAB_KIND!"=="" (
  echo [오류] 1-1 / 1-2 / 1-3 중 선택하세요.
  goto fail
)
if /I "!VOCAB_KIND!"=="id" (
  set /p VOCAB_KEY=shorts_vocabulary_clips id 1~3: 
) else if /I "!VOCAB_KIND!"=="set" (
  set /p VOCAB_KEY=ko_narration set_id 예 1001: 
) else (
  set /p VOCAB_KEY=topic 예 jingyesi: 
)
if "!VOCAB_KEY!"=="" goto fail

:vocab_parse_extra
set "EXTRA_ARGS="
:parse_extra
if "%~1"=="" goto vocab_run
set "EXTRA_ARGS=!EXTRA_ARGS! %1"
shift
goto parse_extra

:vocab_run
echo.
if /I "!VOCAB_KIND!"=="set" (
  echo ^> ko_narration set_id=!VOCAB_KEY!
) else if /I "!VOCAB_KIND!"=="id" (
  echo ^> 숏츠 단어 뜻 / clips id=!VOCAB_KEY!
) else (
  echo ^> 숏츠 단어 뜻 / topic=!VOCAB_KEY!
)
call :setup_py
if /I "!VOCAB_KIND!"=="set" (
  %_PY% -m pip install -q pysrt gtts mutagen edge-tts 2>nul
  %_PY% -m tools.tts_gen.build_shorts_ko_narration --set-id !VOCAB_KEY! --shorts-type vocabulary !EXTRA_ARGS!
) else (
  %_PY% -m pip install -q gtts mutagen edge-tts 2>nul
  if /I "!VOCAB_KIND!"=="id" (
    %_PY% -m tools.tts_gen.build_vocab_meaning_ko --id !VOCAB_KEY! !EXTRA_ARGS!
  ) else (
    %_PY% -m tools.tts_gen.build_vocab_meaning_ko --topic "!VOCAB_KEY!" !EXTRA_ARGS!
  )
)
set "_ERR=!ERRORLEVEL!"
goto done

:mode_conversation
set "KO_SET_ID=%ARG2%"
if "!KO_SET_ID!"=="" (
  echo.
  echo [ko_narration set_id]
  echo   shorts_vocabulary_clips 의 ko_narration_id 와 동일합니다.
  echo   예: 1000=bao 인트로  1001=jingyesi 한시 인트로
  echo   CSV: ko_narration_lines.csv / ko_narration_sets.csv
  echo.
)
if "!KO_SET_ID!"=="" set /p KO_SET_ID=set_id 예 1001: 
if "!KO_SET_ID!"=="" (
  echo [오류] set_id 가 필요합니다. 예: lvpd.bat tts set 1001
  goto fail
)
if not "%ARG2%"=="" shift
set "EXTRA_ARGS="
:parse_extra_conv
if "%~1"=="" goto conv_run
set "EXTRA_ARGS=!EXTRA_ARGS! %1"
shift
goto parse_extra_conv
:conv_run
echo.
echo ^> 숏츠 회화 / set_id=!KO_SET_ID!
call :setup_py
%_PY% -m pip install -q pysrt gtts mutagen edge-tts 2>nul
%_PY% -m tools.tts_gen.build_shorts_ko_narration --set-id !KO_SET_ID! !EXTRA_ARGS!
set "_ERR=!ERRORLEVEL!"
goto done

:mode_word
set "WORD_IDS=%ARG2%"
if "!WORD_IDS!"=="" set /p WORD_IDS=word_id 30123 또는 30123^|30124: 
if "!WORD_IDS!"=="" (
  echo [오류] word_id 가 필요합니다. 예: batch_tts.bat 3 30123
  goto fail
)
if not "%ARG2%"=="" shift
set "EXTRA_ARGS="
:parse_extra_word
if "%~1"=="" goto word_run
set "EXTRA_ARGS=!EXTRA_ARGS! %1"
shift
goto parse_extra_word
:word_run
echo.
echo ^> 단어 자체 / word_id=!WORD_IDS!
call :setup_py
%_PY% -m pip install -q gtts mutagen edge-tts 2>nul
%_PY% -m tools.tts_gen.build_vocab_meaning_ko --word-id "!WORD_IDS!" !EXTRA_ARGS!
set "_ERR=!ERRORLEVEL!"
goto done

:setup_py
set PYTHONPATH=%CD%
set _PY=
where py >nul 2>nul && set _PY=py -3
if not defined _PY set _PY=python
exit /b 0

:done
if not "!_ERR!"=="0" (
  echo.
  echo 종료 코드 !_ERR!. edge-tts: pip install edge-tts
)
if not "%SKIP_PAUSE%"=="1" pause
exit /b !_ERR!

:fail
if not "%SKIP_PAUSE%"=="1" pause
exit /b 1
