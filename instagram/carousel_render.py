"""
인스타그램 캐러셀 슬라이드 렌더링 v5 — Clean Editorial
- 라이트 모드 베이지/화이트 배경
- 왼쪽 굵은 포인트 컬러 스트라이프
- 에디토리얼 타이포그래피 (좌정렬, 강한 대비)
- 불필요한 장식 요소 제거
"""
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CAROUSEL_W = 1080
CAROUSEL_H = 1350
PAD        = 80

_BASE      = Path(__file__).parent.parent
_FONT_BOLD = _BASE / "assets" / "fonts" / "malgunbd.ttf"
_FONT_NORM = _BASE / "assets" / "fonts" / "malgun.ttf"
_NANUM_BOLD = Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
_NANUM_NORM = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")

# ── 색상 상수 ─────────────────────────────────────────────────────────
DARK  = (14,  14,  28)    # 제목 텍스트
GRAY  = (95,  95, 115)    # 본문 텍스트
LGRAY = (185, 185, 200)   # 점 비활성

# 장르별 배경 색조 (거의 화이트에 가까운 파스텔)
GENRE_BG = {
    "재테크":       (244, 247, 252),
    "자기계발":     (248, 244, 255),
    "교육/지식":    (244, 251, 255),
    "라이프스타일": (255, 244, 249),
    "건강/뷰티":    (244, 255, 249),
    "비즈니스":     (244, 246, 255),
}


# ── 유틸 ──────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [_FONT_BOLD, _NANUM_BOLD] if bold else [_FONT_NORM, _NANUM_NORM]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue
    return ImageFont.load_default()


def _strip_emoji(text: str) -> str:
    return re.sub(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+",
        "", text, flags=re.UNICODE,
    ).strip()


def _hex_rgb(hex_c: str) -> tuple:
    h = hex_c.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _accent(slide: dict) -> tuple:
    return _hex_rgb(slide.get("accent_color", "#2563eb"))


def _accent_for_text(rgb: tuple) -> tuple:
    """배경이 밝을 때 accent가 너무 연하면 어둡게 보정"""
    r, g, b = rgb
    lum = 0.299*r + 0.587*g + 0.114*b
    if lum > 190:   # 너무 밝은 색 → 채도·명도 낮춤
        return (max(0, r-80), max(0, g-80), max(0, b-80))
    return rgb


def _wrap(text: str, font_size: int, max_width: int) -> list:
    chars_per_line = max(6, int(max_width / (font_size * 0.92)))
    words = text.split()
    lines, cur = [], ""
    for word in words:
        cand = f"{cur} {word}".strip()
        if len(cand) <= chars_per_line:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def _dots(draw, cx, cy, total, current, accent):
    """하단 진행 도트"""
    dr, dg = 6, 18
    dw = total*(dr*2) + (total-1)*dg
    x  = cx - dw//2
    for i in range(total):
        col = _accent_for_text(accent) if i == current else LGRAY
        if i == current:
            draw.ellipse([x, cy-dr, x+dr*2, cy+dr], fill=col)
        else:
            draw.ellipse([x+1, cy-dr+1, x+dr*2-1, cy+dr-1], outline=LGRAY, width=2)
        x += dr*2 + dg


# ── 배경 생성 ─────────────────────────────────────────────────────────

def _make_bg(slide: dict, genre: str) -> Image.Image:
    tint = GENRE_BG.get(genre, (246, 247, 252))
    return Image.new("RGB", (CAROUSEL_W, CAROUSEL_H), tint)


# ── 슬라이드 렌더링 ───────────────────────────────────────────────────

def _render_cover(slide: dict, canvas: Image.Image, genre: str) -> Image.Image:
    draw    = ImageDraw.Draw(canvas)
    W, H    = CAROUSEL_W, CAROUSEL_H
    accent  = _accent(slide)
    atext   = _accent_for_text(accent)
    heading = _strip_emoji(slide.get("heading",  ""))
    sub     = _strip_emoji(slide.get("subtitle", "") or "")

    # ── 상단 굵은 accent 바 (20px)
    draw.rectangle([0, 0, W, 20], fill=accent)

    # ── 콘텐츠 블록 전체 높이 계산 → 수직 중앙 정렬
    BADGE_H  = 50    # 장르 뱃지
    BADGE_GAP = 28
    fh       = _get_font(76, bold=True)
    fs       = _get_font(36)
    lines    = _wrap(heading, 76, W - PAD * 2)
    lh       = 92
    title_h  = len(lines) * lh
    line_h   = 12    # 언더라인
    LINE_GAP = 18
    sub_h    = 44 if sub else 0
    total_h  = BADGE_H + BADGE_GAP + title_h + LINE_GAP + line_h + (LINE_GAP + sub_h if sub else 0)

    y = 30 + max(0, (H - 30 - 90 - total_h) // 2)

    # ── 장르 뱃지 (제목 바로 위)
    gf = _get_font(26)
    gw = int(len(genre) * 26 * 0.95) + 36
    draw.rectangle([PAD, y, PAD + gw, y + BADGE_H], fill=accent)
    draw.text((PAD + 18, y + 10), genre, font=gf, fill=(255, 255, 255))
    y += BADGE_H + BADGE_GAP

    # ── 메인 제목
    for line in lines:
        draw.text((PAD, y), line, font=fh, fill=DARK)
        y += lh

    # ── accent 굵은 선
    y += LINE_GAP
    draw.rectangle([PAD, y, PAD + 240, y + line_h], fill=accent)
    y += line_h

    # ── 부제목
    if sub:
        y += LINE_GAP
        draw.text((PAD, y), sub, font=fs, fill=GRAY)

    # ── 하단 accent 바 + 인디케이터
    draw.rectangle([0, H - 16, W, H], fill=accent)
    _dots(draw, W // 2, H - 50, 5, 0, accent)

    return canvas


def _render_content(slide: dict, num: int, total: int,
                    canvas: Image.Image) -> Image.Image:
    draw    = ImageDraw.Draw(canvas)
    W, H    = CAROUSEL_W, CAROUSEL_H
    accent  = _accent(slide)
    atext   = _accent_for_text(accent)
    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")

    # ── 왼쪽 세로 accent 스트라이프 (14px)
    draw.rectangle([0, 0, 14, H], fill=accent)

    # ── 슬라이드 번호 (우상단, 연하게)
    fn = _get_font(26)
    draw.text((W - PAD - 70, 52), f"{num}/{total}", font=fn, fill=LGRAY)

    # ── 배지 번호 파싱
    parts       = heading.split(" ", 1)
    badge_num   = parts[0] if parts and parts[0].isdigit() else str(num - 1)
    badge_title = parts[1] if len(parts) > 1 and parts[0].isdigit() else heading

    # ── 콘텐츠 블록 전체 높이 계산 → 수직 중앙 정렬
    NUM_H    = 126    # 큰 번호 높이
    NUM_GAP  = 20
    fh       = _get_font(58, bold=True)
    fb       = _get_font(40)
    t_lines  = _wrap(badge_title, 58, W - PAD * 2)
    b_lines  = _wrap(body, 40, W - PAD * 2) if body else []
    title_h  = len(t_lines) * 72
    body_h   = len(b_lines) * 57
    div_h    = 3 + 32    # 구분선 + 여백
    total_h  = NUM_H + NUM_GAP + title_h + 24 + div_h + body_h

    # 사용 가능한 영역: 상단(80) ~ 하단 도트(H-90)
    y = 80 + max(0, (H - 90 - 80 - total_h) // 2)

    # ── 큰 번호
    fnum = _get_font(110, bold=True)
    draw.text((PAD, y), badge_num, font=fnum, fill=atext)
    y += NUM_H + NUM_GAP

    # ── 제목
    for line in t_lines:
        draw.text((PAD, y), line, font=fh, fill=DARK)
        y += 72

    # ── 구분선
    y += 16
    draw.rectangle([PAD, y, PAD + 180, y + 3], fill=accent)
    y += div_h

    # ── 본문
    for line in b_lines:
        draw.text((PAD, y), line, font=fb, fill=GRAY)
        y += 57

    # ── 하단 도트
    _dots(draw, W // 2, H - 60, total, num - 1, accent)

    return canvas


def _render_cta(slide: dict, canvas: Image.Image) -> Image.Image:
    draw    = ImageDraw.Draw(canvas)
    W, H    = CAROUSEL_W, CAROUSEL_H
    accent  = _accent(slide)
    atext   = _accent_for_text(accent)
    heading = _strip_emoji(slide.get("heading", "저장하고 나중에 보세요"))
    body    = _strip_emoji(slide.get("body", "") or "")

    # ── 상단 굵은 accent 블록 (높이 30%)
    bh = H * 3 // 10
    draw.rectangle([0, 0, W, bh], fill=accent)

    # ── 블록 안에 흰색 다이아몬드 아이콘
    cx, cy = W // 2, bh // 2
    sz = 55
    draw.polygon([(cx, cy-sz), (cx+sz, cy), (cx, cy+sz), (cx-sz, cy)],
                 fill=(255, 255, 255))

    # ── 제목 (accent 블록 아래, 중앙 정렬)
    fh    = _get_font(66, bold=True)
    lines = _wrap(heading, 66, W - PAD * 2)
    lh    = 82
    y     = bh + 70
    for line in lines:
        tw = int(len(line) * 66 * 0.92)
        x  = max(PAD, (W - tw) // 2)
        draw.text((x, y), line, font=fh, fill=DARK)
        y += lh

    # ── 구분선
    draw.rectangle([PAD * 3, y + 18, W - PAD * 3, y + 21], fill=accent)
    y += 40

    # ── 본문
    if body:
        fb = _get_font(38)
        for line in _wrap(body, 38, W - PAD * 2):
            tw = int(len(line) * 38 * 0.92)
            x  = max(PAD, (W - tw) // 2)
            draw.text((x, y), line, font=fb, fill=GRAY)
            y += 52

    # ── 하단 accent 바
    draw.rectangle([0, H - 16, W, H], fill=accent)

    return canvas


# ── 메인 ──────────────────────────────────────────────────────────────

def render_all_slides(slides: list, job_dir: Path, genre: str = "") -> list:
    total = len(slides)
    paths = []
    for i, slide in enumerate(slides, 1):
        canvas = _make_bg(slide, genre)
        s_type = slide.get("type", "content")

        if s_type == "cover":
            canvas = _render_cover(slide, canvas, genre)
        elif s_type == "cta":
            canvas = _render_cta(slide, canvas)
        else:
            canvas = _render_content(slide, i, total, canvas)

        out = job_dir / f"slide_{i:02d}.png"
        canvas.save(out, "PNG")
        paths.append(out)
    return paths


def pack_zip(slide_paths: list, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in slide_paths:
            zf.write(p, p.name)
