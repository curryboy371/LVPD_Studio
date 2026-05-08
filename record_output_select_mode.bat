@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM print 로그가 녹화 중에도 즉시 콘솔에 보이게 함(파이썬 stdout 블록 버퍼링 방지)
set PYTHONUNBUFFERED=1

set STUDIO=%~1
set MODE_CHOICE=

if /I "%STUDIO%"=="conversation" goto :run
if /I "%STUDIO%"=="vocabulary" goto :run
if /I "%STUDIO%"=="combo" goto :run_combo

echo [화면 출력 전용] 회화/단어 모드 선택 실행 (F5 디버그와 유사)
echo  0^) 리소스 체크 모드 (topic 기반 누락 파일 점검)
echo  1^) 회화 모드 (conversation)
echo  2^) 단어 모드 (vocabulary)
echo  3^) 녹화 결합: 지정 topic만 ^(1^) 회화 전부 1파일 ^(2^) 단어 전부 1파일 ^(3^) ffmpeg 병합
set /p MODE_CHOICE=선택하세요 [0/1/2/3]:

if "%MODE_CHOICE%"=="0" set STUDIO=check
if "%MODE_CHOICE%"=="1" set STUDIO=conversation
if "%MODE_CHOICE%"=="2" set STUDIO=vocabulary
if "%MODE_CHOICE%"=="3" set STUDIO=combo

if not defined STUDIO (
  echo.
  echo 잘못된 입력입니다. 사용 예:
  echo   record_output_select_mode.bat conversation
  echo   record_output_select_mode.bat vocabulary
  echo   record_output_select_mode.bat combo
  echo   record_output_select_mode.bat check
  exit /b 1
)

if /I "%STUDIO%"=="combo" goto :run_combo
if /I "%STUDIO%"=="check" goto :run_check

:run
echo.
echo [%STUDIO%] 화면 출력(debug) 모드 실행
echo.

where py >nul 2>nul && (
  py -3 -u -m studio.runner --studio %STUDIO% --mode debug
) || (
  python -u -m studio.runner --studio %STUDIO% --mode debug
)

if errorlevel 1 (
  echo.
  echo 실패. pandas/opencv 등 미설치 또는 입력 데이터 문제일 수 있습니다.
  exit /b 1
)

echo.
pause
exit /b 0

:run_check
echo.
set "CHECK_TOPIC=%~2"
if defined CHECK_TOPIC goto :run_check_topic_ready
set /p CHECK_TOPIC=체크할 topic 입력 [전체는 엔터]:
:run_check_topic_ready
echo.
echo [check] topic=%CHECK_TOPIC%
where py >nul 2>nul && (
  py -3 -u -m tools.check_topic_resources --topic "%CHECK_TOPIC%"
) || (
  python -u -m tools.check_topic_resources --topic "%CHECK_TOPIC%"
)
if errorlevel 1 (
  echo.
  echo [check] 누락 리소스가 있습니다.
  pause
  exit /b 1
)
echo.
echo [check] 모든 리소스가 준비되었습니다.
pause
exit /b 0

:run_combo
echo.
echo [combo] 지정 topic만 사용합니다 ^(base_sentences / vocabulary_word_rows 의 topic^).
echo   1단계: 회화 ^(conversation^) 목록 끝까지 1회 녹화 → release\*.mp4
echo   2단계: 단어장 ^(vocabulary^) 해당 topic만 1회 녹화 → release\*.mp4
echo   3단계: 위 두 파일을 순서대로 ffmpeg 로 합칩니다 ^(회화 → 단어^).
echo.

set "RECORD_TOPIC=%~2"
if "%RECORD_TOPIC%"=="" (
  set /p RECORD_TOPIC=녹화할 topic 입력 [엔터=기본값 fruit_store / core.paths DEFAULT_STUDIO_TOPIC 동일]: 
)
REM 배치 기본값은 core\paths.py 의 DEFAULT_STUDIO_TOPIC 과 같아야 함 ^(현재 fruit_store^)
if "%RECORD_TOPIC%"=="" set "RECORD_TOPIC=fruit_store"
echo   ^> topic=%RECORD_TOPIC%
echo.

if not exist "release" mkdir "release"
set "CONV_MAX_SEC=900"
set "VOCAB_MAX_SEC=1800"
set "VOCAB_FALLBACK_SEC=90"

set "CONV_VIDEO="
set "VOCAB_VIDEO="
set "MERGED_OUT="

echo -------- 1/2 회화 녹화 ^(topic=%RECORD_TOPIC%^) --------
call :run_record_and_pick_latest conversation CONV_VIDEO %CONV_MAX_SEC%
if errorlevel 1 exit /b 1

echo.
echo -------- 2/2 단어장 녹화 ^(topic=%RECORD_TOPIC%^) --------
call :run_record_and_pick_latest vocabulary VOCAB_VIDEO %VOCAB_MAX_SEC%
if errorlevel 1 exit /b 1

if not defined CONV_VIDEO (
  echo [오류] conversation 녹화 결과를 찾지 못했습니다.
  exit /b 1
)
if not defined VOCAB_VIDEO (
  echo [오류] vocabulary 녹화 결과를 찾지 못했습니다.
  exit /b 1
)
if /I "%CONV_VIDEO%"=="%VOCAB_VIDEO%" (
  echo [오류] 두 녹화 결과 파일이 동일합니다. 녹화가 정상 생성됐는지 확인하세요.
  exit /b 1
)

set "LIST_FILE=%TEMP%\lvpd_concat_%RANDOM%_%RANDOM%.txt"
> "%LIST_FILE%" echo file '%CONV_VIDEO:\=/%'
>> "%LIST_FILE%" echo file '%VOCAB_VIDEO:\=/%'

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"`) do set "TS=%%A"
set "MERGED_OUT=%CD%\release\record_combo_%RECORD_TOPIC%_%TS%.mp4"

echo.
echo -------- 3/3 병합 ^(회화 + 단어, topic=%RECORD_TOPIC%^) --------
echo [merge] %CONV_VIDEO%
echo         + %VOCAB_VIDEO%
echo         = %MERGED_OUT%
echo.

ffmpeg -y -f concat -safe 0 -i "%LIST_FILE%" -c copy "%MERGED_OUT%"
if errorlevel 1 (
  del /q "%LIST_FILE%" >nul 2>nul
  echo [오류] 병합 실패. ffmpeg 설치/경로 또는 두 영상의 코덱/해상도/fps 호환성을 확인하세요.
  exit /b 1
)

del /q "%LIST_FILE%" >nul 2>nul
echo.
echo [완료] 병합 영상 생성: %MERGED_OUT%
echo.
pause
exit /b 0

:run_record_and_pick_latest
set "TARGET_STUDIO=%~1"
set "OUT_VAR=%~2"
set "TARGET_MAX_SEC=%~3"
set "BEFORE_FILE="
set "AFTER_FILE="

echo [record] %TARGET_STUDIO% 녹화 시작...

for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "$f=Get-ChildItem -Path '%CD%\release' -File -Filter *.mp4 | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){$f.FullName}"`) do (
  set "BEFORE_FILE=%%F"
)

call :run_record %TARGET_STUDIO% %TARGET_MAX_SEC%
if errorlevel 1 (
  if /I "%TARGET_STUDIO%"=="vocabulary" (
    echo [warn] vocabulary until-content-done 실패. 고정 길이[%VOCAB_FALLBACK_SEC%초] 녹화로 재시도합니다.
    call :run_record_fixed vocabulary %VOCAB_FALLBACK_SEC%
    if errorlevel 1 (
      echo [오류] %TARGET_STUDIO% record 재시도도 실패
      exit /b 1
    )
  ) else (
    echo [오류] %TARGET_STUDIO% record 실행 실패
    exit /b 1
  )
)

for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "$f=Get-ChildItem -Path '%CD%\release' -File -Filter *.mp4 | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){$f.FullName}"`) do (
  set "AFTER_FILE=%%F"
)

if not defined AFTER_FILE (
  if /I "%TARGET_STUDIO%"=="vocabulary" (
    echo [warn] vocabulary 신규 mp4 감지 실패. 고정 길이[%VOCAB_FALLBACK_SEC%초] 녹화 1회 더 시도합니다.
    call :run_record_fixed vocabulary %VOCAB_FALLBACK_SEC%
    if errorlevel 1 (
      echo [오류] %TARGET_STUDIO% record 추가 재시도 실패
      exit /b 1
    )
    for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "$f=Get-ChildItem -Path '%CD%\release' -File -Filter *.mp4 | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){$f.FullName}"`) do (
      set "AFTER_FILE=%%F"
    )
  )
  if not defined AFTER_FILE (
    echo [오류] release 폴더에서 신규 mp4 결과를 찾지 못했습니다. [%TARGET_STUDIO%]
    exit /b 1
  )
)

if defined BEFORE_FILE (
  if /I "%AFTER_FILE%"=="%BEFORE_FILE%" (
    if /I "%TARGET_STUDIO%"=="vocabulary" (
      echo [warn] vocabulary 신규 파일이 없어 [%VOCAB_FALLBACK_SEC%초] 녹화를 1회 더 시도합니다.
      call :run_record_fixed vocabulary %VOCAB_FALLBACK_SEC%
      if errorlevel 1 (
        echo [오류] %TARGET_STUDIO% 추가 재시도 실패
        exit /b 1
      )
      for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "$f=Get-ChildItem -Path '%CD%\release' -File -Filter *.mp4 | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){$f.FullName}"`) do (
        set "AFTER_FILE=%%F"
      )
    )
  )
)

if defined BEFORE_FILE (
  if /I "%AFTER_FILE%"=="%BEFORE_FILE%" (
    echo [오류] %TARGET_STUDIO% 녹화 후에도 신규 mp4가 생성되지 않았습니다.
    exit /b 1
  )
)

set "%OUT_VAR%=%AFTER_FILE%"
echo [record] %TARGET_STUDIO% 완료: %AFTER_FILE%
exit /b 0

:run_record
set "R_STUDIO=%~1"
set "R_MAX_SEC=%~2"
where py >nul 2>nul && (
  py -3 -u -m studio.runner --studio %R_STUDIO% --mode record --record-until-content-done --record-max-sec %R_MAX_SEC% --topic "%RECORD_TOPIC%"
) || (
  python -u -m studio.runner --studio %R_STUDIO% --mode record --record-until-content-done --record-max-sec %R_MAX_SEC% --topic "%RECORD_TOPIC%"
)
exit /b %errorlevel%

:run_record_fixed
set "R_STUDIO=%~1"
set "R_DURATION=%~2"
where py >nul 2>nul && (
  py -3 -u -m studio.runner --studio %R_STUDIO% --mode record --record-duration %R_DURATION% --topic "%RECORD_TOPIC%"
) || (
  python -u -m studio.runner --studio %R_STUDIO% --mode record --record-duration %R_DURATION% --topic "%RECORD_TOPIC%"
)
exit /b %errorlevel%
