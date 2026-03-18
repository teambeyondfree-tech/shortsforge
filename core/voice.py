"""
음성 합성 모듈
Gemini 2.5 Flash TTS → WAV 파일 생성
"""
import time
import wave
from pathlib import Path
from google import genai
from google.genai import types
import config

# 목소리 목록 (한국어 추천)
VOICES = {
    "Kore":    "차분한 여성 (재테크/교육 추천)",
    "Charon":  "묵직한 남성 (범죄/공포 추천)",
    "Puck":    "활기찬 남성 (자기계발 추천)",
    "Aoede":   "따뜻한 여성 (생활정보 추천)",
    "Fenrir":  "강인한 남성 (스포츠/도전 추천)",
    "Leda":    "밝은 여성 (일상/브이로그 추천)",
}


def _retry_api_call(func, max_retries=3):
    """Gemini API 호출을 exponential backoff로 재시도"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"    [재시도 {attempt+1}/{max_retries}] {e} → {wait}초 후 재시도")
            time.sleep(wait)


def get_voice_duration(audio_path: Path) -> float:
    """WAV 파일의 실제 재생 길이(초)를 반환"""
    with wave.open(str(audio_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / rate


def generate_voice(narration: str, voice_name: str, output_path: Path) -> Path:
    """
    Gemini TTS로 나레이션 음성 생성 → WAV 저장.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    print(f"  음성 생성 중... ({voice_name})")

    # 구어체 연출을 위한 프롬프트 래핑
    tts_prompt = (
        f"자연스럽고 감정이 담긴 한국어로 읽어주세요. "
        f"너무 빠르지도 느리지도 않게, 유튜브 나레이션처럼요: {narration}"
    )

    def _call():
        return client.models.generate_content(
            model=config.MODEL_TTS,
            contents=tts_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name,
                        )
                    )
                ),
            ),
        )

    response = _retry_api_call(_call)

    audio_data = response.candidates[0].content.parts[0].inline_data.data

    # WAV 파일로 저장
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)                   # 모노
        wf.setsampwidth(2)                   # 16-bit
        wf.setframerate(config.AUDIO_RATE)   # 24kHz
        wf.writeframes(audio_data)

    return output_path
