@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [회화+단어] 콘텐츠 끝까지 오프스크린 녹화 -^> release\ (상한 1시간, 늘리려면 RECORD_MAX_SEC 수정)
echo.
set RECORD_MAX_SEC=3600
where py >nul 2>nul && (
  py -3 -m studio.runner --studio conversation_then_words --mode record --record-until-content-done --record-max-sec %RECORD_MAX_SEC%
) || (
  python -m studio.runner --studio conversation_then_words --mode record --record-until-content-done --record-max-sec %RECORD_MAX_SEC%
)
if errorlevel 1 (
  echo.
  echo 실패. pandas/opencv 등 미설치일 수 있습니다.
  exit /b 1
)
echo.
pause

