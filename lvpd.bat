@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "PYTHONUNBUFFERED=1"

REM lvpd.bat [csv|tts|run|f5|6-9|audio|hanzi|help] [args...]

set "CAT=%~1"
if /I "%CAT%"=="1" set "CAT=csv"
if /I "%CAT%"=="2" (
  if not "%~2"=="" (
    call :do_tts 2 %~2 %~3 %~4 %~5 %~6 %~7 %~8 %~9
    exit /b !ERRORLEVEL!
  )
  set "CAT=tts"
)
if /I "%CAT%"=="3" set "CAT=run"
if /I "%CAT%"=="record" set "CAT=run"
if /I "%CAT%"=="4" set "CAT=audio"
if /I "%CAT%"=="5" set "CAT=hanzi"
if /I "%CAT%"=="f5" set "CAT=f5"
if /I "%CAT%"=="debug" set "CAT=f5"
if /I "%CAT%"=="help" set "CAT=help"
if /I "%CAT%"=="-h" set "CAT=help"
if /I "%CAT%"=="--help" set "CAT=help"

if "%CAT%"=="6" shift & call :f5_shorts_vocab %1 & exit /b %ERRORLEVEL%
if "%CAT%"=="7" shift & call :f5_shorts_conv %1 & exit /b %ERRORLEVEL%
if "%CAT%"=="8" shift & call :f5_vocabulary %1 & exit /b %ERRORLEVEL%
if "%CAT%"=="9" shift & call :f5_conversation %1 & exit /b %ERRORLEVEL%

if not "%CAT%"=="" goto run_cli
goto main_menu

:run_cli
shift
if /I "%CAT%"=="csv" goto cli_csv
if /I "%CAT%"=="tts" goto cli_tts
if /I "%CAT%"=="run" goto cli_run
if /I "%CAT%"=="f5" goto cli_f5
if /I "%CAT%"=="audio" goto cli_audio
if /I "%CAT%"=="hanzi" goto cli_hanzi
if /I "%CAT%"=="editor" goto cli_table_editor
if /I "%CAT%"=="table-editor" goto cli_table_editor
if /I "%CAT%"=="help" goto show_help
echo [오류] 알 수 없는 작업: %CAT%
exit /b 1

:cli_csv
call :do_csv
exit /b %ERRORLEVEL%

:cli_tts
call :do_tts %*
exit /b %ERRORLEVEL%

:cli_run
call :do_run %*
exit /b %ERRORLEVEL%

:cli_f5
set "F5_MODE=%~1"
set "F5_TOPIC=%~2"
if /I "%F5_MODE%"=="6" set "F5_MODE=shorts-vocab"
if /I "%F5_MODE%"=="7" set "F5_MODE=shorts-conv"
if /I "%F5_MODE%"=="8" set "F5_MODE=vocabulary"
if /I "%F5_MODE%"=="9" set "F5_MODE=conversation"
if /I "%F5_MODE%"=="shorts-vocabulary" set "F5_MODE=shorts-vocab"
if /I "%F5_MODE%"=="shorts_vocab" set "F5_MODE=shorts-vocab"
if /I "%F5_MODE%"=="shorts-conversation" set "F5_MODE=shorts-conv"
if /I "%F5_MODE%"=="shorts_conv" set "F5_MODE=shorts-conv"
if /I "%F5_MODE%"=="shorts-vocab" goto f5_shorts_vocab
if /I "%F5_MODE%"=="shorts-conv" goto f5_shorts_conv
if /I "%F5_MODE%"=="vocabulary" goto f5_vocabulary
if /I "%F5_MODE%"=="conversation" goto f5_conversation
call :pick_f5_mode
exit /b %ERRORLEVEL%

:cli_audio
call :do_audio
exit /b %ERRORLEVEL%

:cli_hanzi
call :do_hanzi %*
exit /b %ERRORLEVEL%

:cli_table_editor
call :do_table_editor
exit /b %ERRORLEVEL%

:main_menu
cls
echo.
echo ========================================================
echo   LVPD Studio 배치 - lvpd.bat
echo ========================================================
echo.
echo  [데이터/도구]
echo   1  CSV 생성
echo   2  TTS 생성
echo   4  비디오-^>MP3
echo   5  한자 프레임
echo   E  테이블 편집기 ^(extra.table_editor^)
echo.
echo  [F5 화면 debug - studio.runner]
echo   6  숏츠 단어   (shorts + vocabulary)
echo   7  숏츠 회화   (shorts + conversation)
echo   8  단어장      (vocabulary)
echo   9  회화        (conversation)
echo.
echo  [기타]
echo   3  실행/녹화 메뉴
echo.
echo   H  도움말    0  종료
echo.
set "MENU_CHOICE="
set /p "MENU_CHOICE=선택: "

if /I "!MENU_CHOICE!"=="0" exit /b 0
if /I "!MENU_CHOICE!"=="H" goto show_help
if /I "!MENU_CHOICE!"=="E" call :do_table_editor
if "!MENU_CHOICE!"=="1" call :do_csv
if "!MENU_CHOICE!"=="2" call :do_tts
if "!MENU_CHOICE!"=="3" call :do_run
if "!MENU_CHOICE!"=="4" call :do_audio
if "!MENU_CHOICE!"=="5" call :do_hanzi
if "!MENU_CHOICE!"=="6" call :f5_shorts_vocab
if "!MENU_CHOICE!"=="7" call :f5_shorts_conv
if "!MENU_CHOICE!"=="8" call :f5_vocabulary
if "!MENU_CHOICE!"=="9" call :f5_conversation
if not "!MENU_CHOICE!"=="1" if not "!MENU_CHOICE!"=="2" if not "!MENU_CHOICE!"=="3" if not "!MENU_CHOICE!"=="4" if not "!MENU_CHOICE!"=="5" if not "!MENU_CHOICE!"=="6" if not "!MENU_CHOICE!"=="7" if not "!MENU_CHOICE!"=="8" if not "!MENU_CHOICE!"=="9" (
  if not "!MENU_CHOICE!"=="" echo [오류] 0~9 또는 H
)
echo.
if not "%SKIP_PAUSE%"=="1" pause
goto main_menu

:pick_f5_mode
echo.
echo [F5 debug] 6=숏츠단어 7=숏츠회화 8=단어장 9=회화
set "F5PICK="
set /p "F5PICK=선택: "
if "!F5PICK!"=="6" call :f5_shorts_vocab & goto :eof
if "!F5PICK!"=="7" call :f5_shorts_conv & goto :eof
if "!F5PICK!"=="8" call :f5_vocabulary & goto :eof
if "!F5PICK!"=="9" call :f5_conversation & goto :eof
echo [오류] 6~9
exit /b 1

:prompt_topic
set "DBG_TOPIC=%~1"
if not "%~2"=="" set "DBG_TOPIC=%~2"
if not "!DBG_TOPIC!"=="" goto :eof
set /p "DBG_TOPIC=topic [엔터=!DBG_DEFAULT!]: "
if "!DBG_TOPIC!"=="" set "DBG_TOPIC=!DBG_DEFAULT!"
goto :eof

:f5_shorts_vocab
set "DBG_DEFAULT=bao"
call :prompt_topic %F5_TOPIC%
echo.
echo [F5] 숏츠 단어 topic=!DBG_TOPIC!
call :run_debug shorts vocabulary "!DBG_TOPIC!"
goto :eof

:f5_shorts_conv
set "DBG_DEFAULT=where"
call :prompt_topic %F5_TOPIC%
echo.
echo [F5] 숏츠 회화 topic=!DBG_TOPIC!
call :run_debug shorts conversation "!DBG_TOPIC!"
goto :eof

:f5_vocabulary
set "DBG_DEFAULT=fruit_store"
call :prompt_topic %F5_TOPIC%
echo.
echo [F5] 단어장 topic=!DBG_TOPIC!
call :run_debug vocabulary "" "!DBG_TOPIC!"
goto :eof

:f5_conversation
set "DBG_DEFAULT=fruit_store"
call :prompt_topic %F5_TOPIC%
echo.
echo [F5] 회화 topic=!DBG_TOPIC!
call :run_debug conversation "" "!DBG_TOPIC!"
goto :eof

:run_debug
call :setup_py
set "DBG_STUDIO=%~1"
set "DBG_SHORTS_TYPE=%~2"
set "DBG_TOPIC=%~3"
set "DBG_EXTRA="
if not "!DBG_TOPIC!"=="" set "DBG_EXTRA=--topic "!DBG_TOPIC!""
if /I "!DBG_STUDIO!"=="shorts" (
  %_PY% -u -m studio.runner --studio shorts --shorts-type !DBG_SHORTS_TYPE! --mode debug !DBG_EXTRA!
) else (
  %_PY% -u -m studio.runner --studio !DBG_STUDIO! --mode debug !DBG_EXTRA!
)
if errorlevel 1 echo [오류] 실행 실패. CSV/에셋/TTS 확인.
goto :eof

:show_help
echo.
echo   lvpd.bat 6 [topic]     숏츠 단어 F5
echo   lvpd.bat 7 [topic]     숏츠 회화 F5
echo   lvpd.bat 8 [topic]     단어장 F5
echo   lvpd.bat 9 [topic]     회화 F5
echo   lvpd.bat f5 shorts-vocab bao
echo   lvpd.bat tts 1 fruit_store     회화 topic -^> ko_sub_*.mp3
echo   lvpd.bat tts 2 hair            단어장 topic -^> ko_word_*
echo   lvpd.bat tts 3 15              숏츠 회화 ko set_id
echo   lvpd.bat tts 3 topic shangchai 숏츠 회화 topic
echo   lvpd.bat tts 4 topic jingyesi  숏츠 단어 topic
echo   lvpd.bat tts 4 set 1001        숏츠 단어 인트로 set
echo   lvpd.bat csv / tts / run / audio / hanzi / editor
echo   lvpd.bat editor              테이블 편집기 GUI
echo.
if not "%SKIP_PAUSE%"=="1" pause
exit /b 0

:do_csv
call :setup_py
echo.
echo [CSV 생성]
%_PY% -m tools.csv_gen
if errorlevel 1 echo pandas: %_PY% -m pip install pandas openpyxl
goto :eof

:do_tts
set "SKIP_PAUSE=1"
call "%~dp0batch_tts.bat" %*
set "SKIP_PAUSE="
goto :eof

:do_run
set "SKIP_PAUSE=1"
call "%~dp0record_output_select_mode.bat" %*
set "SKIP_PAUSE="
goto :eof

:do_audio
call :setup_py
echo.
echo [비디오 오디오 분리]
%_PY% run_extract_audio.py
goto :eof

:do_hanzi
call :setup_py
echo.
echo [한자 프레임]
%_PY% -m pip install -q playwright 2>nul
%_PY% tools\hanzi\render_svg_frames.py --skip-existing %*
goto :eof

:do_table_editor
call :setup_py
echo.
echo [테이블 편집기]
%_PY% -m extra.table_editor
goto :eof

:setup_py
set "PYTHONPATH=%CD%"
set "_PY="
where py >nul 2>&1 && set "_PY=py -3"
if not defined _PY set "_PY=python"
goto :eof
