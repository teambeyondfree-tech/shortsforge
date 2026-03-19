"""
음성 합성 모듈
① Gemini 2.5 Flash TTS (기본, 무료)
② ElevenLabs Multilingual v2 (고품질 한국어, ELEVENLABS_API_KEY 필요)
"""
import time
import wave
from pathlib import Path
from google import genai
from google.genai import types
import config

# ── Gemini 목소리 목록 (한국어 추천)
VOICES = {
    "Kore":    "차분한 여성 ★경제/재테크/교육 추천",
    "Aoede":   "따뜻한 여성 ★릴스/라이프/자기계발 추천",
    "Puck":    "활기찬 남성 (자기계발/정보 추천)",
    "Leda":    "밝은 여성 (일상/브이로그 추천)",
    "Charon":  "묵직한 남성 (범죄/공포 전용)",
    "Fenrir":  "강인한 남성 (범죄/공포 전용)",
}

# ── ElevenLabs 한국어 지원 목소리 (Voice ID, 설명)
ELEVENLABS_VOICES = {
    "Rachel":  ("21m00Tcm4TlvDq8ikWAM", "부드러운 여성 — 다목적"),
    "Adam":    ("pNInz6obpgDQGcFmaJgB", "신뢰감 있는 남성 — 나레이션"),
    "Antoni":  ("ErXwobaYiN019PkySvjV", "젊은 남성 — 활기찬"),
    "Bella":   ("EXAVITQu4vr4xnSDxMaL", "따뜻한 여성 — 친근한"),
    "Josh":    ("TxGEqnHWrfWFTfGW9XjX", "묵직한 남성 — 권위 있는"),
}


def _retry_api_call(func, max_retries=3):
    """API 호출을 exponential backoff로 재시도"""
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


# 장르별 TTS 스타일 지시 — 자연스럽게, 과하지 않게
_GENRE_VOICE_DIRECTION = {
    "범죄": (
        "차분하고 낮은 톤으로 또렷하게 읽어주세요. "
        "과장하지 말고 담담하게, 사실을 전달하듯 읽어주세요. "
        "긴장감은 목소리 톤으로만 표현하고, 연기는 하지 마세요."
    ),
    "공포": (
        "조용하고 낮은 목소리로 천천히 읽어주세요. "
        "속삭이듯 차분하게, 과장 없이 읽어주세요."
    ),
    "재테크": (
        "명확하고 자신감 있는 목소리로 읽어주세요. "
        "숫자나 핵심 정보는 살짝 또렷하게 강조하되, 자연스러운 말투를 유지하세요. "
        "30대 경제 유튜버처럼 친근하고 신뢰감 있게 읽어주세요."
    ),
    "교육": (
        "친근하고 밝은 목소리로 읽어주세요. "
        "재미있는 사실을 알려주는 친구처럼 자연스럽게 읽어주세요."
    ),
    "자기계발": (
        "활기차고 긍정적인 목소리로 읽어주세요. "
        "동기부여가 되는 말투로, 자연스럽게 읽어주세요."
    ),
    "인스타_재테크": (
        "친근하고 자연스러운 말투로 읽어주세요. "
        "친한 친구에게 유용한 정보를 알려주듯, 가볍고 빠르게 읽어주세요."
    ),
    "인스타_자기계발": (
        "따뜻하고 공감 가는 목소리로 읽어주세요. "
        "자연스럽고 친근하게, 편안한 톤으로 읽어주세요."
    ),
    "인스타_라이프": (
        "밝고 친근한 목소리로 자연스럽게 읽어주세요."
    ),
    "인스타_정보": (
        "호기심 있고 경쾌한 목소리로 읽어주세요. "
        "신기한 정보를 알려주듯 자연스럽게 읽어주세요."
    ),
    "인스타_비즈": (
        "전문적이고 신뢰감 있는 목소리로 자연스럽게 읽어주세요."
    ),
}

_DEFAULT_VOICE_DIRECTION = (
    "자연스럽고 친근한 한국어로 읽어주세요. "
    "유튜브 쇼츠 나레이션처럼 명확하고 리듬감 있게, 과장 없이 읽어주세요."
)

# 후킹 첫 문장 강조 — 가볍게만 지시
_HOOK_PREFIX = (
    "첫 문장은 임팩트 있게, 이후는 자연스럽게 이어서 읽어주세요.\n\n"
)


def _generate_voice_gemini(narration: str, voice_name: str, output_path: Path, genre: str = "") -> Path:
    """Gemini TTS로 나레이션 음성 생성 → WAV 저장"""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    print(f"  음성 생성 중... [Gemini] ({voice_name})")

    direction  = _GENRE_VOICE_DIRECTION.get(genre, _DEFAULT_VOICE_DIRECTION)
    tts_prompt = f"{_HOOK_PREFIX}{direction}\n\n읽을 내용:\n{narration}"

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

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(config.AUDIO_RATE)
        wf.writeframes(audio_data)

    return output_path


def _generate_voice_elevenlabs(narration: str, voice_id: str, output_path: Path) -> Path:
    """
    ElevenLabs Multilingual v2로 한국어 고품질 음성 생성 → WAV 저장.
    output_format=pcm_24000 → raw PCM → wave 모듈로 WAV 변환.
    """
    try:
        from elevenlabs import ElevenLabs
    except ImportError:
        raise RuntimeError("elevenlabs 패키지가 없습니다. `pip install elevenlabs` 실행 후 재시도하세요.")

    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY가 설정되지 않았습니다. .env 파일에 추가하세요.")

    print(f"  음성 생성 중... [ElevenLabs] (voice_id={voice_id[:8]}...)")
    client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)

    def _call():
        return client.text_to_speech.convert(
            voice_id=voice_id,
            text=narration,
            model_id="eleven_multilingual_v2",
            output_format="pcm_24000",  # 24kHz 16-bit mono PCM
        )

    audio_chunks = _retry_api_call(_call)

    # PCM 청크를 모아 WAV로 저장
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)   # mono
        wf.setsampwidth(2)   # 16-bit
        wf.setframerate(24000)
        for chunk in audio_chunks:
            if chunk:
                wf.writeframes(chunk)

    return output_path


def generate_voice(
    narration: str,
    voice_name: str,
    output_path: Path,
    engine: str = "gemini",
    elevenlabs_voice_id: str = "",
    genre: str = "",
) -> Path:
    """
    나레이션 음성 생성.

    engine="gemini"      → Gemini TTS (기본, voice_name으로 목소리 선택)
    engine="elevenlabs"  → ElevenLabs (elevenlabs_voice_id 필요)
    """
    if engine == "elevenlabs":
        if not elevenlabs_voice_id:
            raise ValueError("ElevenLabs 사용 시 elevenlabs_voice_id를 지정해야 합니다.")
        return _generate_voice_elevenlabs(narration, elevenlabs_voice_id, output_path)
    else:
        return _generate_voice_gemini(narration, voice_name, output_path, genre=genre)
