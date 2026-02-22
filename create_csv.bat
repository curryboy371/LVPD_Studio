@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [테이블 CSV 생성] resource\table\video_data.xlsx -^> resource\csv\video_data.csv
echo.
where py >nul 2>nul && (py -3 run_create_csv.py) || (python run_create_csv.py)
if errorlevel 1 (
    echo.
    echo pandas 미설치 시: py -3 -m pip install pandas openpyxl
)
echo.
pause
