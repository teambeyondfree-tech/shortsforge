"""
인스타그램 캐러셀 슬라이드 렌더링 v7
고성과 SNS 콘텐츠 기반 3가지 템플릿
  - Template A (커버): 대각선 그라디언트, 임팩트형
  - Template B (콘텐츠): 단색 다크, 정보형
  - Template C (CTA): 솔리드 컬러, 행동유도형
캔버스: 1080 × 1080 정사각형
"""
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CANVAS  = 1080
PAD     = int(CANVAS * 0.15)   # 162px — 여백이 디자인이다
CONTENT = CANVAS - PAD * 2     # 756px

_BASE       = Path(__file__).parent.parent
_FONT_BOLD  = _BASE / "assets" / "fonts" / "malgunbd.ttf"
_FONT_NORM  = _BASE / "assets" / "fonts" / "malgun.ttf"
_NANUM_BOLD = Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
_NANUM_NORM = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")

# ── 장르별 검증 팔레트 ────────────────────────────────────────────────
GENRE_THEME = {
    "재테크": {
        "grad":    [(26, 26, 46), (22, 33, 62), (15, 52, 96)],
        "solid":   (10, 14, 28),
        "cta":     (15, 52, 96),
        "text":    (255, 255, 255),
        "sub":     (185, 200, 225),   # ~65% opacity 근사
        "accent":  (93, 160, 245),    # bright blue
    },
    "자기계발": {
        "grad":    [(45, 27, 105), (91, 44, 142)],
        "solid":   (22, 10, 55),
        "cta":     (68, 30, 110),
        "text":    (255, 255, 255),
        "sub":     (195, 175, 235),
        "accent":  (196, 136, 252),   # bright purple
    },
    "교육/지식": {
        "grad":    [(15, 15, 15), (30, 30, 30)],
        "solid":   (12, 12, 12),
        "cta":     (20, 20, 20),
        "text":    (255, 255, 255),
        "sub":     (175, 175, 175),
        "accent":  (220, 220, 220),
    },
    "라이프스타일": {
        "grad":    [(29, 53, 87), (69, 123, 157)],
        "solid":   (14, 28, 46),
        "cta":     (29, 53, 87),
        "text":    (241, 250, 238),
        "sub":     (175, 210, 220),
        "accent":  (130, 215, 252),   # sky blue
    },
    "건강/뷰티": {
        "grad":    [(8, 38, 22), (5, 78, 48)],
        "solid":   (6, 22, 14),
        "cta":     (5, 78, 48),
        "text":    (255, 255, 255),
        "sub":     (175, 220, 200),
        "accent":  (114, 232, 162),   # mint
    },
    "비즈니스": {
        "grad":    [(26, 26, 26), (51, 51, 51)],
        "solid":   (14, 14, 14),
        "cta":     (26, 26, 26),
        "text":    (255, 255, 255),
        "sub":     (175, 175, 175),
        "accent":  (255, 107, 53),    # orange
    },
}
_DEFAULT = GENRE_THEME["교육/지식"]


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


def _wrap(text: str, font_size: int, max_w: int, max_lines: int = 99) -> list:
    cpp   = max(5, int(max_w / (font_size * 0.92)))
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) <= cpp:
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


def _cx(text: str, fs: int) -> int:
    """content 영역 내 중앙 X"""
    est = len(text) * fs * 0.92
    return PAD + max(0, int((CONTENT - est) / 2))


def _draw_centered(draw, y: int, text: str, font, color: tuple):
    x = _cx(text, font.size if hasattr(font, "size") else 40)
    draw.text((x, y), text, font=font, fill=color)
    return y


def _diag_gradient(colors: list) -> Image.Image:
    """대각선 그라디언트 (좌상→우하), colors = 2 or 3개 RGB tuple"""
    W = H = CANVAS
    x = np.arange(W, dtype=np.float32).reshape(1, W)
    y = np.arange(H, dtype=np.float32).reshape(H, 1)
    t = (x + y) / (W + H - 2)           # shape (H, W), 0→1

    c = [np.array(c, dtype=np.float32) for c in colors]
    t3 = t[:, :, np.newaxis]            # (H, W, 1)

    if len(c) == 2:
        arr = c[0] * (1 - t3) + c[1] * t3
    else:  # 3-color
        half = t < 0.5
        s1   = np.clip(t * 2, 0, 1)[:, :, np.newaxis]
        s2   = np.clip(t * 2 - 1, 0, 1)[:, :, np.newaxis]
        seg1 = c[0] * (1 - s1) + c[1] * s1
        seg2 = c[1] * (1 - s2) + c[2] * s2
        arr  = np.where(half[:, :, np.newaxis], seg1, seg2)

    return Image.fromarray(arr.astype(np.uint8), "RGB")


# ── Template A: 임팩트형 커버 ─────────────────────────────────────────

def _render_cover(slide: dict, genre: str) -> Image.Image:
    th      = GENRE_THEME.get(genre, _DEFAULT)
    canvas  = _diag_gradient(th["grad"])
    draw    = ImageDraw.Draw(canvas)
    heading = _strip_emoji(slide.get("heading", ""))
    sub     = _strip_emoji(slide.get("subtitle", "") or "")

    # ── 메인 카피 (max 2줄, weight 800, line-height 1.3)
    FS_MAIN = 82
    LH_MAIN = int(FS_MAIN * 1.3)   # 107
    fmain   = _get_font(FS_MAIN, bold=True)
    mlines  = _wrap(heading, FS_MAIN, CONTENT, max_lines=2)

    # ── 서브 카피 (메인의 40%, max 1줄)
    FS_SUB  = int(FS_MAIN * 0.40)   # 33
    LH_SUB  = int(FS_SUB * 1.3)    # 43
    fsub    = _get_font(FS_SUB)
    slines  = _wrap(sub, FS_SUB, CONTENT, max_lines=1) if sub else []

    # 전체 블록 높이 → 수직 중앙
    blk_h = len(mlines) * LH_MAIN + (28 + LH_SUB if slines else 0)
    y     = (CANVAS - blk_h) // 2

    for line in mlines:
        _draw_centered(draw, y, line, fmain, th["text"])
        y += LH_MAIN

    if slines:
        y += 28
        _draw_centered(draw, y, slines[0], fsub, th["sub"])

    # ── 하단 카테고리 태그 (작게, accent)
    ftag = _get_font(22)
    tag  = f"# {genre}"
    tx   = _cx(tag, 22)
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

    # 본문 → 첫 문장 하이라이트 / 나머지 본문
    sentences = re.split(r"(?<=[.?!。])\s*", body.strip()) if body else []
    highlight = sentences[0] if sentences else ""
    rest_body = " ".join(sentences[1:]) if len(sentences) > 1 else ""

    # 폰트
    FS_NUM  = 100; LH_NUM  = 115
    FS_H    = 56;  LH_H    = int(FS_H * 1.3)
    FS_HL   = 40;  LH_HL   = int(FS_HL * 1.3)
    FS_B    = 36;  LH_B    = int(FS_B * 1.3)

    fnum  = _get_font(FS_NUM, bold=True)
    fh    = _get_font(FS_H,   bold=True)
    fhl   = _get_font(FS_HL)
    fb    = _get_font(FS_B)

    hlines = _wrap(title,     FS_H,  CONTENT, max_lines=2)
    hllines = _wrap(highlight, FS_HL, CONTENT, max_lines=2) if highlight else []
    blines  = _wrap(rest_body, FS_B,  CONTENT, max_lines=2) if rest_body else []

    # 전체 블록 높이
    blk = (LH_NUM + 20
           + len(hlines) * LH_H
           + (32 + len(hllines) * LH_HL if hllines else 0)
           + (20 + len(blines)  * LH_B  if blines  else 0))
    y = (CANVAS - blk) // 2

    # 슬라이드 번호 (우상단, 작고 연하게)
    draw.text((CANVAS - PAD - 60, PAD // 2),
              f"{num}/{total}", font=_get_font(24), fill=th["sub"])

    # 큰 숫자 (accent)
    _draw_centered(draw, y, num_txt, fnum, th["accent"])
    y += LH_NUM + 20

    # 제목 (bold, text)
    for line in hlines:
        _draw_centered(draw, y, line, fh, th["text"])
        y += LH_H

    # 하이라이트 문장 (accent)
    if hllines:
        y += 32
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

    FS_MAIN = 68; LH_MAIN = int(FS_MAIN * 1.3)
    FS_SUB  = int(FS_MAIN * 0.45); LH_SUB = int(FS_SUB * 1.3)

    fmain  = _get_font(FS_MAIN, bold=True)
    fsub   = _get_font(FS_SUB)
    mlines = _wrap(heading, FS_MAIN, CONTENT, max_lines=2)
    slines = _wrap(body,    FS_SUB,  CONTENT, max_lines=1) if body else []

    sep_h = 2
    blk_h = (len(mlines) * LH_MAIN
             + (32 + sep_h + 32 + LH_SUB if slines else 0))
    y = (CANVAS - blk_h) // 2

    for line in mlines:
        _draw_centered(draw, y, line, fmain, th["text"])
        y += LH_MAIN

    if slines:
        y += 32
        # 얇은 구분선 (심플하게)
        lw = int(CONTENT * 0.4)
        lx = PAD + (CONTENT - lw) // 2
        draw.rectangle([lx, y, lx + lw, y + sep_h],
                       fill=(*th["sub"], 120) if len(th["sub"]) == 3
                       else th["sub"])
        y += sep_h + 32
        _draw_centered(draw, y, slines[0], fsub, th["sub"])

    return canvas


# ── 메인 ──────────────────────────────────────────────────────────────

def render_all_slides(slides: list, job_dir: Path, genre: str = "") -> list:
    total = len(slides)
    paths = []
    for i, slide in enumerate(slides, 1):
        s_type = slide.get("type", "content")
        if s_type == "cover":
            canvas = _render_cover(slide, genre)
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
