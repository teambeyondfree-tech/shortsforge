@echo off
echo ====================================
echo  ShortsForge 설치 시작
echo ====================================

echo.
echo [1/4] FFmpeg 설치 중...
winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements

echo.
echo [2/4] Python 가상환경 생성 중...
python -m venv venv

echo.
echo [3/4] 패키지 설치 중...
call venv\Scripts\activate
pip install -r requirements.txt

echo.
echo [4/4] .env 파일 생성 중...
if not exist .env (
    copy .env.example .env
    echo .env 파일이 생성되었습니다.
    echo .env 파일을 열어서 API 키를 입력하세요!
) else (
    echo .env 파일이 이미 존재합니다.
)

echo.
echo ====================================
echo  설치 완료!
echo.
echo  다음 단계:
echo  1. .env 파일에 GEMINI_API_KEY 입력
echo     발급: https://aistudio.google.com
echo.
echo  2. 실행:
echo     venv\Scripts\activate
echo     streamlit run app.py
echo ====================================
pause
