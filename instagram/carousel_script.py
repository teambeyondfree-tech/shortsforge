"""
인스타그램 캐러셀 스크립트 생성
Gemini로 후킹 문구 + 슬라이드별 콘텐츠 생성
"""
import json
import re
import time
from google import genai
import config


CAROUSEL_GENRES = {
    "재테크": (
        "당신은 재테크/금융 인스타그램 캐러셀 전문 크리에이터입니다. "
        "팔로워가 저장하고 싶어지는 실용적인 돈 정보를 제공합니다. "
        "구체적인 숫자와 사례로 신뢰감을 주세요."
    ),
    "자기계발": (
        "당신은 자기계발/동기부여 인스타그램 캐러셀 전문 크리에이터입니다. "
        "팔로워가 당장 실천하고 싶어지는 내용을 씁니다. "
        "짧고 임팩트 있는 문장으로 행동을 유도하세요."
    ),
    "교육/지식": (
        "당신은 교육/지식 인스타그램 캐러셀 전문 크리에이터입니다. "
        "복잡한 정보를 단순하게 정리해서 팔로워가 배운 느낌이 들게 합니다. "
        "'사실 이거 몰랐죠?' 스타일로 지식 격차를 자극하세요."
    ),
    "라이프스타일": (
        "당신은 라이프스타일 인스타그램 캐러셀 전문 크리에이터입니다. "
        "팔로워의 일상을 업그레이드할 수 있는 팁을 제공합니다. "
        "공감 가는 상황에서 시작해서 해결책을 제시하세요."
    ),
    "건강/뷰티": (
        "당신은 건강/뷰티 인스타그램 캐러셀 전문 크리에이터입니다. "
        "과학적 근거가 있는 건강/뷰티 정보를 제공합니다. "
        "팔로워가 바로 실천할 수 있는 구체적인 방법을 포함하세요."
    ),
    "비즈니스": (
        "당신은 비즈니스/마케팅 인스타그램 캐러셀 전문 크리에이터입니다. "
        "창업자/직장인이 저장해두고 싶은 비즈니스 인사이트를 제공합니다. "
        "성공 사례나 데이터로 신뢰감을 형성하세요."
    ),
}

SLIDE_COLOR_PALETTES = {
    "재테크":    [("#0d1b2a", "#1b4332"), ("#1a1a2e", "#0f3460"), ("#13293d", "#006494")],
    "자기계발":  [("#1a0533", "#6a0572"), ("#0d0221", "#410099"), ("#2d1b69", "#11998e")],
    "교육/지식": [("#0a192f", "#172a45"), ("#03001c", "#301551"), ("#1b262c", "#0a3d62")],
    "라이프스타일": [("#1a1a2e", "#e94560"), ("#2c003e", "#f7971e"), ("#0f0c29", "#302b63")],
    "건강/뷰티": [("#134e5e", "#71b280"), ("#0f2027", "#203a43"), ("#1d4350", "#a43931")],
    "비즈니스":  [("#1a1a2e", "#16213e"), ("#0d0d0d", "#434343"), ("#141e30", "#243b55")],
}


def _retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def generate_carousel_script(topic: str, genre: str, slide_count: int = 7) -> dict:
    """
    주제 + 장르로 인스타그램 캐러셀 스크립트 생성.

    반환:
    {
        "title": "캐러셀 제목",
        "hashtags": ["#태그1", ...],
        "caption": "인스타 캡션 텍스트",
        "slides": [
            {
                "id": 1,
                "type": "cover|content|cta",
                "heading": "슬라이드 제목",
                "subtitle": "부제목 (cover만)",
                "body": "본문 내용",
                "accent_color": "#ffcc00"
            },
            ...
        ]
    }
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    role = CAROUSEL_GENRES.get(genre, CAROUSEL_GENRES["교육/지식"])
    content_count = slide_count - 2

    prompt = f"""
{role}

주제: "{topic}"
총 슬라이드: {slide_count}개 (표지 1개 + 본문 {content_count}개 + CTA 1개)

규칙:
1. 표지(cover): "이거 모르면 손해", "저장 필수", "아직도 모르세요?" 스타일의 강력한 후킹 제목
2. 본문(content): 각 슬라이드에 핵심 정보 1가지, 번호 포함 (예: "01 타이틀")
3. CTA: "저장하고 나중에 확인하세요", "팔로우하면 매일 이런 정보를" 스타일
4. 모든 텍스트는 짧고 임팩트 있게 (슬라이드당 heading 1줄, body 2-3줄 이내)
5. heading에 번호 포함 (본문만): "01", "02" 등
6. accent_color: 슬라이드 강조 색상 (hex, 밝은 색 사용)
7. hashtags: 인기 한국 인스타 해시태그 10개
8. caption: 인스타그램 게시글 캡션 (이모지 포함, 3-4줄)

JSON 형식으로만 응답:

{{
  "title": "캐러셀 전체 주제 제목",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5", "#태그6", "#태그7", "#태그8", "#태그9", "#태그10"],
  "caption": "인스타그램 캡션 텍스트\n(줄바꿈 포함)",
  "slides": [
    {{
      "id": 1,
      "type": "cover",
      "heading": "강렬한 후킹 제목",
      "subtitle": "짧은 부제목",
      "body": null,
      "accent_color": "#ffcc00"
    }},
    {{
      "id": 2,
      "type": "content",
      "heading": "01 팁 제목",
      "subtitle": null,
      "body": "핵심 내용 2-3줄로 짧게",
      "accent_color": "#ff6b6b"
    }},
    {{
      "id": {slide_count},
      "type": "cta",
      "heading": "저장하고 나중에 보세요",
      "subtitle": null,
      "body": "팔로우하면 이런 정보를 매일 받아볼 수 있어요",
      "accent_color": "#ffcc00"
    }}
  ]
}}
"""

    def _call():
        return client.models.generate_content(
            model=config.MODEL_SCRIPT,
            contents=prompt,
        )

    response = _retry(_call)
    raw = response.text.strip()
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError(f"JSON 파싱 실패: {raw[:300]}")

    json_str = match.group()
    # 문자열 값 내부의 실제 줄바꿈·탭 등 제어문자를 이스케이프로 변환
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

    data = json.loads(_fix_control_chars(json_str))

    # 팔레트 주입
    palettes = SLIDE_COLOR_PALETTES.get(genre, SLIDE_COLOR_PALETTES["교육/지식"])
    for i, slide in enumerate(data.get("slides", [])):
        palette = palettes[i % len(palettes)]
        slide["bg_top"] = palette[0]
        slide["bg_bottom"] = palette[1]

    return data
