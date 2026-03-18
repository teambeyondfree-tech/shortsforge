"""
인스타그램 캐러셀 슬라이드 렌더링 v4
- 후킹 강화 커버 (스와이프 힌트 제거, 반투명 제목 박스)
- 다이나믹 배경 (대각선 밴드 + 도트 텍스처)
- 넘버 배지 콘텐츠 슬라이드
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

# Linux(Streamlit Cloud) Nanum 폰트 fallback
_NANUM_BOLD = Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
_NANUM_NORM = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")


# ── 유틸 ──────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [_FONT_BOLD, _NANUM_BOLD] if bold
        else [_FONT_NORM, _NANUM_NORM]
    )
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue
    return ImageFont.load_default()


def _strip_emoji(text: str) -> str:
    return re.sub(
        "[\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
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
    est_w = len(text) * font_size * 0.92
    return max(60, int((canvas_w - est_w) / 2))


def _draw_text(draw, x, y, text, font, color=(255, 255, 255), shadow=True):
    if shadow:
        draw.text((x+3, y+3), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)


def _alpha_rect(canvas: Image.Image, x1, y1, x2, y2, color_rgba) -> Image.Image:
    """반투명 사각형을 RGB 캔버스에 합성 후 RGB로 반환"""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([x1, y1, x2, y2], fill=color_rgba)
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


# ── 배경 생성 ─────────────────────────────────────────────────────────

GENRE_COLORS = {
    "재테크":       [("#0a0f1a", "#0d2035"), (255, 200,   0), ( 30,  70, 150)],
    "자기계발":     [("#0b0118", "#1a0433"), (190, 110, 255), ( 90,  25, 170)],
    "교육/지식":    [("#010b1a", "#082440"), (100, 185, 255), ( 15,  65, 135)],
    "라이프스타일": [("#100010", "#200020"), (255, 100, 180), (140,  25,  85)],
    "건강/뷰티":    [("#031510", "#082818"), ( 80, 230, 140), ( 18, 110,  60)],
    "비즈니스":     [("#090912", "#121228"), (155, 205, 255), ( 35,  55, 130)],
}


def _make_bg(slide: dict, genre: str) -> Image.Image:
    colors = GENRE_COLORS.get(genre, GENRE_COLORS["교육/지식"])
    (top_hex, bot_hex), accent_rgb, circle_rgb = colors

    # 1. 그라디언트 기본 배경
    c1  = np.array(_hex_rgb(top_hex), dtype=np.float32)
    c2  = np.array(_hex_rgb(bot_hex), dtype=np.float32)
    t   = np.linspace(0, 1, CAROUSEL_H).reshape(-1, 1)
    row = (c1*(1-t) + c2*t).astype(np.uint8)
    arr = np.broadcast_to(row.reshape(CAROUSEL_H, 1, 3),
                          (CAROUSEL_H, CAROUSEL_W, 3)).copy()
    img = Image.fromarray(arr, "RGB").convert("RGBA")

    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)

    # 2. 배경 큰 원 (깊이감)
    r1 = 540
    d.ellipse([-r1//3, -r1//5, r1*5//3, r1*6//5], fill=(*circle_rgb, 22))
    r2 = 440
    d.ellipse([CAROUSEL_W - r2*3//4, CAROUSEL_H - r2*3//4,
               CAROUSEL_W + r2*5//4, CAROUSEL_H + r2*5//4],
              fill=(*circle_rgb, 18))

    # 3. 대각선 accent 밴드 (역동감)
    mid = CAROUSEL_H * 2 // 5
    d.polygon([(0, mid),           (CAROUSEL_W, mid - 140),
               (CAROUSEL_W, mid - 140 + 55), (0, mid + 55)],
              fill=(*accent_rgb, 14))

    # 4. 도트 텍스처
    for gy in range(45, CAROUSEL_H, 90):
        for gx in range(45, CAROUSEL_W, 90):
            d.ellipse([gx-2, gy-2, gx+2, gy+2], fill=(*accent_rgb, 13))

    # 5. 상단 / 하단 accent 바
    d.rectangle([0, 0, CAROUSEL_W, 6], fill=(*accent_rgb, 230))
    d.rectangle([0, CAROUSEL_H - 5, CAROUSEL_W, CAROUSEL_H],
                fill=(*accent_rgb, 150))

    return Image.alpha_composite(img, ov).convert("RGB")


# ── 슬라이드 렌더링 ───────────────────────────────────────────────────

def _render_cover(slide: dict, canvas: Image.Image, genre: str) -> Image.Image:
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 80
    accent = _accent(slide)

    heading  = _strip_emoji(slide.get("heading",  ""))
    subtitle = _strip_emoji(slide.get("subtitle", "") or "")

    # 제목 영역 사전 계산
    fh      = _get_font(76, bold=True)
    lines   = _wrap(heading, 76, W - pad * 2)
    lh      = 93
    total_h = len(lines) * lh
    title_y = H // 2 - total_h // 2 - 70

    # 제목 뒤 반투명 박스 + 좌측 accent 바
    canvas = _alpha_rect(canvas,
                         pad - 22, title_y - 26,
                         W - pad + 22, title_y + total_h + 26,
                         (0, 0, 0, 95))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([pad - 22, title_y - 26,
                    pad - 16, title_y + total_h + 26], fill=accent)

    # 제목 텍스트
    y = title_y
    for line in lines:
        x = _text_x_center(line, 76, W)
        _draw_text(draw, x, y, line, fh, color=(255, 255, 255))
        y += lh

    # 부제목 (accent 색, 밑줄 강조)
    if subtitle:
        y  += 32
        fs  = _get_font(36)
        sx  = _text_x_center(subtitle, 36, W)
        sw  = int(len(subtitle) * 36 * 0.92)
        # 부제목 아래 얇은 accent 언더라인
        draw.rectangle([sx, y + 44, sx + sw, y + 48], fill=accent)
        _draw_text(draw, sx, y, subtitle, fs, color=(220, 220, 220), shadow=False)

    # 하단: 스크롤 인디케이터 도트 (스와이프 텍스트 대신)
    cx = W // 2
    dy = H - 68
    dots = [-40, -20, 0, 20, 40]
    for i, off in enumerate(dots):
        if i == 0:
            draw.ellipse([cx + off - 6, dy - 6, cx + off + 6, dy + 6],
                         fill=accent)
        else:
            draw.ellipse([cx + off - 4, dy - 4, cx + off + 4, dy + 4],
                         fill=(65, 65, 65))

    return canvas


def _render_content(slide: dict, num: int, total: int,
                    canvas: Image.Image) -> Image.Image:
    draw   = ImageDraw.Draw(canvas)
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 72
    accent = _accent(slide)

    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")

    # 우상단 슬라이드 번호
    fn = _get_font(28)
    draw.text((W - pad - 100, 48), f"{num} / {total}",
              font=fn, fill=(115, 115, 115))

    # 넘버 배지 — 원 + 숫자
    parts = heading.split(" ", 1)
    if parts[0].isdigit():
        badge_num     = parts[0]
        badge_heading = parts[1] if len(parts) > 1 else ""
    else:
        badge_num     = str(num - 1)
        badge_heading = heading

    bx, by, br = pad, 130, 46
    draw.ellipse([bx, by, bx + br*2, by + br*2], fill=accent)
    fb_badge = _get_font(34, bold=True)
    bnum_x   = bx + br - len(badge_num) * 10
    draw.text((bnum_x, by + br - 18), badge_num,
              font=fb_badge, fill=(15, 15, 15))

    # 제목
    fh    = _get_font(58, bold=True)
    lines = _wrap(badge_heading, 58, W - pad*2 - 20)
    y     = by + br*2 + 32
    for line in lines:
        _draw_text(draw, pad, y, line, fh)
        y += 74

    # 구분선
    y += 16
    draw.rectangle([pad, y, pad + 170, y + 4], fill=accent)
    y += 30

    # 본문
    if body:
        fb2   = _get_font(40)
        bwrap = _wrap(body, 40, W - pad*2)
        for line in bwrap:
            _draw_text(draw, pad, y, line, fb2,
                       color=(208, 208, 208), shadow=False)
            y += 58

    # 하단 진행 도트
    dr, dg = 7, 20
    dw = total*(dr*2) + (total-1)*dg
    dx = (W - dw) // 2
    dy2 = H - 68
    for i in range(total):
        col = accent if i == num - 1 else (55, 55, 55)
        draw.ellipse([dx, dy2-dr, dx+dr*2, dy2+dr], fill=col)
        dx += dr*2 + dg

    return canvas


def _render_cta(slide: dict, canvas: Image.Image) -> Image.Image:
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 80
    accent = _accent(slide)

    heading = _strip_emoji(slide.get("heading", "저장하고 나중에 보세요"))
    body    = _strip_emoji(slide.get("body", "") or "")

    # 제목 사전 계산
    fh      = _get_font(64, bold=True)
    lines   = _wrap(heading, 64, W - pad * 2)
    lh      = 82
    total_h = len(lines) * lh
    title_y = H // 2 - total_h // 2 - 50

    # 제목 뒤 반투명 박스
    canvas = _alpha_rect(canvas,
                         pad - 20, title_y - 28,
                         W - pad + 20, title_y + total_h + 28,
                         (0, 0, 0, 85))
    draw = ImageDraw.Draw(canvas)

    # 다이아몬드 장식 (제목 위)
    cx, cy = W // 2, title_y - 88
    sz     = 50
    draw.polygon([(cx, cy-sz), (cx+sz, cy), (cx, cy+sz), (cx-sz, cy)],
                 fill=(*accent, 215))

    # 제목
    y = title_y
    for line in lines:
        x = _text_x_center(line, 64, W)
        _draw_text(draw, x, y, line, fh, color=accent)
        y += lh

    # 본문
    if body:
        y += 24
        fb = _get_font(36)
        for line in _wrap(body, 36, W - pad * 2):
            x = _text_x_center(line, 36, W)
            _draw_text(draw, x, y, line, fb, color=(178, 178, 178), shadow=False)
            y += 50

    # 하단 이중 accent 선
    draw.rectangle([pad*2,      H - 86, W - pad*2,      H - 82],
                   fill=(*accent, 210))
    draw.rectangle([pad*2 + 40, H - 76, W - pad*2 - 40, H - 72],
                   fill=(*accent, 120))

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
