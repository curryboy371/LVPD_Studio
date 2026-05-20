@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"

REM LVPD Studio 통합 배치 - lvpd.bat [csv|tts|run|audio|hanzi|help] [args...]

set "CAT=%~1"
if /I "%CAT%"=="1" set "CAT=csv"
if /I "%CAT%"=="create-csv" set "CAT=csv"
if /I "%CAT%"=="2" set "CAT=tts"
if /I "%CAT%"=="3" set "CAT=run"
if /I "%CAT%"=="record" set "CAT=run"
if /I "%CAT%"=="play" set "CAT=run"
if /I "%CAT%"=="4" set "CAT=audio"
if /I "%CAT%"=="extract" set "CAT=audio"
if /I "%CAT%"=="5" set "CAT=hanzi"
if /I "%CAT%"=="frames" set "CAT=hanzi"
if /I "%CAT%"=="help" set "CAT=help"
if /I "%CAT%"=="-h" set "CAT=help"
if /I "%CAT%"=="--help" set "CAT=help"

if not "%CAT%"=="" goto run_cli

goto main_menu

:run_cli
shift
if /I "%CAT%"=="csv" goto cli_csv
if /I "%CAT%"=="tts" goto cli_tts
if /I "%CAT%"=="run" goto cli_run
if /I "%CAT%"=="audio" goto cli_audio
if /I "%CAT%"=="hanzi" goto cli_hanzi
if /I "%CAT%"=="help" goto show_help
echo [오류] 알 수 없는 작업: %CAT%  (help: lvpd.bat help)
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

:cli_audio
call :do_audio
exit /b %ERRORLEVEL%

:cli_hanzi
call :do_hanzi %*
exit /b %ERRORLEVEL%

:main_menu
cls
echo.
echo ========================================================
echo   LVPD Studio 배치 (통합) - lvpd.bat
echo ========================================================
echo.
echo   1  CSV 생성       (resource\table -^> resource\csv)
echo   2  TTS 생성       (숏츠 단어/회화, words word_id)
echo   3  실행/녹화      (회화, 단어, 숏츠, combo...)
echo   4  비디오-^>MP3    (resource\video)
echo   5  한자 프레임     (SVG -^> hanzi_frames)
echo.
echo   H  도움말    0  종료
echo.
set "MENU_CHOICE="
set /p "MENU_CHOICE=선택 (0-5, H): "

if /I "!MENU_CHOICE!"=="0" exit /b 0
if /I "!MENU_CHOICE!"=="H" goto show_help
if "!MENU_CHOICE!"=="1" call :do_csv
if "!MENU_CHOICE!"=="2" call :do_tts
if "!MENU_CHOICE!"=="3" call :do_run
if "!MENU_CHOICE!"=="4" call :do_audio
if "!MENU_CHOICE!"=="5" call :do_hanzi
if not "!MENU_CHOICE!"=="1" if not "!MENU_CHOICE!"=="2" if not "!MENU_CHOICE!"=="3" if not "!MENU_CHOICE!"=="4" if not "!MENU_CHOICE!"=="5" (
  if not "!MENU_CHOICE!"=="" echo [오류] 0~5 또는 H
)
echo.
if not "%SKIP_PAUSE%"=="1" pause
goto main_menu

:show_help
echo.
echo   lvpd.bat
echo   lvpd.bat csv
echo   lvpd.bat tts 1 id 1
echo   lvpd.bat tts 2 1000
echo   lvpd.bat tts 3 30123
echo   lvpd.bat run conversation
echo   lvpd.bat run shorts_vocabulary bao
echo   lvpd.bat audio
echo   lvpd.bat hanzi --force
echo.
if not "%SKIP_PAUSE%"=="1" pause
exit /b 0

:do_csv
call :setup_py
echo.
echo [CSV 생성]
%_PY% -m tools.csv_gen
if errorlevel 1 (
  echo pandas: %_PY% -m pip install pandas openpyxl
)
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
%_PY% tools\hanzi\render_svg_frames.py --skip-existing %*
goto :eof

:setup_py
set "PYTHONPATH=%CD%"
set "_PY="
where py >nul 2>&1 && set "_PY=py -3"
if not defined _PY set "_PY=python"
goto :eof
