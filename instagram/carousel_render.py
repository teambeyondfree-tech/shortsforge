"""
인스타그램 캐러셀 슬라이드 렌더링 v8
고성과 SNS 콘텐츠 기반 3가지 템플릿
  - Template A (커버): AI 생성 배경 + 다크 오버레이, 임팩트형
  - Template B (콘텐츠): 단색 다크 + 좌측 강조선 + 정밀 중앙정렬
  - Template C (CTA): 솔리드 컬러, 행동유도형
캔버스: 1080 × 1080 정사각형
폰트: Pretendard (맑은고딕 fallback)
"""
import io
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CANVAS  = 1080
PAD     = int(CANVAS * 0.15)   # 162px — 여백이 디자인이다
CONTENT = CANVAS - PAD * 2     # 756px

_BASE             = Path(__file__).parent.parent
_FONT_PRETENDARD_BOLD = _BASE / "assets" / "fonts" / "Pretendard-ExtraBold.ttf"
_FONT_PRETENDARD_REG  = _BASE / "assets" / "fonts" / "Pretendard-Regular.ttf"
_FONT_BOLD        = _BASE / "assets" / "fonts" / "malgunbd.ttf"
_FONT_NORM        = _BASE / "assets" / "fonts" / "malgun.ttf"
_NANUM_BOLD       = Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
_NANUM_NORM       = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")

# ── 장르별 검증 팔레트 ────────────────────────────────────────────────
GENRE_THEME = {
    "재테크": {
        "grad":    [(26, 26, 46), (22, 33, 62), (15, 52, 96)],
        "solid":   (10, 14, 28),
        "cta":     (15, 52, 96),
        "text":    (255, 255, 255),
        "sub":     (185, 200, 225),
        "accent":  (93, 160, 245),
        "bg_prompt": "dark navy financial district at night, city lights bokeh, cinematic",
    },
    "자기계발": {
        "grad":    [(45, 27, 105), (91, 44, 142)],
        "solid":   (22, 10, 55),
        "cta":     (68, 30, 110),
        "text":    (255, 255, 255),
        "sub":     (195, 175, 235),
        "accent":  (196, 136, 252),
        "bg_prompt": "purple aurora borealis over mountain silhouette, inspirational, cinematic",
    },
    "교육/지식": {
        "grad":    [(15, 15, 15), (30, 30, 30)],
        "solid":   (12, 12, 12),
        "cta":     (20, 20, 20),
        "text":    (255, 255, 255),
        "sub":     (175, 175, 175),
        "accent":  (220, 220, 220),
        "bg_prompt": "minimal dark library with dramatic lighting, knowledge, cinematic",
    },
    "라이프스타일": {
        "grad":    [(29, 53, 87), (69, 123, 157)],
        "solid":   (14, 28, 46),
        "cta":     (29, 53, 87),
        "text":    (241, 250, 238),
        "sub":     (175, 210, 220),
        "accent":  (130, 215, 252),
        "bg_prompt": "cozy lifestyle aesthetic, morning coffee bokeh, soft warm light, minimal",
    },
    "건강/뷰티": {
        "grad":    [(8, 38, 22), (5, 78, 48)],
        "solid":   (6, 22, 14),
        "cta":     (5, 78, 48),
        "text":    (255, 255, 255),
        "sub":     (175, 220, 200),
        "accent":  (114, 232, 162),
        "bg_prompt": "fresh green nature wellness background, soft bokeh, healthy lifestyle",
    },
    "비즈니스": {
        "grad":    [(26, 26, 26), (51, 51, 51)],
        "solid":   (14, 14, 14),
        "cta":     (26, 26, 26),
        "text":    (255, 255, 255),
        "sub":     (175, 175, 175),
        "accent":  (255, 107, 53),
        "bg_prompt": "modern minimalist office interior dark, professional, cinematic lighting",
    },
}
_DEFAULT = GENRE_THEME["교육/지식"]


# ── 유틸 ──────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if bold:
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


def _strip_emoji(text: str) -> str:
    return re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        r"\U00002702-\U000027B0\U0001F900-\U0001F9FF"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+",
        "", text, flags=re.UNICODE,
    ).strip()


def _measure(text: str, font) -> tuple:
    """PIL textbbox로 정확한 텍스트 크기 측정"""
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bb = dummy.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]   # width, height


def _wrap_precise(text: str, font, max_w: int, max_lines: int = 99) -> list:
    """textbbox 기반 정확한 줄바꿈"""
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


def _draw_centered(draw, y: int, text: str, font, color: tuple):
    """캔버스 전체 폭 기준 정확한 중앙정렬"""
    w, _ = _measure(text, font)
    x = (CANVAS - w) // 2
    draw.text((x, y), text, font=font, fill=color)


def _diag_gradient(colors: list) -> Image.Image:
    """대각선 그라디언트 (좌상→우하), colors = 2 or 3개 RGB tuple"""
    W = H = CANVAS
    x = np.arange(W, dtype=np.float32).reshape(1, W)
    y = np.arange(H, dtype=np.float32).reshape(H, 1)
    t = (x + y) / (W + H - 2)

    c = [np.array(c, dtype=np.float32) for c in colors]
    t3 = t[:, :, np.newaxis]

    if len(c) == 2:
        arr = c[0] * (1 - t3) + c[1] * t3
    else:
        half = t < 0.5
        s1   = np.clip(t * 2, 0, 1)[:, :, np.newaxis]
        s2   = np.clip(t * 2 - 1, 0, 1)[:, :, np.newaxis]
        seg1 = c[0] * (1 - s1) + c[1] * s1
        seg2 = c[1] * (1 - s2) + c[2] * s2
        arr  = np.where(half[:, :, np.newaxis], seg1, seg2)

    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _fetch_ai_background(prompt: str, genre_grad: list) -> Image.Image:
    """
    Gemini Imagen으로 커버 배경 생성.
    실패 시 대각선 그라디언트 fallback.
    """
    try:
        import config
        from google import genai
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        full_prompt = (
            f"{prompt}, square format 1:1, dark moody aesthetic, "
            "no text, no people, ultra high quality"
        )
        response = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=full_prompt,
            config={"number_of_images": 1, "aspect_ratio": "1:1"},
        )
        img_bytes = response.generated_images[0].image.image_bytes
        bg = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((CANVAS, CANVAS))
        return bg
    except Exception as e:
        print(f"  [배경 생성 실패, fallback] {e}")
        return _diag_gradient(genre_grad)


def _apply_dark_overlay(bg: Image.Image, opacity: int = 155) -> Image.Image:
    """배경 위에 다크 오버레이 합성 (텍스트 가독성 확보)"""
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, opacity))
    result  = bg.convert("RGBA")
    result  = Image.alpha_composite(result, overlay)
    return result.convert("RGB")


def _watermark_text(canvas: Image.Image, text: str, color: tuple, opacity: int = 18):
    """배경에 반투명 대형 워터마크 타이포 (시각적 깊이감)"""
    draw   = ImageDraw.Draw(canvas, "RGBA")
    fs     = 280
    font   = _get_font(fs, bold=True)
    w, _   = _measure(text, font)
    x      = (CANVAS - w) // 2
    y      = (CANVAS - fs) // 2 - 60
    r, g, b = color
    draw.text((x, y), text, font=font, fill=(r, g, b, opacity))


# ── Template A: 임팩트형 커버 ─────────────────────────────────────────

def _render_cover(slide: dict, genre: str, use_ai_bg: bool = True) -> Image.Image:
    th      = GENRE_THEME.get(genre, _DEFAULT)
    heading = _strip_emoji(slide.get("heading", ""))
    sub     = _strip_emoji(slide.get("subtitle", "") or "")

    # 배경
    if use_ai_bg:
        bg = _fetch_ai_background(th.get("bg_prompt", ""), th["grad"])
    else:
        bg = _diag_gradient(th["grad"])
    canvas = _apply_dark_overlay(bg, opacity=160)

    # 반투명 워터마크 (장르 영문)
    wm_map = {
        "재테크": "MONEY", "자기계발": "GROW", "교육/지식": "KNOW",
        "라이프스타일": "LIFE", "건강/뷰티": "GLOW", "비즈니스": "BIZ",
    }
    _watermark_text(canvas, wm_map.get(genre, ""), th["accent"], opacity=20)

    draw = ImageDraw.Draw(canvas)

    # ── 메인 카피 (max 2줄, ExtraBold)
    FS_MAIN = 82
    LH_MAIN = int(FS_MAIN * 1.28)
    fmain   = _get_font(FS_MAIN, bold=True)
    mlines  = _wrap_precise(heading, fmain, CONTENT, max_lines=2)

    # ── 서브 카피 (메인의 40%, max 1줄)
    FS_SUB  = int(FS_MAIN * 0.40)
    LH_SUB  = int(FS_SUB * 1.3)
    fsub    = _get_font(FS_SUB)
    slines  = _wrap_precise(sub, fsub, CONTENT, max_lines=1) if sub else []

    # 전체 블록 높이 → 수직 중앙
    blk_h = len(mlines) * LH_MAIN + (32 + LH_SUB if slines else 0)
    y     = (CANVAS - blk_h) // 2

    for line in mlines:
        _draw_centered(draw, y, line, fmain, th["text"])
        y += LH_MAIN

    if slines:
        y += 32
        _draw_centered(draw, y, slines[0], fsub, th["sub"])

    # ── 하단 카테고리 태그
    ftag = _get_font(22)
    tag  = f"# {genre}"
    tw, _ = _measure(tag, ftag)
    tx = (CANVAS - tw) // 2
    draw.text((tx, CANVAS - PAD + 20), tag, font=ftag, fill=th["accent"])

    return canvas


# ── Template B: 정보형 콘텐츠 ─────────────────────────────────────────

def _render_content(slide: dict, num: int, total: int, genre: str) -> Image.Image:
    th      = GENRE_THEME.get(genre, _DEFAULT)
    canvas  = Image.new("RGB", (CANVAS, CANVAS), th["solid"])
    draw    = ImageDraw.Draw(canvas)
    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")

    # 배지 번호 파싱
    parts   = heading.split(" ", 1)
    num_txt = parts[0] if parts and parts[0].isdigit() else str(num - 1)
    title   = parts[1] if len(parts) > 1 and parts[0].isdigit() else heading

    # 본문 → 첫 문장 하이라이트 / 나머지
    sentences = re.split(r"(?<=[.?!。])\s*", body.strip()) if body else []
    highlight = sentences[0] if sentences else ""
    rest_body = " ".join(sentences[1:]) if len(sentences) > 1 else ""

    FS_NUM = 100; LH_NUM = 115
    FS_H   = 56;  LH_H   = int(FS_H * 1.28)
    FS_HL  = 40;  LH_HL  = int(FS_HL * 1.3)
    FS_B   = 34;  LH_B   = int(FS_B * 1.3)

    fnum  = _get_font(FS_NUM, bold=True)
    fh    = _get_font(FS_H,   bold=True)
    fhl   = _get_font(FS_HL)
    fb    = _get_font(FS_B)

    hlines  = _wrap_precise(title,     fh,  CONTENT,        max_lines=2)
    hllines = _wrap_precise(highlight, fhl, CONTENT,        max_lines=2) if highlight else []
    blines  = _wrap_precise(rest_body, fb,  CONTENT,        max_lines=2) if rest_body else []

    # 전체 블록 높이
    blk = (LH_NUM + 20
           + len(hlines) * LH_H
           + (32 + len(hllines) * LH_HL if hllines else 0)
           + (20 + len(blines)  * LH_B  if blines  else 0))
    y = (CANVAS - blk) // 2

    # 슬라이드 번호 (우상단)
    draw.text((CANVAS - PAD - 60, PAD // 2),
              f"{num}/{total}", font=_get_font(24), fill=th["sub"])

    # 큰 숫자 (accent)
    _draw_centered(draw, y, num_txt, fnum, th["accent"])
    y += LH_NUM + 20

    # 제목 (bold)
    for line in hlines:
        _draw_centered(draw, y, line, fh, th["text"])
        y += LH_H

    # 좌측 강조선 + 하이라이트 문장
    if hllines:
        y += 32
        # 강조선: 좌측 PAD 위치에 3px accent 세로선
        line_h = len(hllines) * LH_HL
        draw.rectangle([PAD, y, PAD + 3, y + line_h], fill=th["accent"])
        for line in hllines:
            _draw_centered(draw, y, line, fhl, th["accent"])
            y += LH_HL

    # 나머지 본문 (sub color)
    if blines:
        y += 20
        for line in blines:
            _draw_centered(draw, y, line, fb, th["sub"])
            y += LH_B

    return canvas


# ── Template C: CTA형 ─────────────────────────────────────────────────

def _render_cta(slide: dict, genre: str) -> Image.Image:
    th      = GENRE_THEME.get(genre, _DEFAULT)
    canvas  = Image.new("RGB", (CANVAS, CANVAS), th["cta"])
    draw    = ImageDraw.Draw(canvas)
    heading = _strip_emoji(slide.get("heading", "저장하고 나중에 보세요"))
    body    = _strip_emoji(slide.get("body", "") or "")

    FS_MAIN = 68; LH_MAIN = int(FS_MAIN * 1.28)
    FS_SUB  = int(FS_MAIN * 0.45); LH_SUB = int(FS_SUB * 1.3)

    fmain  = _get_font(FS_MAIN, bold=True)
    fsub   = _get_font(FS_SUB)
    mlines = _wrap_precise(heading, fmain, CONTENT, max_lines=2)
    slines = _wrap_precise(body,    fsub,  CONTENT, max_lines=1) if body else []

    sep_h = 2
    blk_h = (len(mlines) * LH_MAIN
             + (32 + sep_h + 32 + LH_SUB if slines else 0))
    y = (CANVAS - blk_h) // 2

    for line in mlines:
        _draw_centered(draw, y, line, fmain, th["text"])
        y += LH_MAIN

    if slines:
        y += 32
        lw = int(CONTENT * 0.4)
        lx = PAD + (CONTENT - lw) // 2
        draw.rectangle([lx, y, lx + lw, y + sep_h], fill=th["sub"])
        y += sep_h + 32
        _draw_centered(draw, y, slines[0], fsub, th["sub"])

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
            canvas = _render_cta(slide, genre)
        else:
            canvas = _render_content(slide, i, total, genre)

        out = job_dir / f"slide_{i:02d}.png"
        canvas.save(out, "PNG")
        paths.append(out)
    return paths


def pack_zip(slide_paths: list, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in slide_paths:
            zf.write(p, p.name)
