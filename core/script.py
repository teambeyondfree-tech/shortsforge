"""
스크립트 생성 모듈
Gemini 2.0 Flash로 주제 → 장면 분리된 스크립트 생성
"""
import json
import re
import time
from google import genai
from google.genai import types
import config

# 장르별 시스템 프롬프트 — 유튜브 쇼츠
GENRE_SYSTEM = {
    "재테크": (
        "당신은 재테크/금융 유튜브 쇼츠 전문 작가입니다. "
        "시청자가 돈 관련 실용 정보를 얻을 수 있는 내용을 씁니다. "
        "전문 용어보다 쉬운 말을 사용하고, 구체적인 숫자와 사례를 넣습니다."
    ),
    "범죄": (
        "당신은 실제 사건/범죄 유튜브 쇼츠 전문 작가입니다. "
        "긴장감 있고 드라마틱하게 사건을 재구성합니다. "
        "사실 기반으로 이야기를 풀어가며 시청자를 몰입하게 만듭니다."
    ),
    "공포": (
        "당신은 공포/미스터리 유튜브 쇼츠 전문 작가입니다. "
        "으스스한 분위기를 만들고 끝까지 긴장감을 유지합니다. "
        "한국 실제 괴담이나 미스터리 사건을 기반으로 합니다."
    ),
    "교육": (
        "당신은 교육/지식 유튜브 쇼츠 전문 작가입니다. "
        "복잡한 내용을 쉽고 재미있게 설명합니다. "
        "'사실 이걸 알면...' 형식으로 지식 격차를 활용합니다."
    ),
    "자기계발": (
        "당신은 자기계발/동기부여 유튜브 쇼츠 전문 작가입니다. "
        "시청자가 행동하게 만드는 실용적인 내용을 씁니다. "
        "1인칭 경험담과 구체적인 실천법을 포함합니다."
    ),
}

# 장르별 시스템 프롬프트 — 인스타그램 릴스 (후킹 + 짧고 임팩트)
INSTA_GENRE_SYSTEM = {
    "인스타_재테크": (
        "당신은 인스타그램 릴스 전문 재테크 크리에이터입니다. "
        "첫 3초 안에 시청자를 잡는 강렬한 후킹으로 시작합니다. "
        "짧고 임팩트 있는 문장으로 돈이 되는 정보를 전달합니다. "
        "트렌디한 인스타 말투로 쓰세요."
    ),
    "인스타_자기계발": (
        "당신은 인스타그램 릴스 전문 자기계발 크리에이터입니다. "
        "공감을 유발하는 후킹으로 시작해서 바로 실천 가능한 팁을 줍니다. "
        "밀레니얼/Z세대 감성으로 짧고 강렬하게 씁니다."
    ),
    "인스타_라이프": (
        "당신은 인스타그램 릴스 전문 라이프스타일 크리에이터입니다. "
        "일상의 공감 포인트를 후킹으로 잡고 업그레이드 팁을 제시합니다. "
        "친근하고 트렌디한 말투를 사용합니다."
    ),
    "인스타_정보": (
        "당신은 인스타그램 릴스 전문 정보/지식 크리에이터입니다. "
        "'이거 몰랐죠?' 스타일로 시작해서 유용한 정보를 줍니다. "
        "놀라운 사실이나 반전 정보로 공유 욕구를 자극합니다."
    ),
    "인스타_비즈": (
        "당신은 인스타그램 릴스 전문 비즈니스 크리에이터입니다. "
        "창업자/직장인이 공감하는 상황으로 시작합니다. "
        "실전 비즈니스 인사이트를 짧고 강렬하게 전달합니다."
    ),
}

# 통합 장르 맵 (UI에서 key로 조회용)
ALL_GENRE_SYSTEM = {**GENRE_SYSTEM, **INSTA_GENRE_SYSTEM}

MOOD_OPTIONS = ["긴장", "충격", "밝음", "슬픔", "설명", "화남"]
MOTION_OPTIONS = ["zoom_in", "zoom_out", "pan_right", "pan_left", "pan_up", "shake"]

# 릴스 구조 — 장르별 공감 포인트 정의
REELS_EMPATHY = {
    "인스타_재테크": "월급은 그대로인데 물가만 오르는 상황",
    "인스타_자기계발": "열심히 사는데 뭔가 제자리인 느낌",
    "인스타_라이프": "바쁘게 사는데 삶의 질은 안 올라가는 현실",
    "인스타_정보": "알고 보면 손해보고 살았던 것들",
    "인스타_비즈": "열심히 일하는데 성과가 안 나오는 직장인/창업자",
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


def generate_reels_script(topic: str, genre: str, duration: int = 30) -> dict:
    """
    인스타 릴스 전용 스크립트 생성.
    후킹 → 공감 → 가치 → 전환 → CTA 구조 강제.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    system  = INSTA_GENRE_SYSTEM.get(genre, INSTA_GENRE_SYSTEM["인스타_정보"])
    empathy = REELS_EMPATHY.get(genre, "공감 가는 일상 상황")

    # 30초 기준 5장면, 15초는 3장면
    if duration <= 15:
        scenes_spec = [
            ("후킹", 3,  "스크롤을 멈추게 하는 충격적/공감 한 문장. 질문형 또는 반전형."),
            ("가치", 8,  "핵심 정보 2가지를 빠르게 전달."),
            ("CTA", 4,  "'나도'라고 댓글 달면 자료 무료 전송 유도."),
        ]
    else:
        scenes_spec = [
            ("후킹", 3,  "스크롤을 멈추게 하는 충격적/공감 한 문장. 질문형 또는 반전형으로. 예: '이거 모르면 평생 손해입니다' / '왜 나는 열심히 해도 안 될까요?'"),
            ("공감", 5,  f"{empathy}. '저도 그랬어요' 또는 '이런 적 있죠?' 스타일로 시청자가 고개 끄덕이게."),
            ("가치1", 7, "핵심 팁/정보 첫 번째. 구체적 숫자나 사례 포함. 짧고 강렬하게."),
            ("가치2", 7, "핵심 팁/정보 두 번째. 실천 가능한 내용으로."),
            ("CTA", 8,  "결과/변화 한 문장 + '나도'라고 댓글 달면 전체 자료 무료 전송 유도. 저장/팔로우 CTA 포함."),
        ]

    scenes_json = "\n".join([
        f'    {{\n      "id": {i+1},\n      "role": "{role}",\n      "duration": {dur},\n      "narration": "{role} 나레이션",\n      "description": "English visual description",\n      "mood": "mood",\n      "motion": "motion"\n    }}'
        for i, (role, dur, _) in enumerate(scenes_spec)
    ])

    spec_text = "\n".join([
        f"  장면{i+1} [{role}] ({dur}초): {desc}"
        for i, (role, dur, desc) in enumerate(scenes_spec)
    ])

    prompt = f"""
{system}

주제: "{topic}"
총 길이: {duration}초

★ 반드시 아래 구조를 지켜서 작성하세요:
{spec_text}

추가 규칙:
- 나레이션은 반드시 구어체 (문어체, 존댓말 딱딱한 표현 금지)
- 후킹은 반드시 1-2문장, 15자 이내로 임팩트 있게
- "그니까요", "진짜로", "근데 있잖아요" 같은 인스타 감성 말투 사용
- mood: {MOOD_OPTIONS} 중 하나
- motion: {MOTION_OPTIONS} 중 하나
- description은 영어로 (Imagen 프롬프트용)
- CTA에 반드시 "나도" 키워드 포함

JSON 형식으로만 응답 (다른 텍스트 없이):

{{
  "title": "인스타 릴스 제목 (클릭/저장 유도형)",
  "scenes": [
{scenes_json}
  ]
}}
"""

    def _call():
        return client.models.generate_content(
            model=config.MODEL_SCRIPT,
            contents=prompt,
        )

    response = _retry_api_call(_call)
    raw = response.text.strip()
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError(f"JSON 파싱 실패: {raw[:200]}")

    def _fix(s):
        result, in_str, esc = [], False, False
        for ch in s:
            if esc:
                result.append(ch); esc = False
            elif ch == '\\':
                result.append(ch); esc = True
            elif ch == '"':
                result.append(ch); in_str = not in_str
            elif in_str and ch in '\n\r\t':
                result.append({'\\n': '\\n', '\r': '\\r', '\t': '\\t'}.get(ch, ch))
            else:
                result.append(ch)
        return ''.join(result)

    return json.loads(_fix(match.group()))


def generate_script(topic: str, genre: str, duration: int = 60) -> dict:
    """
    주제와 장르로 쇼츠/릴스 스크립트 생성.
    인스타 릴스(인스타_ prefix)는 후킹→공감→가치→CTA 구조 전용 함수로 분기.
    """
    # 인스타 릴스는 전용 구조 함수로
    if genre.startswith("인스타_"):
        return generate_reels_script(topic, genre, duration)

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    system = ALL_GENRE_SYSTEM.get(genre, GENRE_SYSTEM["교육"])
    # 인스타 릴스(15-30초)는 장면 수 적게, 쇼츠(30-60초)는 기존 로직
    if duration <= 15:
        scene_count = 3
    elif duration <= 30:
        scene_count = max(3, duration // 8)
    else:
        scene_count = max(5, duration // 10)

    prompt = f"""
{system}

주제: "{topic}"
총 길이: {duration}초
장면 수: {scene_count}개 (각 장면 약 {duration // scene_count}초)

다음 규칙을 반드시 지켜서 JSON을 작성하세요:

1. 첫 장면은 강력한 후킹 문장으로 시작 (예: "지금 당장 확인 안 하면 후회합니다")
2. 마지막 장면은 처음과 자연스럽게 연결되는 루프 구조
3. 나레이션은 반드시 구어체로 (문어체 금지)
4. 나레이션에 "그런데요", "사실은요", "진짜로요" 같은 표현 자연스럽게 포함
5. mood는 반드시 다음 중 하나: {MOOD_OPTIONS}
6. motion은 반드시 다음 중 하나: {MOTION_OPTIONS}
7. description은 영어로 (이미지 생성 프롬프트에 사용됨)

JSON 형식으로만 응답하세요 (다른 텍스트 없이):

{{
  "title": "유튜브 쇼츠 제목 (클릭 유도형)",
  "scenes": [
    {{
      "id": 1,
      "duration": {duration // scene_count},
      "narration": "한국어 나레이션 텍스트",
      "description": "Visual scene description in English for image generation",
      "mood": "mood_name",
      "motion": "motion_type"
    }}
  ]
}}
"""

    def _call():
        return client.models.generate_content(
            model=config.MODEL_SCRIPT,
            contents=prompt,
        )

    response = _retry_api_call(_call)

    raw = response.text.strip()
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError(f"JSON 파싱 실패: {raw[:200]}")

    # 문자열 내부 제어문자 이스케이프 처리
    def _fix_control_chars(s: str) -> str:
        result = []
        in_string = False
        escape = False
        for ch in s:
            if escape:
                result.append(ch)
                escape = False
            elif ch == '\\':
                result.append(ch)
                escape = True
            elif ch == '"':
                result.append(ch)
                in_string = not in_string
            elif in_string and ch == '\n':
                result.append('\\n')
            elif in_string and ch == '\r':
                result.append('\\r')
            elif in_string and ch == '\t':
                result.append('\\t')
            else:
                result.append(ch)
        return ''.join(result)

    result = json.loads(_fix_control_chars(match.group()))
    return result


def get_full_narration(script: dict) -> str:
    """모든 장면 나레이션을 하나로 합침 (TTS용)"""
    parts = []
    for scene in script["scenes"]:
        parts.append(scene["narration"])
    return " ... ".join(parts)  # 장면 사이에 자연스러운 포즈
