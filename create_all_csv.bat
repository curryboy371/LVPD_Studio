@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [테이블 CSV 일괄 생성] resource\table\*.xlsx -^> resource\csv\
echo   base_sentences, words, sub_sentences, vocabulary_word_rows
echo.
where py >nul 2>nul && (py -3 -m tools.csv_gen) || (python -m tools.csv_gen)
if errorlevel 1 (
    echo pandas 미설치 시: py -3 -m pip install pandas openpyxl
)
echo.
pause
