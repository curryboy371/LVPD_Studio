@echo off
chcp 65001 >nul
cd /d "%~dp0"

set STUDIO=%~1

if /I "%STUDIO%"=="conversation" goto :run
if /I "%STUDIO%"=="vocabulary" goto :run

echo [화면 출력 전용] 회화/단어 모드 선택 실행 (F5 디버그와 유사)
echo  1^) 회화 모드 (conversation)
echo  2^) 단어 모드 (vocabulary)
set /p MODE_CHOICE=선택하세요 [1/2]:

if "%MODE_CHOICE%"=="1" set STUDIO=conversation
if "%MODE_CHOICE%"=="2" set STUDIO=vocabulary

if not defined STUDIO (
  echo.
  echo 잘못된 입력입니다. 사용 예:
  echo   record_output_select_mode.bat conversation
  echo   record_output_select_mode.bat vocabulary
  exit /b 1
)

:run
echo.
echo [%STUDIO%] 화면 출력(debug) 모드 실행
echo.

where py >nul 2>nul && (
  py -3 -m studio.runner --studio %STUDIO% --mode debug
) || (
  python -m studio.runner --studio %STUDIO% --mode debug
)

if errorlevel 1 (
  echo.
  echo 실패. pandas/opencv 등 미설치 또는 입력 데이터 문제일 수 있습니다.
  exit /b 1
)

echo.
pause

