import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# API 키 — 로컬 .env 우선, Streamlit Cloud secrets 폴백
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    try:
        import streamlit as st
        GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass

# 경로
BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR   = BASE_DIR / "temp"
ASSETS_DIR = BASE_DIR / "assets"
BGM_DIR    = ASSETS_DIR / "bgm"
FONTS_DIR  = ASSETS_DIR / "fonts"
LUTS_DIR   = ASSETS_DIR / "luts"

for d in [OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# 영상 설정 (9:16 세로형 쇼츠)
VIDEO_W   = 1080
VIDEO_H   = 1920
VIDEO_FPS = 30

# 오디오 설정
BGM_VOLUME = 0.20    # 목소리 대비 20%
AUDIO_RATE = 24000   # Gemini TTS 출력 샘플레이트

# 자막 폰트 — 플랫폼별 분기
if sys.platform == "win32":
    SUBTITLE_FONT = "Malgun Gothic"
else:
    SUBTITLE_FONT = "NanumGothic"   # Streamlit Cloud (Linux) — packages.txt에서 설치

SUBTITLE_FONT_SIZE = 80
SUBTITLE_COLOR     = "&H00FFFFFF"
SUBTITLE_OUTLINE   = "&H00000000"
SUBTITLE_OUTLINE_W = 5

# Gemini 모델
MODEL_SCRIPT = "gemini-2.0-flash"
MODEL_TTS    = "gemini-2.5-flash-preview-tts"
MODEL_IMAGE  = "imagen-4.0-fast-generate-001"
