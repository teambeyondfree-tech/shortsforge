"""
인스타그램 캐러셀 슬라이드 렌더링 v9
고성과 SNS 콘텐츠 기반 3가지 템플릿
  - Template A (커버): AI 배경 + 필 배지 + 프리헤드라인 + 스와이프 유도
  - Template B (콘텐츠): 큰 따옴표 장식 + 원형 번호 배지 + 진행 도트
  - Template C (CTA): 심볼 + 굵은 CTA + 팔로우 유도
캔버스: 1080 × 1080 정사각형
폰트: Pretendard (맑은고딕 fallback)
"""
import io
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CANVAS  = 1080
PAD     = int(CANVAS * 0.14)   # 151px
CONTENT = CANVAS - PAD * 2     # 778px

_BASE                 = Path(__file__).parent.parent
_FONT_PRETENDARD_XBOLD = _BASE / "assets" / "fonts" / "Pretendard-ExtraBold.ttf"
_FONT_PRETENDARD_BOLD  = _BASE / "assets" / "fonts" / "Pretendard-Bold.ttf"
_FONT_PRETENDARD_REG   = _BASE / "assets" / "fonts" / "Pretendard-Regular.ttf"
_FONT_BOLD             = _BASE / "assets" / "fonts" / "malgunbd.ttf"
_FONT_NORM             = _BASE / "assets" / "fonts" / "malgun.ttf"
_NANUM_BOLD            = Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
_NANUM_NORM            = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")


# ── 장르별 검증 팔레트 ────────────────────────────────────────────────
GENRE_THEME = {
    "재테크": {
        "grad":      [(18, 18, 38), (20, 30, 58), (12, 48, 90)],
        "solid":     (8, 12, 24),
        "cta":       (12, 48, 90),
        "text":      (255, 255, 255),
        "sub":       (170, 190, 220),
        "accent":    (80, 150, 240),
        "pill_bg":   (80, 150, 240),
        "pill_text": (255, 255, 255),
        "bg_prompt": "dark navy financial district at night, city lights bokeh, cinematic ultra wide",
        "wm_word":   "MONEY",
        "hook_icon": "▶",
    },
    "자기계발": {
        "grad":      [(40, 20, 100), (85, 40, 138)],
        "solid":     (18, 8, 50),
        "cta":       (60, 25, 105),
        "text":      (255, 255, 255),
        "sub":       (190, 165, 232),
        "accent":    (190, 125, 250),
        "pill_bg":   (190, 125, 250),
        "pill_text": (18, 8, 50),
        "bg_prompt": "purple aurora borealis over mountain silhouette, inspirational, cinematic",
        "wm_word":   "GROW",
        "hook_icon": "★",
    },
    "교육/지식": {
        "grad":      [(12, 12, 12), (28, 28, 28)],
        "solid":     (10, 10, 10),
        "cta":       (18, 18, 18),
        "text":      (255, 255, 255),
        "sub":       (165, 165, 165),
        "accent":    (210, 210, 210),
        "pill_bg":   (210, 210, 210),
        "pill_text": (10, 10, 10),
        "bg_prompt": "minimal dark library with dramatic single light beam, cinematic moody",
        "wm_word":   "KNOW",
        "hook_icon": "◆",
    },
    "라이프스타일": {
        "grad":      [(25, 48, 80), (62, 115, 148)],
        "solid":     (12, 25, 42),
        "cta":       (25, 48, 80),
        "text":      (240, 250, 235),
        "sub":       (165, 205, 215),
        "accent":    (120, 208, 248),
        "pill_bg":   (120, 208, 248),
        "pill_text": (12, 25, 42),
        "bg_prompt": "cozy lifestyle morning coffee bokeh, warm golden hour, minimal aesthetic",
        "wm_word":   "LIFE",
        "hook_icon": "●",
    },
    "건강/뷰티": {
        "grad":      [(6, 34, 18), (4, 70, 42)],
        "solid":     (5, 18, 10),
        "cta":       (4, 70, 42),
        "text":      (255, 255, 255),
        "sub":       (165, 215, 190),
        "accent":    (100, 225, 150),
        "pill_bg":   (100, 225, 150),
        "pill_text": (5, 18, 10),
        "bg_prompt": "fresh green nature wellness, soft bokeh, dewy leaves, healthy lifestyle",
        "wm_word":   "GLOW",
        "hook_icon": "◎",
    },
    "비즈니스": {
        "grad":      [(20, 20, 20), (45, 45, 45)],
        "solid":     (12, 12, 12),
        "cta":       (22, 22, 22),
        "text":      (255, 255, 255),
        "sub":       (168, 168, 168),
        "accent":    (250, 100, 48),
        "pill_bg":   (250, 100, 48),
        "pill_text": (255, 255, 255),
        "bg_prompt": "modern minimalist dark office interior, dramatic side lighting, professional cinematic",
        "wm_word":   "BIZ",
        "hook_icon": "▲",
    },
}
_DEFAULT = GENRE_THEME["교육/지식"]


# ── 폰트 ──────────────────────────────────────────────────────────────

def _get_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    if weight == "xbold":
        candidates = [_FONT_PRETENDARD_XBOLD, _FONT_BOLD, _NANUM_BOLD]
    elif weight == "bold":
        candidates = [_FONT_PRETENDARD_BOLD, _FONT_BOLD, _NANUM_BOLD]
    else:
        candidates = [_FONT_PRETENDARD_REG, _FONT_NORM, _NANUM_NORM]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── 텍스트 측정 & 렌더링 ───────────────────────────────────────────────

def _measure(text: str, font) -> tuple:
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bb = dummy.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def _wrap(text: str, font, max_w: int, max_lines: int = 99) -> list:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        w_px, _ = _measure(cand, font)
        if w_px <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
                if len(lines) >= max_lines:
                    return lines
            cur = w
    if cur:
        lines.append(cur)
    return (lines or [text])[:max_lines]


def _cx(text: str, font) -> int:
    w, _ = _measure(text, font)
    return (CANVAS - w) // 2


def _draw_c(draw, y: int, text: str, font, color):
    draw.text((_cx(text, font), y), text, font=font, fill=color)


def _strip_emoji(text: str) -> str:
    return re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        r"\U00002702-\U000027B0\U0001F900-\U0001F9FF"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+",
        "", text, flags=re.UNICODE,
    ).strip()


# ── 배경 생성 ─────────────────────────────────────────────────────────

def _diag_gradient(colors: list) -> Image.Image:
    W = H = CANVAS
    x = np.arange(W, dtype=np.float32).reshape(1, W)
    y = np.arange(H, dtype=np.float32).reshape(H, 1)
    t = (x + y) / (W + H - 2)
    c = [np.array(col, dtype=np.float32) for col in colors]
    t3 = t[:, :, np.newaxis]
    if len(c) == 2:
        arr = c[0] * (1 - t3) + c[1] * t3
    else:
        half = t < 0.5
        s1 = np.clip(t * 2, 0, 1)[:, :, np.newaxis]
        s2 = np.clip(t * 2 - 1, 0, 1)[:, :, np.newaxis]
        arr = np.where(half[:, :, np.newaxis],
                       c[0] * (1 - s1) + c[1] * s1,
                       c[1] * (1 - s2) + c[2] * s2)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _fetch_ai_bg(heading: str, genre_prompt: str, grad: list) -> Image.Image:
    """슬라이드 제목 기반으로 배경 이미지 생성"""
    try:
        import config
        from google import genai
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        # 제목 내용을 프롬프트에 반영
        prompt = (
            f"{heading} concept, {genre_prompt}, "
            "square 1:1, cinematic photography, dark moody atmosphere, "
            "no text, no letters, no people, blurred bokeh background, ultra quality"
        )
        resp = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=prompt,
            config={"number_of_images": 1, "aspect_ratio": "1:1"},
        )
        img_bytes = resp.generated_images[0].image.image_bytes
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((CANVAS, CANVAS))
        # 블러 처리 — 텍스트 가독성 확보
        from PIL import ImageFilter
        img = img.filter(ImageFilter.GaussianBlur(radius=6))
        return img
    except Exception as e:
        print(f"  [AI 배경 fallback] {e}")
        return _diag_gradient(grad)


def _dark_overlay(bg: Image.Image, opacity: int = 195) -> Image.Image:
    """단순 다크 오버레이"""
    ov = Image.new("RGBA", bg.size, (0, 0, 0, opacity))
    return Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")


def _gradient_overlay(bg: Image.Image, solid_color: tuple, opacity: int = 180) -> Image.Image:
    """
    좌측 절반은 단색 오버레이(텍스트 영역), 우측은 점점 투명해지는 그라디언트 오버레이.
    텍스트는 왼쪽에, 이미지는 오른쪽에서 보이는 효과.
    """
    W, H = bg.size
    arr = np.zeros((H, W, 4), dtype=np.uint8)
    r, g, b = solid_color
    # x축 기준: 0 → opacity, W//2 이후 → opacity/2 로 선형 감소
    for xi in range(W):
        if xi < W // 2:
            a = opacity
        else:
            ratio = (xi - W // 2) / (W // 2)
            a = int(opacity * (1 - ratio * 0.45))
        arr[:, xi, 0] = r
        arr[:, xi, 1] = g
        arr[:, xi, 2] = b
        arr[:, xi, 3] = a
    ov = Image.fromarray(arr, "RGBA")
    return Image.alpha_composite(bg.convert("RGBA"), ov).convert("RGB")


# ── 공통 UI 컴포넌트 ──────────────────────────────────────────────────

def _draw_pill(draw, cx: int, cy: int, text: str, font,
               bg_color: tuple, text_color: tuple, pad_x: int = 28, pad_y: int = 12):
    """중앙 기준 pill 배지"""
    tw, th = _measure(text, font)
    w = tw + pad_x * 2
    h = th + pad_y * 2
    x0 = cx - w // 2
    y0 = cy - h // 2
    try:
        draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=h // 2, fill=bg_color)
    except AttributeError:
        draw.rectangle([x0, y0, x0 + w, y0 + h], fill=bg_color)
    draw.text((x0 + pad_x, y0 + pad_y), text, font=font, fill=text_color)


def _draw_accent_line(draw, y: int, width: int, color: tuple, thickness: int = 3):
    """중앙 정렬 수평 강조선"""
    x0 = (CANVAS - width) // 2
    draw.rectangle([x0, y, x0 + width, y + thickness], fill=color)


def _draw_progress_dots(draw, current: int, total: int, y: int,
                        dot_r: int, gap: int, active_col: tuple, inactive_col: tuple):
    """하단 진행 도트"""
    count = total
    total_w = count * dot_r * 2 + (count - 1) * gap
    x = (CANVAS - total_w) // 2
    for i in range(count):
        col = active_col if i == current - 1 else inactive_col
        cx = x + i * (dot_r * 2 + gap) + dot_r
        draw.ellipse([cx - dot_r, y - dot_r, cx + dot_r, y + dot_r], fill=col)


def _draw_swipe_arrow(draw, y: int, text_color: tuple, accent: tuple, font):
    """하단 스와이프 유도 화살표"""
    label = "계속 보기"
    lw, lh = _measure(label, font)
    # 화살표 모양 (삼각형) 그리기
    arrow_w, arrow_h = 18, 14
    total_w = lw + 14 + arrow_w
    sx = (CANVAS - total_w) // 2
    ty = y + (arrow_h - lh) // 2

    draw.text((sx, ty), label, font=font, fill=text_color)
    ax = sx + lw + 14
    ay = y
    # 오른쪽 방향 삼각형
    draw.polygon([
        (ax, ay),
        (ax, ay + arrow_h),
        (ax + arrow_w, ay + arrow_h // 2),
    ], fill=accent)


def _draw_big_quote(canvas: Image.Image, color: tuple, opacity: int = 22):
    """배경에 큰 따옴표 장식 (좌상단, 반투명)"""
    draw = ImageDraw.Draw(canvas, "RGBA")
    font = _get_font(320, "xbold")
    r, g, b = color
    draw.text((PAD - 20, PAD - 60), "\u201c", font=font, fill=(r, g, b, opacity))


def _draw_wm(canvas: Image.Image, word: str, color: tuple, opacity: int = 18):
    """반투명 워터마크 타이포"""
    draw = ImageDraw.Draw(canvas, "RGBA")
    font = _get_font(260, "xbold")
    r, g, b = color
    w, _ = _measure(word, font)
    draw.text(((CANVAS - w) // 2, (CANVAS - 260) // 2 - 40),
              word, font=font, fill=(r, g, b, opacity))


# ── Template A: 임팩트형 커버 ─────────────────────────────────────────

def _render_cover(slide: dict, genre: str, use_ai_bg: bool = True) -> Image.Image:
    th      = GENRE_THEME.get(genre, _DEFAULT)
    heading = _strip_emoji(slide.get("heading", ""))
    sub     = _strip_emoji(slide.get("subtitle", "") or "")

    # 배경 — 슬라이드 제목 기반으로 생성
    bg = _fetch_ai_bg(heading, th["bg_prompt"], th["grad"]) if use_ai_bg else _diag_gradient(th["grad"])
    # 좌측 그라디언트 오버레이: 텍스트 영역(좌)은 어둡게, 이미지(우)는 살짝 보이게
    canvas = _gradient_overlay(bg, (0, 0, 0), opacity=205)

    draw = ImageDraw.Draw(canvas)

    f_main = _get_font(90, "xbold")
    f_sub  = _get_font(30, "regular")
    f_tag  = _get_font(18, "bold")

    LH_MAIN = int(90 * 1.16)   # 104px

    mlines = _wrap(heading, f_main, CONTENT, max_lines=2)
    slines = _wrap(sub, f_sub, CONTENT, max_lines=1) if sub else []

    # 좌측 accent 세로선 + 블록 세로 중앙 정렬
    # 전체 블록: 헤드라인 + 서브
    main_h = len(mlines) * LH_MAIN
    sub_h  = (20 + int(30 * 1.2)) if slines else 0
    blk_h  = main_h + sub_h
    y      = (CANVAS - blk_h) // 2
    x      = PAD   # 좌측 정렬 기준

    # 좌측 accent 세로선 (헤드라인 높이만큼)
    bar_x = x - 16
    draw.rectangle([bar_x, y, bar_x + 4, y + main_h], fill=th["accent"])

    # 메인 헤드라인 (좌측 정렬)
    for line in mlines:
        draw.text((x, y), line, font=f_main, fill=th["text"])
        y += LH_MAIN

    # 서브타이틀
    if slines:
        y += 20
        draw.text((x, y), slines[0], font=f_sub, fill=th["sub"])

    # 장르 태그 (좌하단)
    draw.text((PAD, CANVAS - PAD + 16), genre, font=f_tag, fill=th["accent"])

    return canvas


# ── Template B: 정보형 콘텐츠 ─────────────────────────────────────────

def _render_content(slide: dict, num: int, total: int, genre: str, use_ai_bg: bool = True) -> Image.Image:
    th      = GENRE_THEME.get(genre, _DEFAULT)
    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")
    # 슬라이드 내용 기반 배경 생성
    content_prompt = f"{heading} {body}"
    bg     = _fetch_ai_bg(content_prompt, th["bg_prompt"], th["grad"]) if use_ai_bg else _diag_gradient(th["grad"])
    canvas = _dark_overlay(bg, opacity=210)
    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")

    # 번호 파싱 (heading은 위에서 이미 선언됨)
    parts   = heading.split(" ", 1)
    num_str = parts[0] if parts and parts[0].isdigit() else str(num - 1)
    title   = parts[1] if len(parts) > 1 and parts[0].isdigit() else heading

    # 문장 분리 (body는 위에서 이미 선언됨)
    sentences = re.split(r"(?<=[.?!。])\s*", body.strip()) if body else []
    highlight = sentences[0] if sentences else ""
    rest_body = " ".join(sentences[1:]) if len(sentences) > 1 else ""

    # 폰트
    f_h  = _get_font(58, "xbold")
    f_hl = _get_font(38, "regular")
    f_b  = _get_font(33, "regular")
    f_sm = _get_font(24, "regular")

    LH_H  = int(58 * 1.28)
    LH_HL = int(38 * 1.3)
    LH_B  = int(33 * 1.3)

    hlines  = _wrap(title,     f_h,  CONTENT, max_lines=2)
    hllines = _wrap(highlight, f_hl, CONTENT, max_lines=2) if highlight else []
    blines  = _wrap(rest_body, f_b,  CONTENT, max_lines=2) if rest_body else []

    # 원형 번호 배지 높이
    badge_r = 36
    badge_h = badge_r * 2

    blk = (badge_h + 24
           + len(hlines) * LH_H
           + (28 + len(hllines) * LH_HL if hllines else 0)
           + (16 + len(blines)  * LH_B  if blines  else 0))
    y = (CANVAS - blk) // 2

    draw = ImageDraw.Draw(canvas)
    x = PAD  # 좌측 정렬 기준

    # 슬라이드 번호 (우상단)
    draw.text((CANVAS - PAD - 70, PAD // 2 + 4),
              f"{num} / {total}", font=f_sm, fill=th["sub"])

    # 원형 번호 배지 (좌측 정렬)
    bcx = x + badge_r
    bcy = y + badge_r
    draw.ellipse([bcx - badge_r, bcy - badge_r, bcx + badge_r, bcy + badge_r],
                 fill=th["accent"])
    f_badge = _get_font(30, "xbold")
    bw, bh  = _measure(num_str, f_badge)
    draw.text((bcx - bw // 2, bcy - bh // 2), num_str,
              font=f_badge, fill=th["solid"])
    y += badge_h + 24

    # 제목 (좌측 정렬)
    for line in hlines:
        draw.text((x, y), line, font=f_h, fill=th["text"])
        y += LH_H

    # 하이라이트 (좌측 강조선 + accent 색)
    if hllines:
        y += 28
        bar_h = len(hllines) * LH_HL
        draw.rectangle([x, y, x + 4, y + bar_h], fill=th["accent"])
        for line in hllines:
            draw.text((x + 20, y), line, font=f_hl, fill=th["accent"])
            y += LH_HL

    # 본문 (좌측 정렬)
    if blines:
        y += 16
        for line in blines:
            draw.text((x, y), line, font=f_b, fill=th["sub"])
            y += LH_B

    # 하단 진행 도트 (중앙)
    dot_r = 5
    dot_gap = 10
    dot_y = CANVAS - PAD // 2
    _draw_progress_dots(draw, max(1, num - 1), max(1, total - 2),
                        dot_y, dot_r, dot_gap,
                        th["accent"], (*th["sub"][:3],) if len(th["sub"]) >= 3 else th["sub"])

    return canvas


# ── Template C: CTA형 ─────────────────────────────────────────────────

def _render_cta(slide: dict, genre: str, use_ai_bg: bool = True) -> Image.Image:
    th      = GENRE_THEME.get(genre, _DEFAULT)
    heading = _strip_emoji(slide.get("heading", "저장하고 나중에 보세요"))
    body    = _strip_emoji(slide.get("body", "") or "")
    bg      = _fetch_ai_bg(f"{heading} {body}", th["bg_prompt"], th["grad"]) if use_ai_bg else _diag_gradient(th["grad"])
    canvas  = _dark_overlay(bg, opacity=215)

    draw = ImageDraw.Draw(canvas)

    f_main = _get_font(64, "xbold")
    f_sub  = _get_font(28, "regular")
    f_pill = _get_font(24, "bold")

    LH_MAIN = int(64 * 1.2)

    mlines = _wrap(heading, f_main, CONTENT, max_lines=2)
    slines = _wrap(body,    f_sub,  CONTENT, max_lines=1) if body else []

    # 블록 높이: 상단 라인 + 헤드라인 + 구분 + 서브 + 필 버튼
    line_h   = 3 + 36
    main_h   = len(mlines) * LH_MAIN
    sub_h    = (24 + int(28 * 1.3) if slines else 0)
    pill_h   = 44 + 52
    blk_h    = line_h + main_h + sub_h + pill_h
    y        = (CANVAS - blk_h) // 2

    # 1. 상단 accent 라인 (56px, 심볼 대신)
    _draw_accent_line(draw, y, 56, th["accent"], thickness=3)
    y += line_h

    # 2. 메인 CTA 헤드라인
    for line in mlines:
        _draw_c(draw, y, line, f_main, th["text"])
        y += LH_MAIN

    # 3. 서브텍스트
    if slines:
        y += 24
        _draw_c(draw, y, slines[0], f_sub, th["sub"])
        y += int(28 * 1.3)

    # 4. 팔로우 pill 버튼
    y += 44
    _draw_pill(draw, CANVAS // 2, y + 26,
               "팔로우하고 매일 받아보기", f_pill,
               th["accent"], th["solid"], pad_x=36, pad_y=16)

    return canvas


# ── 메인 ──────────────────────────────────────────────────────────────

def render_all_slides(
    slides: list,
    job_dir: Path,
    genre: str = "",
    use_ai_bg: bool = True,
) -> list:
    total = len(slides)
    paths = []
    for i, slide in enumerate(slides, 1):
        s_type = slide.get("type", "content")
        if s_type == "cover":
            canvas = _render_cover(slide, genre, use_ai_bg=use_ai_bg)
        elif s_type == "cta":
            canvas = _render_cta(slide, genre, use_ai_bg=use_ai_bg)
        else:
            canvas = _render_content(slide, i, total, genre, use_ai_bg=use_ai_bg)

        out = job_dir / f"slide_{i:02d}.png"
        canvas.save(out, "PNG")
        paths.append(out)
    return paths


def pack_zip(slide_paths: list, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in slide_paths:
            zf.write(p, p.name)
