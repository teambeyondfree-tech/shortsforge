@echo off
chcp 65001 > nul
title ShortsForge

echo.
echo  ================================
echo   ShortsForge AI 콘텐츠 생성기
echo   유튜브 쇼츠 / 인스타 캐러셀 / 릴스
echo  ================================
echo.

:: 현재 배치파일 위치로 이동
cd /d "%~dp0"

:: venv 존재 확인
if not exist "venv\Scripts\python.exe" (
    echo  [오류] 가상환경이 없습니다.
    echo  setup.bat 을 먼저 실행하세요.
    echo.
    pause
    exit /b 1
)

:: .env 파일 확인
if not exist ".env" (
    echo  [경고] .env 파일이 없습니다.
    if exist ".env.example" (
        copy ".env.example" ".env" > nul
        echo  .env 파일을 생성했습니다.
    )
    echo  .env 파일에 GEMINI_API_KEY 를 입력하세요.
    echo.
    pause
    exit /b 1
)

:: API 키 입력 여부 확인
findstr /C:"GEMINI_API_KEY=" .env | findstr /V /C:"GEMINI_API_KEY=$" | findstr /V /C:"GEMINI_API_KEY=your" > nul
if errorlevel 1 (
    echo  [경고] GEMINI_API_KEY 가 입력되지 않았습니다.
    echo  .env 파일을 열어서 API 키를 입력하세요.
    echo.
    start notepad ".env"
    pause
    exit /b 1
)

:: Streamlit 실행 (브라우저는 서버 준비 후 자동 열림)
echo  앱을 시작합니다. 잠시만 기다려주세요...
echo  (수동: http://localhost:8501)
echo.

call venv\Scripts\activate
streamlit run app.py --server.port 8501 --server.headless false --browser.serverAddress localhost --browser.gatherUsageStats false

pause
