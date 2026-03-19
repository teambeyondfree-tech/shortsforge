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


def _retry_api_call(func, max_retries=4):
    """Gemini API 호출 재시도 — 429는 길게 대기"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            msg = str(e)
            is_429 = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            wait = 60 if is_429 else (2 ** attempt)
            print(f"    [재시도 {attempt+1}/{max_retries}] {'429 한도초과' if is_429 else str(e)[:60]} → {wait}초 대기")
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
    hook_desc = (
        "⚡ 후킹 (절대 규칙): 20자 이내, 단 1문장. "
        "반드시 아래 유형 중 하나:\n"
        "  ① 충격형: '이거 모르면 평생 손해입니다'\n"
        "  ② 질문형: '왜 열심히 할수록 가난해질까요?'\n"
        "  ③ 반전형: '저축이 당신을 가난하게 만듭니다'\n"
        "  ④ 직접호명: '지금 월급 300 이하면 꼭 보세요'\n"
        "  → 시청자가 첫 3초 안에 스크롤을 멈춰야 함"
    )
    if duration <= 15:
        scenes_spec = [
            ("후킹", 3,  hook_desc),
            ("가치", 8,  "핵심 정보 2가지. 구체적 숫자/사례 포함. 짧고 강렬하게."),
            ("CTA", 4,  "변화 한 문장 + '나도' 댓글 유도 + 저장/팔로우 CTA."),
        ]
    else:
        scenes_spec = [
            ("후킹", 3,  hook_desc),
            ("공감", 5,  f"{empathy}. '저도 그랬어요' / '이런 적 있죠?' 스타일. 시청자가 고개 끄덕이게."),
            ("가치1", 7, "핵심 팁 첫 번째. 구체적 숫자/사례 포함. 짧고 강렬하게."),
            ("가치2", 7, "핵심 팁 두 번째. 바로 실천 가능한 내용으로."),
            ("CTA", 8,  "변화/결과 한 문장 + '나도' 댓글 달면 자료 무료 전송 유도 + 저장/팔로우 CTA."),
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
- 나레이션은 실제 말하듯 구어체로 (문어체, 딱딱한 존댓말 금지)
- 후킹은 반드시 1-2문장, 15자 이내로 강렬하게
- "그니까요", "진짜로", "근데 있잖아요", "솔직히 말하면" 같은 인스타 감성 말투 사용
- 짧은 문장을 섞어 리듬감 살리기 (예: "놀랍죠?", "이게 끝이 아니에요.", "진짜예요.")
- 숫자/핵심 정보 앞에는 "무려", "딱", "단" 같은 강조 부사 활용
- TTS로 읽을 때 자연스럽게 들리도록 긴 문장은 짧게 쪼개서 작성
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
    if genre.startswith("인스타_"):
        return generate_reels_script(topic, genre, duration)

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    system = ALL_GENRE_SYSTEM.get(genre, GENRE_SYSTEM["교육"])

    # 장면 수 결정 (첫 장면 항상 3초 후킹)
    if duration <= 20:
        body_scenes = 2
    elif duration <= 35:
        body_scenes = 3
    else:
        body_scenes = max(4, (duration - 3) // 10)

    total_scenes = 1 + body_scenes  # 후킹(3초) + 본편
    body_duration = duration - 3
    per_body = body_duration // body_scenes

    prompt = f"""
{system}

주제: "{topic}"
총 길이: {duration}초
장면 수: {total_scenes}개

━━━ 필수 구조 ━━━
장면1 [후킹] 3초 — 스크롤을 강제로 멈추는 단 1~2문장. 반드시 아래 유형 중 하나:
  ① 충격형:    "이거 모르면 평생 손해입니다."
  ② 질문형:    "왜 열심히 일할수록 가난해질까요?"
  ③ 반전형:    "사실 저축은 당신을 가난하게 만들어요."
  ④ 직접호명:  "지금 월급 300 이하면 꼭 보세요."
  → 나레이션 글자 수: 20자 이내. 짧고 강렬하게.

장면2~{total_scenes-1} [본론] 각 {per_body}초 — 구체적 정보/사례/숫자 전달
장면{total_scenes} [마무리] {per_body}초 — 후킹과 연결되는 반전/결론으로 루프 구조

━━━ 나레이션 규칙 ━━━
- 실제 말하듯 구어체 (문어체/딱딱한 존댓말 금지)
- 짧은 문장으로 리듬감: "놀랍죠?", "맞아요.", "이게 끝이 아니에요."
- 숫자/핵심 정보 앞: "무려", "딱", "단" 같은 강조 부사
- 한 문장이 20자 넘으면 쪼개서 작성 (TTS 호흡 단위)
- "그런데요", "사실은요", "진짜로요" 같은 자연스러운 접속 표현 포함

━━━ 기타 ━━━
- mood: {MOOD_OPTIONS} 중 하나
- motion: {MOTION_OPTIONS} 중 하나
- description: 영어로 (이미지 생성용), 후킹 장면은 dramatic close-up, high contrast 포함

JSON 형식으로만 응답하세요 (다른 텍스트 없이):

{{
  "title": "유튜브 쇼츠 제목 — 클릭/궁금증 유발형",
  "scenes": [
    {{
      "id": 1,
      "role": "후킹",
      "duration": 3,
      "narration": "20자 이내 강렬한 후킹 문장",
      "description": "Dramatic close-up visual in English",
      "mood": "충격",
      "motion": "zoom_in"
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
    # 장면 사이 자연스러운 포즈 — 마침표+공백으로 TTS가 자연스럽게 쉬게 함
    return "  ".join(parts)
