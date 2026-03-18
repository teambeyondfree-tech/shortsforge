"""
인스타그램 캐러셀 슬라이드 렌더링 v3
- 글자 수 기준 줄바꿈 (한글 textbbox 오측정 문제 해결)
- PIL 기하 도형으로 세련된 디자인
- 번들 한국어 폰트 (맑은고딕)
"""
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CAROUSEL_W = 1080
CAROUSEL_H = 1350

_BASE      = Path(__file__).parent.parent
_FONT_BOLD = _BASE / "assets" / "fonts" / "malgunbd.ttf"
_FONT_NORM = _BASE / "assets" / "fonts" / "malgun.ttf"


# ── 유틸 ─────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD if bold else _FONT_NORM
    if path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    return ImageFont.load_default()


def _strip_emoji(text: str) -> str:
    # 한글(U+AC00~U+D7A3)이 포함되는 넓은 범위 제거 — 이모지만 정확히 타겟
    return re.sub(
        "[\U0001F600-\U0001F64F"   # 감정 이모지
        "\U0001F300-\U0001F5FF"    # 기호 & 픽토그램
        "\U0001F680-\U0001F6FF"    # 교통 & 지도
        "\U0001F1E0-\U0001F1FF"    # 국기
        "\U00002702-\U000027B0"    # 딩뱃
        "\U0001F900-\U0001F9FF"    # 보충 기호
        "\U0001FA00-\U0001FA6F"    # 체스 기호
        "\U0001FA70-\U0001FAFF"    # 기호 확장
        "]+",
        "", text, flags=re.UNICODE,
    ).strip()


def _hex_rgb(hex_c: str) -> tuple:
    h = hex_c.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _accent(slide: dict) -> tuple:
    return _hex_rgb(slide.get("accent_color", "#ffcc00"))


def _wrap(text: str, font_size: int, max_width: int) -> list:
    """글자 수 기준 줄바꿈 — 한글 1글자 ≈ font_size * 0.92px"""
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


def _text_x_center(text: str, font_size: int, canvas_w: int) -> int:
    """한글 폭 추정으로 중앙 X 계산"""
    est_w = len(text) * font_size * 0.92
    return max(60, int((canvas_w - est_w) / 2))


def _draw_text(draw, x, y, text, font, color=(255,255,255), shadow=True):
    if shadow:
        draw.text((x+3, y+3), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)


# ── 배경 생성 ────────────────────────────────────────────────────────

GENRE_COLORS = {
    "재테크":      [("#0d1117", "#0d2137"), (255,200,0),   (20, 60,120)],
    "자기계발":    [("#0d0221", "#1a0533"), (180,100,255), (80, 20,160)],
    "교육/지식":   [("#020c1b", "#0a2540"), (100,180,255), (10, 60,120)],
    "라이프스타일":[("#0d0d0d", "#1a0a1a"), (255,100,180), (120,20,80)],
    "건강/뷰티":   [("#041a10", "#0a2e1a"), (100,255,160), (10,100,60)],
    "비즈니스":    [("#0d0d0d", "#1a1a2e"), (150,200,255), (30, 50,120)],
}


def _make_bg(slide: dict, genre: str) -> Image.Image:
    colors = GENRE_COLORS.get(genre, GENRE_COLORS["교육/지식"])
    (top_hex, bot_hex), accent_rgb, circle_rgb = colors

    c1 = np.array(_hex_rgb(top_hex), dtype=np.float32)
    c2 = np.array(_hex_rgb(bot_hex), dtype=np.float32)
    t  = np.linspace(0, 1, CAROUSEL_H).reshape(-1, 1)
    row = (c1*(1-t) + c2*t).astype(np.uint8)
    arr = np.broadcast_to(row.reshape(CAROUSEL_H, 1, 3), (CAROUSEL_H, CAROUSEL_W, 3)).copy()
    img = Image.fromarray(arr, "RGB").convert("RGBA")

    # 장식용 큰 원
    overlay = Image.new("RGBA", img.size, (0,0,0,0))
    d = ImageDraw.Draw(overlay)
    r1 = 480
    d.ellipse([-r1//2, CAROUSEL_H//4 - r1//2, -r1//2+r1*2, CAROUSEL_H//4 + r1*2 - r1//2],
              fill=(*circle_rgb, 28))
    r2 = 360
    d.ellipse([CAROUSEL_W - r2, CAROUSEL_H*3//4 - r2//2,
               CAROUSEL_W + r2, CAROUSEL_H*3//4 + r2*3//2],
              fill=(*circle_rgb, 22))
    # 얇은 선 장식
    d.rectangle([0, CAROUSEL_H//3, CAROUSEL_W, CAROUSEL_H//3+1], fill=(*accent_rgb, 35))
    d.rectangle([0, CAROUSEL_H*2//3, CAROUSEL_W, CAROUSEL_H*2//3+1], fill=(*accent_rgb, 20))

    img = Image.alpha_composite(img, overlay).convert("RGB")
    return img


# ── 슬라이드 렌더링 ──────────────────────────────────────────────────

def _render_cover(slide: dict, canvas: Image.Image, genre: str) -> Image.Image:
    draw   = ImageDraw.Draw(canvas)
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 80
    accent = _accent(slide)

    heading  = _strip_emoji(slide.get("heading",  ""))
    subtitle = _strip_emoji(slide.get("subtitle", "") or "")

    # 상단 장식바
    draw.rectangle([pad, 68, pad+120, 76], fill=accent)
    draw.rectangle([pad+130, 68, pad+145, 76], fill=(*accent, 120))

    # 메인 제목 — 80px
    fh    = _get_font(80, bold=True)
    lines = _wrap(heading, 80, W - pad*2)
    lh    = 98
    total = len(lines) * lh
    y     = H//2 - total//2 - 60

    for line in lines:
        x = _text_x_center(line, 80, W)
        _draw_text(draw, x, y, line, fh, color=(255,255,255))
        y += lh

    # 부제목 — 38px
    if subtitle:
        y += 18
        fs = _get_font(38)
        x  = _text_x_center(subtitle, 38, W)
        _draw_text(draw, x, y, subtitle, fs, color=(190,190,190), shadow=False)

    # 하단 스와이프 힌트
    ft  = _get_font(32)
    tip = ">> 스와이프해서 확인하세요"
    x   = _text_x_center(tip, 32, W)
    draw.text((x, H - 110), tip, font=ft, fill=accent)

    # 하단 강조선
    draw.rectangle([pad, H-72, W-pad, H-68], fill=(*accent, 160))
    return canvas


def _render_content(slide: dict, num: int, total: int, canvas: Image.Image) -> Image.Image:
    draw   = ImageDraw.Draw(canvas)
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 72
    accent = _accent(slide)

    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")

    # 우상단 슬라이드 번호
    fn = _get_font(30)
    draw.text((W - pad - 90, 52), f"{num} / {total}", font=fn, fill=(140,140,140))

    # 좌측 세로 강조바
    bar_y = H//2 - 140
    bar_h = 200
    draw.rectangle([pad, bar_y, pad+8, bar_y+bar_h], fill=accent)

    # 제목 — 62px, 좌측정렬
    fh    = _get_font(62, bold=True)
    lines = _wrap(heading, 62, W - pad*2 - 30)
    y     = bar_y

    for line in lines:
        _draw_text(draw, pad+26, y, line, fh)
        y += 78

    # 구분선
    y += 22
    draw.rectangle([pad+26, y, pad+130, y+4], fill=accent)
    y += 30

    # 본문 — 40px
    if body:
        fb    = _get_font(40)
        blines = _wrap(body, 40, W - pad*2 - 30)
        for line in blines:
            _draw_text(draw, pad+26, y, line, fb, color=(215,215,215), shadow=False)
            y += 58

    # 하단 도트
    dr, dg = 7, 20
    dw = total*(dr*2) + (total-1)*dg
    dx = (W - dw)//2
    dy = H - 70
    for i in range(total):
        col = accent if i == num-1 else (60,60,60)
        draw.ellipse([dx, dy-dr, dx+dr*2, dy+dr], fill=col)
        dx += dr*2 + dg

    return canvas


def _render_cta(slide: dict, canvas: Image.Image) -> Image.Image:
    draw   = ImageDraw.Draw(canvas)
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 80
    accent = _accent(slide)

    heading = _strip_emoji(slide.get("heading", "저장하고 나중에 보세요"))
    body    = _strip_emoji(slide.get("body", "") or "")

    # 중앙 큰 다이아몬드 장식
    cx, cy = W//2, H//2 - 220
    size   = 60
    draw.polygon([(cx, cy-size), (cx+size, cy), (cx, cy+size), (cx-size, cy)],
                 fill=(*accent, 200))

    # 제목 — 68px
    fh    = _get_font(68, bold=True)
    lines = _wrap(heading, 68, W - pad*2)
    lh    = 86
    y     = H//2 - 120

    for line in lines:
        x = _text_x_center(line, 68, W)
        _draw_text(draw, x, y, line, fh, color=accent)
        y += lh

    # 본문 — 38px
    if body:
        y += 20
        fb = _get_font(38)
        for line in _wrap(body, 38, W - pad*2):
            x = _text_x_center(line, 38, W)
            _draw_text(draw, x, y, line, fb, color=(190,190,190), shadow=False)
            y += 52

    # 하단 강조선
    draw.rectangle([pad*2, H-90, W-pad*2, H-86], fill=(*accent, 180))
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
