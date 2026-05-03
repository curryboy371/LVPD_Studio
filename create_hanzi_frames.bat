@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [한자 프레임 생성] resource\svgs\*.svg -^> resource\hanzi_frames\{코드포인트}\
echo   사전 준비: pip install playwright ^&^& python -m playwright install chromium
echo.
echo 기본: words.csv 글자 중 SVG가 있는 것만 대상, 이미 meta.json+PNG 완료된 폴더는 건너뜀 ^(--skip-existing^)
echo   전부 다시 렌더: %~nx0 --force   또는 동일 옵션을 render_svg_frames.py에 전달
echo   전체 SVG: %~nx0 --all-svgs
echo   특정 글자: %~nx0 --codepoints 33600 33821
echo.

where py >nul 2>nul && (
  py -3 tools\hanzi\render_svg_frames.py --skip-existing %*
) || (
  python tools\hanzi\render_svg_frames.py --skip-existing %*
)
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% NEQ 0 (
  echo.
  echo 실패 시 playwright/Chromium 설치를 확인하세요.
)
echo.
if not "%SKIP_PAUSE%"=="1" pause
exit /b %EXITCODE%
