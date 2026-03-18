"""
인스타그램 캐러셀 슬라이드 렌더링 v6
- 커버: 좌우 분할 패널 (컬러 패널 + 타이틀 영역)
- 콘텐츠: 거대 워터마크 숫자 배경
- 장르별 검증된 고정 컬러 팔레트
"""
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CAROUSEL_W = 1080
CAROUSEL_H = 1350

_BASE       = Path(__file__).parent.parent
_FONT_BOLD  = _BASE / "assets" / "fonts" / "malgunbd.ttf"
_FONT_NORM  = _BASE / "assets" / "fonts" / "malgun.ttf"
_NANUM_BOLD = Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
_NANUM_NORM = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")

# ── 장르별 디자인 시스템 ──────────────────────────────────────────────
# (배경색, 패널 진한색, 패널 연한색, 텍스트 accent)
GENRE_THEME = {
    "재테크": {
        "bg":    (242, 246, 253),
        "panel": (23,  58, 153),   # deep blue
        "panel2":(37,  99, 235),   # medium blue (gradient용)
        "accent":(37,  99, 235),
    },
    "자기계발": {
        "bg":    (247, 242, 255),
        "panel": (91,  33, 182),   # deep purple
        "panel2":(124, 58, 237),
        "accent":(124, 58, 237),
    },
    "교육/지식": {
        "bg":    (242, 250, 255),
        "panel": (7,   89, 133),   # deep sky
        "panel2":(2,  132, 199),
        "accent":(2,  132, 199),
    },
    "라이프스타일": {
        "bg":    (255, 242, 249),
        "panel": (157, 23,  77),   # deep rose
        "panel2":(219, 39, 119),
        "accent":(219, 39, 119),
    },
    "건강/뷰티": {
        "bg":    (242, 255, 248),
        "panel": (4,  120,  87),   # deep green
        "panel2":(5,  150, 105),
        "accent":(5,  150, 105),
    },
    "비즈니스": {
        "bg":    (242, 244, 253),
        "panel": (30,  27, 100),   # deep indigo
        "panel2":(67,  56, 202),
        "accent":(67,  56, 202),
    },
}
_DEFAULT_THEME = GENRE_THEME["교육/지식"]

DARK  = (16,  16,  32)
GRAY  = (100, 100, 118)
LGRAY = (190, 190, 205)
WHITE = (255, 255, 255)


# ── 유틸 ──────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [_FONT_BOLD, _NANUM_BOLD] if bold else [_FONT_NORM, _NANUM_NORM]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    return ImageFont.load_default()


def _strip_emoji(text: str) -> str:
    return re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        r"\U00002702-\U000027B0\U0001F900-\U0001F9FF"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+",
        "", text, flags=re.UNICODE,
    ).strip()


def _wrap(text: str, font_size: int, max_width: int) -> list:
    cpp = max(6, int(max_width / (font_size * 0.92)))
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) <= cpp:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def _center_x(text: str, font_size: int, area_x: int, area_w: int) -> int:
    est = len(text) * font_size * 0.92
    return area_x + max(0, int((area_w - est) / 2))


def _dots(draw, cx, cy, total, current, accent):
    dr, dg = 6, 18
    dw = total*(dr*2) + (total-1)*dg
    x  = cx - dw//2
    for i in range(total):
        if i == current:
            draw.ellipse([x, cy-dr, x+dr*2, cy+dr], fill=accent)
        else:
            draw.ellipse([x+1, cy-dr+1, x+dr*2-1, cy+dr-1],
                         outline=LGRAY, width=2)
        x += dr*2 + dg


def _blend(c1, c2, t):
    """두 RGB 색을 t(0~1) 비율로 선형 보간"""
    return tuple(int(a*(1-t) + b*t) for a, b in zip(c1, c2))


def _panel_gradient(draw, x0, y0, x1, y1, c_top, c_bot, steps=40):
    """수직 그라디언트 사각형"""
    h = y1 - y0
    seg = max(1, h // steps)
    for i in range(steps):
        t  = i / (steps - 1)
        cy = y0 + i * seg
        ey = min(y0 + (i+1)*seg, y1)
        draw.rectangle([x0, cy, x1, ey], fill=_blend(c_top, c_bot, t))


# ── 배경 ──────────────────────────────────────────────────────────────

def _make_bg(slide: dict, genre: str) -> Image.Image:
    theme = GENRE_THEME.get(genre, _DEFAULT_THEME)
    return Image.new("RGB", (CAROUSEL_W, CAROUSEL_H), theme["bg"])


# ── 커버 슬라이드 ─────────────────────────────────────────────────────

def _render_cover(slide: dict, canvas: Image.Image, genre: str) -> Image.Image:
    theme   = GENRE_THEME.get(genre, _DEFAULT_THEME)
    W, H    = CAROUSEL_W, CAROUSEL_H
    PANEL_W = 380          # 왼쪽 컬러 패널 너비
    PAD_L   = PANEL_W + 44 # 오른쪽 영역 시작 x
    PAD_R   = 56           # 오른쪽 여백
    TEXT_W  = W - PAD_L - PAD_R

    heading = _strip_emoji(slide.get("heading",  ""))
    sub     = _strip_emoji(slide.get("subtitle", "") or "")

    draw = ImageDraw.Draw(canvas)

    # ── 왼쪽 패널 (그라디언트)
    _panel_gradient(draw, 0, 0, PANEL_W, H,
                    theme["panel"], theme["panel2"])

    # 패널 안 — 장르 라벨 (하단)
    gf  = _get_font(30, bold=True)
    glw = int(len(genre) * 30 * 0.92)
    gx  = (PANEL_W - glw) // 2
    draw.text((gx, H - 90), genre, font=gf, fill=(*WHITE, 220))

    # 패널 안 — 얇은 가로선 3개 (중앙, 장식)
    for k, (bw, by) in enumerate([(200, H//2-60), (140, H//2), (240, H//2+60)]):
        bx = (PANEL_W - bw) // 2
        draw.rectangle([bx, by, bx+bw, by+5],
                       fill=(255, 255, 255))

    # 패널 안 — 작은 원형 아이콘 (위쪽)
    cx, cy, cr = PANEL_W//2, H//4, 54
    draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr],
                 outline=WHITE, width=4)
    draw.ellipse([cx-cr+14, cy-cr+14, cx+cr-14, cy+cr-14],
                 outline=(*WHITE, 140), width=2)

    # ── 오른쪽 패널 — 제목 블록 수직 중앙 정렬
    fh     = _get_font(66, bold=True)
    lines  = _wrap(heading, 66, TEXT_W)
    lh     = 82
    sub_h  = 50 if sub else 0
    blk_h  = len(lines)*lh + 22 + sub_h
    y      = (H - blk_h) // 2

    for line in lines:
        draw.text((PAD_L, y), line, font=fh, fill=DARK)
        y += lh

    # 제목 하단 accent 선
    draw.rectangle([PAD_L, y+14, PAD_L+200, y+22],
                   fill=theme["accent"])
    y += 22

    if sub:
        y += 16
        fs = _get_font(34)
        draw.text((PAD_L, y), sub, font=fs, fill=GRAY)

    # 상단/하단 accent 가는 바
    draw.rectangle([PANEL_W, 0, W, 6], fill=theme["accent"])
    draw.rectangle([PANEL_W, H-6, W, H], fill=theme["accent"])

    # 도트
    _dots(draw, PAD_L + TEXT_W//2, H-40, 5, 0, theme["accent"])

    return canvas


# ── 콘텐츠 슬라이드 ───────────────────────────────────────────────────

def _render_content(slide: dict, num: int, total: int,
                    canvas: Image.Image, genre: str) -> Image.Image:
    theme   = GENRE_THEME.get(genre, _DEFAULT_THEME)
    W, H    = CAROUSEL_W, CAROUSEL_H
    PAD     = 80
    accent  = theme["accent"]
    bg_rgb  = theme["bg"]
    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")

    draw = ImageDraw.Draw(canvas)

    # ── 배경 워터마크 숫자 (거대, 연한 accent)
    parts     = heading.split(" ", 1)
    badge_num = parts[0] if parts and parts[0].isdigit() else str(num - 1)
    title_txt = parts[1] if len(parts) > 1 and parts[0].isdigit() else heading

    fwm   = _get_font(500, bold=True)
    ghost = _blend(accent, bg_rgb, 0.82)   # accent를 배경색과 82% 혼합 → 연하게
    # 워터마크: 오른쪽 아래 영역에 크게
    wm_x = W - int(len(badge_num) * 500 * 0.55) - 20
    wm_y = H // 2 - 60
    draw.text((wm_x, wm_y), badge_num, font=fwm, fill=ghost)

    # ── 왼쪽 세로 accent 스트라이프
    draw.rectangle([0, 0, 12, H], fill=accent)

    # ── 슬라이드 번호 (우상단)
    draw.text((W-PAD-70, 50), f"{num}/{total}",
              font=_get_font(26), fill=LGRAY)

    # ── 콘텐츠 블록 수직 중앙 정렬
    fnum   = _get_font(100, bold=True)
    fh     = _get_font(58,  bold=True)
    fb     = _get_font(42)
    tlines = _wrap(title_txt, 58, W - PAD*2)
    blines = _wrap(body,      42, W - PAD*2) if body else []

    NUM_H  = 108
    blk_h  = NUM_H + 14 + len(tlines)*72 + 22 + 4 + 24 + len(blines)*60
    y      = 80 + max(0, (H - 90 - 80 - blk_h) // 2)

    # 큰 번호 (foreground, 선명하게)
    draw.text((PAD, y), badge_num, font=fnum, fill=accent)
    y += NUM_H + 14

    # 제목
    for line in tlines:
        draw.text((PAD, y), line, font=fh, fill=DARK)
        y += 72

    # 구분선
    y += 16
    draw.rectangle([PAD, y, PAD+180, y+4], fill=accent)
    y += 28

    # 본문
    for line in blines:
        draw.text((PAD, y), line, font=fb, fill=GRAY)
        y += 60

    # 도트
    _dots(draw, W//2, H-60, total, num-1, accent)

    return canvas


# ── CTA 슬라이드 ──────────────────────────────────────────────────────

def _render_cta(slide: dict, canvas: Image.Image, genre: str) -> Image.Image:
    theme   = GENRE_THEME.get(genre, _DEFAULT_THEME)
    W, H    = CAROUSEL_W, CAROUSEL_H
    PAD     = 80
    heading = _strip_emoji(slide.get("heading", "저장하고 나중에 보세요"))
    body    = _strip_emoji(slide.get("body", "") or "")
    accent  = theme["accent"]

    draw = ImageDraw.Draw(canvas)

    # ── 상단 컬러 블록 (35%)
    BH = H * 35 // 100
    _panel_gradient(draw, 0, 0, W, BH, theme["panel"], theme["panel2"])

    # 블록 안 — 흰 다이아몬드
    cx, cy = W//2, BH//2
    sz = 64
    draw.polygon([(cx, cy-sz), (cx+sz, cy), (cx, cy+sz), (cx-sz, cy)],
                 fill=WHITE)

    # ── 텍스트 영역 (BH 아래)
    fh     = _get_font(62, bold=True)
    fb     = _get_font(38)
    tlines = _wrap(heading, 62, W - PAD*2)
    blines = _wrap(body,    38, W - PAD*2) if body else []

    blk_h = len(tlines)*80 + 30 + len(blines)*52
    y     = BH + max(60, (H - BH - blk_h - 80) // 2)

    for line in tlines:
        x = _center_x(line, 62, PAD, W-PAD*2)
        draw.text((x, y), line, font=fh, fill=DARK)
        y += 80

    # 구분선
    draw.rectangle([PAD*2, y+10, W-PAD*2, y+14], fill=accent)
    y += 30

    for line in blines:
        x = _center_x(line, 38, PAD, W-PAD*2)
        draw.text((x, y), line, font=fb, fill=GRAY)
        y += 52

    # 하단 accent 바
    draw.rectangle([0, H-6, W, H], fill=accent)

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
            canvas = _render_cta(slide, canvas, genre)
        else:
            canvas = _render_content(slide, i, total, canvas, genre)

        out = job_dir / f"slide_{i:02d}.png"
        canvas.save(out, "PNG")
        paths.append(out)
    return paths


def pack_zip(slide_paths: list, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in slide_paths:
            zf.write(p, p.name)
