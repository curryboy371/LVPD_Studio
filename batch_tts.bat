@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal EnableDelayedExpansion

REM ---------------------------------------------------------------------------
REM  TTS 배치 4단계 (lvpd.bat tts)
REM    1  회화 모드     topic → sub_sentences.alt_translation → ko_sub_{id}.mp3
REM    2  단어장 모드   topic → vocabulary_word_rows → ko_word_{word_id}_*
REM    3  숏츠 회화     ko_narration set_id → ko_set_{id}_*  (기존)
REM    4  숏츠 단어     clips id / topic / ko set  (기존)
REM ---------------------------------------------------------------------------

set "MODE=%~1"
set "ARG2=%~2"
set "ARG3=%~3"
set "EXTRA_ARGS="

REM --- 별칭: 스튜디오 회화/단어 (모드 1·2) ---
if /I "%MODE%"=="studio-conversation" set "MODE=1"
if /I "%MODE%"=="conv-studio" set "MODE=1"
if /I "%MODE%"=="studio-conv" set "MODE=1"
if /I "%MODE%"=="studio-vocabulary" set "MODE=2"
if /I "%MODE%"=="studio-vocab" set "MODE=2"
if /I "%MODE%"=="vocab-studio" set "MODE=2"

REM --- 별칭: 숏츠 (모드 3·4) ---
if /I "%MODE%"=="shorts-conversation" set "MODE=3"
if /I "%MODE%"=="shorts-conv" set "MODE=3"
if /I "%MODE%"=="shorts_conv" set "MODE=3"
if /I "%MODE%"=="ko" set "MODE=3"
if /I "%MODE%"=="set" set "MODE=3"
if /I "%MODE%"=="narration" set "MODE=3"
if /I "%MODE%"=="shorts-vocabulary" set "MODE=4"
if /I "%MODE%"=="shorts-vocab" set "MODE=4"
if /I "%MODE%"=="shorts_vocab" set "MODE=4"
if /I "%MODE%"=="shorts" set "MODE=4"

REM 구 호환: conversation → 숏츠 회화(3), vocabulary → 숏츠 단어 topic(4) 아님 — 명시적 숏츠만
if /I "%MODE%"=="shorts-conversation" set "MODE=3"

REM lvpd.bat tts 1001 → 숏츠 회화 set_id
if "%ARG2%"=="" (
  echo %MODE%| findstr /r "^100[0-9]$" >nul
  if not errorlevel 1 (
    set "ARG2=%MODE%"
    set "MODE=3"
  )
)

if not "%MODE%"=="" shift

if "%MODE%"=="" goto menu
if "%MODE%"=="1" goto mode_studio_conv
if "%MODE%"=="2" goto mode_studio_vocab
if "%MODE%"=="3" goto mode_shorts_conv
if "%MODE%"=="4" goto mode_shorts_vocab
echo [오류] 모드는 1~4 입니다.
echo   1=회화 topic  2=단어장 topic  3=숏츠회화 set_id  4=숏츠단어
goto fail

:menu
echo.
echo ========================================
echo   TTS 배치 (4단계)
echo ========================================
echo   1  회화 모드 - F5 conversation
echo      topic -^> sub_sentences.alt_translation
echo      산출: resource/sound/sentense/ko_sub_baseId_subId.mp3
echo      기본: 해당 topic mp3 삭제 후 전부 재생성 ^(스킵 없음^)
echo      기존 유지: batch_tts.bat 1 ^<topic^> --skip-existing
echo      검증: python -m tools.tts_gen.verify_conversation_sub_ko --topic ^<topic^>
echo.
echo   2  단어장 모드 - F5 vocabulary
echo      산출: resource/sound/shorts/ko_word_숫자.mp3
echo      topic -^> vocabulary_word_rows 전체 word_id
echo      선택: word-id 로 ID 직접 지정 가능
echo.
echo   3  숏츠 회화 (기존)
echo      set_id: lvpd.bat tts 3 15
echo      topic:  lvpd.bat tts 3 topic shangchai
echo      산출: resource/sound/shorts/ko_set_숫자.mp3
echo.
echo   4  숏츠 단어 (기존)
echo      4-1 clips id / 4-2 topic / 4-3 ko set_id
echo      산출: ko_word 또는 ko_set mp3
echo.
set /p MODE=선택 1-4: 
if "%MODE%"=="1" goto mode_studio_conv
if "%MODE%"=="2" goto mode_studio_vocab
if "%MODE%"=="3" goto mode_shorts_conv
if "%MODE%"=="4" goto mode_shorts_vocab
echo [오류] 1~4 중 선택하세요.
goto fail

:mode_studio_conv
set "TOPIC=%ARG2%"
if "!TOPIC!"=="" set /p TOPIC=base_sentences.topic 예 fruit_store: 
if "!TOPIC!"=="" goto fail
if not "%ARG2%"=="" shift
set "EXTRA_ARGS="
:parse_extra_sc
if "%~1"=="" goto studio_conv_run
set "EXTRA_ARGS=!EXTRA_ARGS! %1"
shift
goto parse_extra_sc
:studio_conv_run
echo.
echo ^> [1] 회화 모드 / topic=!TOPIC!
call :setup_py
%_PY% -m pip install -q gtts mutagen edge-tts 2>nul
%_PY% -m tools.tts_gen.build_conversation_sub_ko --topic "!TOPIC!" !EXTRA_ARGS!
set "_ERR=!ERRORLEVEL!"
goto done

:mode_studio_vocab
set "STUDIO_TOPIC=%ARG2%"
set "WORD_IDS="
if /I "%ARG2%"=="word-id" (
  set "WORD_IDS=%ARG3%"
  shift
  shift
  goto studio_vocab_parse_extra
)
if /I "%ARG2%"=="word" set "ARG2=word-id" & goto mode_studio_vocab
if not "%ARG2%"=="" (
  echo %ARG2%| findstr /r "^[0-9][0-9]*$" >nul
  if not errorlevel 1 (
    set "WORD_IDS=%ARG2%"
    shift
    goto studio_vocab_parse_extra
  )
  set "STUDIO_TOPIC=%ARG2%"
  shift
)
if "!STUDIO_TOPIC!"=="" if "!WORD_IDS!"=="" (
  echo.
  echo [2] 단어장 모드
  echo   topic 예: hair  jingyesi
  echo   또는 word-id 30123 ^| 30123^|30124
  echo.
  set /p STUDIO_TOPIC=topic [비우고 Enter면 word-id 입력]: 
)
if "!STUDIO_TOPIC!"=="" if "!WORD_IDS!"=="" (
  set /p WORD_IDS=word_id: 
)
:studio_vocab_parse_extra
set "EXTRA_ARGS="
:parse_extra_sv
if "%~1"=="" goto studio_vocab_run
set "EXTRA_ARGS=!EXTRA_ARGS! %1"
shift
goto parse_extra_sv
:studio_vocab_run
echo.
call :setup_py
%_PY% -m pip install -q gtts mutagen edge-tts 2>nul
if not "!WORD_IDS!"=="" (
  echo ^> [2] 단어장 / word_id=!WORD_IDS!
  %_PY% -m tools.tts_gen.build_vocab_meaning_ko --word-id "!WORD_IDS!" !EXTRA_ARGS!
) else (
  echo ^> [2] 단어장 / topic=!STUDIO_TOPIC!
  %_PY% -m tools.tts_gen.build_vocab_meaning_ko --studio-topic "!STUDIO_TOPIC!" !EXTRA_ARGS!
)
set "_ERR=!ERRORLEVEL!"
goto done

:mode_shorts_conv
set "SHC_TOPIC="
set "KO_SET_ID="

REM lvpd.bat tts 3 topic shangchai
if /I "%ARG2%"=="topic" (
  set "SHC_TOPIC=%ARG3%"
  if not "%ARG2%"=="" shift
  if not "%ARG2%"=="" shift
  goto shorts_conv_parse_extra
)

if not "%ARG2%"=="" (
  echo %ARG2%| findstr /r "^[0-9][0-9]*$" >nul
  if not errorlevel 1 (
    set "KO_SET_ID=%ARG2%"
    shift
    goto shorts_conv_parse_extra
  )
  set "SHC_TOPIC=%ARG2%"
  shift
  goto shorts_conv_parse_extra
)

echo.
echo [3] 숏츠 회화
echo   set_id ^(숫자^): shorts 클립의 ko_narration_id
echo   topic ^(문자^): shorts_conversation_clips.topic
echo   예: 15  또는  shangchai
echo.
set /p SHC_INPUT=set_id 또는 topic: 
if "!SHC_INPUT!"=="" goto fail
echo !SHC_INPUT!| findstr /r "^[0-9][0-9]*$" >nul
if not errorlevel 1 (
  set "KO_SET_ID=!SHC_INPUT!"
) else (
  set "SHC_TOPIC=!SHC_INPUT!"
)
goto shorts_conv_parse_extra

:shorts_conv_parse_extra
set "EXTRA_ARGS="
:parse_extra_shc
if "%~1"=="" (
  if not "!KO_SET_ID!"=="" goto shorts_conv_run_by_id
  if not "!SHC_TOPIC!"=="" goto shorts_conv_run_by_topic
  goto fail
)
set "EXTRA_ARGS=!EXTRA_ARGS! %1"
shift
goto parse_extra_shc

:shorts_conv_run_by_id
echo.
echo ^> [3] 숏츠 회화 / set_id=!KO_SET_ID!
call :setup_py
%_PY% -m pip install -q pysrt gtts mutagen edge-tts 2>nul
%_PY% -m tools.tts_gen.build_shorts_ko_narration --set-id !KO_SET_ID! !EXTRA_ARGS!
set "_ERR=!ERRORLEVEL!"
goto done

:shorts_conv_run_by_topic
echo.
echo ^> [3] 숏츠 회화 / topic=!SHC_TOPIC!
call :setup_py
%_PY% -m pip install -q pysrt gtts mutagen edge-tts 2>nul
%_PY% -m tools.tts_gen.build_shorts_ko_narration --topic "!SHC_TOPIC!" !EXTRA_ARGS!
set "_ERR=!ERRORLEVEL!"
goto done

:mode_shorts_vocab
set "VOCAB_KIND="
set "VOCAB_KEY="

if /I "%ARG2%"=="id" (
  set "VOCAB_KIND=id"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto shorts_vocab_parse_extra
)
if /I "%ARG2%"=="topic" (
  set "VOCAB_KIND=topic"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto shorts_vocab_parse_extra
)
if /I "%ARG2%"=="set" (
  set "VOCAB_KIND=set"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto shorts_vocab_parse_extra
)
if /I "%ARG2%"=="ko" (
  set "VOCAB_KIND=set"
  set "VOCAB_KEY=%ARG3%"
  shift
  goto shorts_vocab_parse_extra
)

if not "%ARG2%"=="" (
  echo %ARG2%| findstr /r "^100[0-9]$" >nul
  if not errorlevel 1 (
    set "VOCAB_KIND=set"
    set "VOCAB_KEY=%ARG2%"
    goto shorts_vocab_parse_extra
  )
  echo %ARG2%| findstr /r "^[0-9][0-9]*$" >nul
  if not errorlevel 1 (
    set "VOCAB_KIND=id"
    set "VOCAB_KEY=%ARG2%"
    goto shorts_vocab_parse_extra
  )
  set "VOCAB_KIND=topic"
  set "VOCAB_KEY=%ARG2%"
  goto shorts_vocab_parse_extra
)

echo.
echo [4] 숏츠 단어 모드
echo   4-1  shorts_vocabulary_clips 행 id
echo   4-2  topic
echo   4-3  ko_narration set_id ^(인트로^)
echo.
set /p VOCAB_SUB=선택 4-1 / 4-2 / 4-3: 
if /I "%VOCAB_SUB%"=="1" set "VOCAB_KIND=id"
if /I "%VOCAB_SUB%"=="4-1" set "VOCAB_KIND=id"
if /I "%VOCAB_SUB%"=="2" set "VOCAB_KIND=topic"
if /I "%VOCAB_SUB%"=="4-2" set "VOCAB_KIND=topic"
if /I "%VOCAB_SUB%"=="3" set "VOCAB_KIND=set"
if /I "%VOCAB_SUB%"=="4-3" set "VOCAB_KIND=set"
if "!VOCAB_KIND!"=="" goto fail
if /I "!VOCAB_KIND!"=="id" (
  set /p VOCAB_KEY=shorts_vocabulary_clips id: 
) else if /I "!VOCAB_KIND!"=="set" (
  set /p VOCAB_KEY=ko set_id 예 1001: 
) else (
  set /p VOCAB_KEY=topic: 
)
if "!VOCAB_KEY!"=="" goto fail

:shorts_vocab_parse_extra
set "EXTRA_ARGS="
:parse_extra_shv
if "%~1"=="" goto shorts_vocab_run
set "EXTRA_ARGS=!EXTRA_ARGS! %1"
shift
goto parse_extra_shv

:shorts_vocab_run
echo.
if /I "!VOCAB_KIND!"=="set" (
  echo ^> [4] 숏츠 단어 / ko set_id=!VOCAB_KEY!
) else if /I "!VOCAB_KIND!"=="id" (
  echo ^> [4] 숏츠 단어 / clips id=!VOCAB_KEY!
) else (
  echo ^> [4] 숏츠 단어 / topic=!VOCAB_KEY!
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
