"""
인스타그램 캐러셀 슬라이드 렌더링 v2
- Pollinations AI 배경 이미지 (병렬 생성)
- 블러 + 다크 오버레이 효과
- 번들 한국어 폰트 (맑은고딕)
"""
import io
import re
import zipfile
import urllib.parse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CAROUSEL_W = 1080
CAROUSEL_H = 1350

_BASE_DIR   = Path(__file__).parent.parent
_FONT_BOLD  = _BASE_DIR / "assets" / "fonts" / "malgunbd.ttf"
_FONT_NORM  = _BASE_DIR / "assets" / "fonts" / "malgun.ttf"


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
    return re.sub(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF]+",
        "", text, flags=re.UNICODE,
    ).strip()


def _hex_rgb(hex_c: str) -> tuple:
    h = hex_c.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _accent(slide: dict) -> tuple:
    return _hex_rgb(slide.get("accent_color", "#ffcc00"))


def _wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw) -> list:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines or [""]


def _shadow(draw, xy, text, font, fill=(255,255,255), blur_col=(0,0,0)):
    draw.text((xy[0]+4, xy[1]+4), text, font=font, fill=blur_col)
    draw.text(xy, text, font=font, fill=fill)


# ── 배경 이미지 생성 ─────────────────────────────────────────────────

GENRE_BG_STYLE = {
    "재테크":      "luxury finance dark office, gold bokeh lights, premium",
    "자기계발":    "motivational sunrise mountain, dramatic light rays, cinematic",
    "교육/지식":   "dark library bookshelves, warm ambient light, intellectual",
    "라이프스타일":"cozy modern apartment, warm tones, aesthetic minimal",
    "건강/뷰티":   "wellness spa nature, soft morning light, fresh clean",
    "비즈니스":    "dark corporate city skyline, blue neon lights, professional",
}


def _build_bg_prompt(slide: dict, genre: str) -> str:
    style  = GENRE_BG_STYLE.get(genre, "dark modern professional background")
    s_type = slide.get("type", "content")
    if s_type == "cover":
        return f"{style}, dramatic cinematic, ultra HD, no text, no people"
    elif s_type == "cta":
        return f"warm bokeh lights, dark background, {style}, no text"
    else:
        return f"{style}, abstract depth of field, no text, 4K"


def _download_bg(prompt: str) -> Image.Image | None:
    try:
        encoded = urllib.parse.quote(prompt)
        seed    = abs(hash(prompt)) % 99999
        url     = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={CAROUSEL_W}&height={CAROUSEL_H}&nologo=true&seed={seed}"
        )
        resp = requests.get(url, timeout=50)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        return img.resize((CAROUSEL_W, CAROUSEL_H), Image.LANCZOS)
    except Exception:
        return None


def _make_canvas(slide: dict, genre: str) -> Image.Image:
    """AI 배경 다운로드 → 블러 → 다크 오버레이"""
    prompt = _build_bg_prompt(slide, genre)
    img    = _download_bg(prompt)

    if img is None:
        # 폴백: 그라디언트
        c1 = np.array(_hex_rgb(slide.get("bg_top", "#1a1a2e")), dtype=np.float32)
        c2 = np.array(_hex_rgb(slide.get("bg_bottom", "#0f3460")), dtype=np.float32)
        t  = np.linspace(0, 1, CAROUSEL_H).reshape(-1, 1)
        row = (c1*(1-t) + c2*t).astype(np.uint8)
        arr = np.broadcast_to(row.reshape(CAROUSEL_H, 1, 3), (CAROUSEL_H, CAROUSEL_W, 3)).copy()
        img = Image.fromarray(arr, "RGB")
    else:
        img = img.filter(ImageFilter.GaussianBlur(radius=10))

    # 다크 오버레이
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 155))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img


# ── 슬라이드 렌더링 ──────────────────────────────────────────────────

def _render_cover(slide: dict, canvas: Image.Image) -> Image.Image:
    draw   = ImageDraw.Draw(canvas)
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 80
    accent = _accent(slide)

    heading  = _strip_emoji(slide.get("heading",  ""))
    subtitle = _strip_emoji(slide.get("subtitle", "") or "")

    # 상단 강조선
    draw.rectangle([pad, 72, pad + 100, 80], fill=accent)

    # 메인 제목 (중앙)
    font_h = _get_font(82, bold=True)
    lines  = _wrap(heading, font_h, W - pad*2, draw)
    y = H//2 - len(lines)*96//2 - 40
    for line in lines:
        bx = draw.textbbox((0,0), line, font=font_h)
        x  = (W - (bx[2]-bx[0])) // 2
        _shadow(draw, (x, y), line, font_h)
        y += 96

    # 부제목
    if subtitle:
        y += 16
        font_s = _get_font(40)
        bx = draw.textbbox((0,0), subtitle, font=font_s)
        x  = (W - (bx[2]-bx[0])) // 2
        draw.text((x, y), subtitle, font=font_s, fill=(210,210,210))

    # 하단 스와이프 힌트
    font_t = _get_font(33)
    tip = ">> 스와이프해서 확인하세요"
    bx  = draw.textbbox((0,0), tip, font=font_t)
    x   = (W - (bx[2]-bx[0])) // 2
    draw.text((x, H - 108), tip, font=font_t, fill=accent)

    # 하단 선
    draw.rectangle([pad, H-68, W-pad, H-64], fill=(*accent, 100))
    return canvas


def _render_content(slide: dict, slide_num: int, total: int, canvas: Image.Image) -> Image.Image:
    draw   = ImageDraw.Draw(canvas)
    W, H   = CAROUSEL_W, CAROUSEL_H
    pad    = 72
    accent = _accent(slide)

    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")

    # 슬라이드 번호 (우상단)
    fn = _get_font(30)
    nt = f"{slide_num} / {total}"
    bx = draw.textbbox((0,0), nt, font=fn)
    draw.text((W - pad - (bx[2]-bx[0]), 52), nt, font=fn, fill=(150,150,150))

    # 좌측 세로 강조바
    bar_y = H//2 - 130
    draw.rectangle([pad, bar_y, pad+8, bar_y+190], fill=accent)

    # 제목
    fh = _get_font(64, bold=True)
    hl = _wrap(heading, fh, W - pad*2 - 30, draw)
    y  = bar_y
    for line in hl:
        _shadow(draw, (pad+26, y), line, fh)
        y += 80

    # 구분선
    y += 20
    draw.rectangle([pad+26, y, pad+110, y+4], fill=accent)
    y += 28

    # 본문
    if body:
        fb = _get_font(42)
        for line in _wrap(body, fb, W - pad*2 - 30, draw):
            draw.text((pad+26, y), line, font=fb, fill=(218,218,218))
            y += 60

    # 하단 도트 네비게이터
    dr, dg = 6, 18
    dw = total*(dr*2) + (total-1)*dg
    dx = (W - dw)//2
    dy = H - 68
    for i in range(total):
        col = accent if i == slide_num-1 else (70,70,70)
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

    # SAVE 텍스트
    fi = _get_font(90, bold=True)
    bx = draw.textbbox((0,0), "SAVE", font=fi)
    x  = (W - (bx[2]-bx[0])) // 2
    draw.text((x, H//2 - 280), "SAVE", font=fi, fill=accent)

    # 제목
    fh = _get_font(68, bold=True)
    lines = _wrap(heading, fh, W - pad*2, draw)
    y = H//2 - 50
    for line in lines:
        bx = draw.textbbox((0,0), line, font=fh)
        x  = (W - (bx[2]-bx[0])) // 2
        _shadow(draw, (x, y), line, fh, fill=accent)
        y += 86

    # 본문
    if body:
        y += 20
        fb = _get_font(38)
        for line in _wrap(body, fb, W - pad*2, draw):
            bx = draw.textbbox((0,0), line, font=fb)
            x  = (W - (bx[2]-bx[0])) // 2
            draw.text((x, y), line, font=fb, fill=(195,195,195))
            y += 52

    return canvas


# ── 메인 파이프라인 ──────────────────────────────────────────────────

def render_all_slides(slides: list, job_dir: Path, genre: str = "") -> list:
    """모든 슬라이드 렌더링 — AI 배경 병렬 생성 후 텍스트 오버레이"""
    total = len(slides)

    # 배경 이미지 병렬 생성
    backgrounds = [None] * total
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_make_canvas, slide, genre): i for i, slide in enumerate(slides)}
        for fut in as_completed(futs):
            backgrounds[futs[fut]] = fut.result()

    # 텍스트 오버레이 + 저장
    paths = []
    for i, (slide, bg) in enumerate(zip(slides, backgrounds), 1):
        canvas    = bg if bg else Image.new("RGB", (CAROUSEL_W, CAROUSEL_H), (20,20,46))
        s_type    = slide.get("type", "content")
        if s_type == "cover":
            canvas = _render_cover(slide, canvas)
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
