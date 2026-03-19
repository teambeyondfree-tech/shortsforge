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
    "Kore":    "차분한 여성 (재테크/교육 추천)",
    "Charon":  "묵직한 남성 (범죄/공포 추천)",
    "Puck":    "활기찬 남성 (자기계발 추천)",
    "Aoede":   "따뜻한 여성 (생활정보 추천)",
    "Fenrir":  "강인한 남성 (스포츠/도전 추천)",
    "Leda":    "밝은 여성 (일상/브이로그 추천)",
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


# 장르별 TTS 디렉팅 — 배우에게 연기 지시하듯 구체적으로 작성
_GENRE_VOICE_DIRECTION = {
    "범죄": (
        "낮고 긴장감 있는 목소리로 읽어주세요. "
        "마치 실제 사건을 전달하는 탐사보도 기자처럼, 충격적인 부분 직전에 살짝 멈추고 "
        "그 다음 문장을 더 또렷하게 강조해주세요. 전체적으로 차분하지만 섬뜩한 분위기를 유지하세요."
    ),
    "공포": (
        "속삭이듯 천천히, 그러면서도 또렷하게 읽어주세요. "
        "무서운 장면이나 반전 포인트 직전에 0.5초 정도 침묵을 두고, "
        "그 다음 문장은 조금 더 낮고 천천히 읽어서 공포감을 극대화하세요. "
        "마치 귀에 대고 비밀을 말해주는 것처럼 읽어주세요."
    ),
    "재테크": (
        "자신감 있고 또렷한 목소리로 읽어주세요. "
        "중요한 숫자나 금액이 나올 때는 살짝 강조해서 확실하게 전달하고, "
        "전반적으로 약간 빠른 템포로 에너지 있게 읽어주세요. "
        "성공한 재테크 유튜버가 핵심 정보를 전달하는 느낌으로요."
    ),
    "교육": (
        "친근하고 명확한 목소리로 읽어주세요. "
        "각 문장의 핵심 단어를 살짝 강조하고, 새로운 개념이 나올 때는 "
        "잠깐 간격을 두어 청자가 흡수할 수 있게 해주세요. "
        "흥미롭고 재미있게, 마치 신기한 사실을 알려주는 친구처럼 읽어주세요."
    ),
    "자기계발": (
        "에너지 넘치고 동기부여가 되는 목소리로 읽어주세요. "
        "청중이 지금 당장 행동하게 만들 듯이 열정적으로, "
        "중요한 행동 지침은 강하게 강조해서 읽어주세요. "
        "전체적으로 빠르고 파워풀한 템포를 유지하세요."
    ),
    "인스타_재테크": (
        "트렌디하고 친근한 말투로 읽어주세요. "
        "첫 문장(후킹)은 특히 강하고 임팩트 있게, "
        "이후 내용은 친한 친구에게 꿀팁을 알려주듯 빠르고 생생하게 읽어주세요. "
        "인스타 릴스 특유의 리듬감을 살려주세요."
    ),
    "인스타_자기계발": (
        "공감되고 따뜻하면서도 에너지 넘치는 목소리로 읽어주세요. "
        "후킹 문장은 약간 느리게 강조하고, 이후는 친구처럼 빠르게 이야기해주세요. "
        "리듬감 있게 읽어주세요."
    ),
    "인스타_라이프": (
        "밝고 친근하며 생동감 있는 목소리로 읽어주세요. "
        "마치 카페에서 친한 친구에게 이야기하듯 자연스럽고 활기차게 읽어주세요."
    ),
    "인스타_정보": (
        "놀람과 호기심이 담긴 목소리로 읽어주세요. "
        "반전 정보나 충격적인 사실 앞에서 살짝 강조하고 잠깐 멈추어 임팩트를 주세요. "
        "전체적으로 빠르고 신기하다는 느낌을 살려주세요."
    ),
    "인스타_비즈": (
        "전문적이면서도 현실감 있는 목소리로 읽어주세요. "
        "공감 포인트에서는 약간 감정을 실어서 '맞아, 나도 그랬어'라는 느낌을 주고, "
        "핵심 인사이트는 자신감 있게 강조해주세요."
    ),
}

_DEFAULT_VOICE_DIRECTION = (
    "자연스럽고 감정이 담긴 한국어로 읽어주세요. "
    "중요한 단어는 살짝 강조하고, 문장 사이에 자연스러운 간격을 두어 "
    "유튜브 쇼츠 나레이션처럼 리듬감 있게 읽어주세요."
)


def _generate_voice_gemini(narration: str, voice_name: str, output_path: Path, genre: str = "") -> Path:
    """Gemini TTS로 나레이션 음성 생성 → WAV 저장"""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    print(f"  음성 생성 중... [Gemini] ({voice_name})")

    direction = _GENRE_VOICE_DIRECTION.get(genre, _DEFAULT_VOICE_DIRECTION)
    tts_prompt = f"{direction}\n\n읽을 내용:\n{narration}"

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
