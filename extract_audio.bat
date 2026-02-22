@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [비디오 오디오 분리] resource\video 하위 비디오 -^> 같은 이름 MP3 추출
echo.
where py >nul 2>nul && (py -3 run_extract_audio.py) || (python run_extract_audio.py)
echo.
pause
