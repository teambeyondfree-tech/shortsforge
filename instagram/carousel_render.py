"""
인스타그램 캐러셀 슬라이드 렌더링
PIL로 그라디언트 배경 + 텍스트 오버레이 → PNG
"""
import io
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 인스타그램 캐러셀 크기 (4:5 세로형, 인스타 피드 최적)
CAROUSEL_W = 1080
CAROUSEL_H = 1350

import sys as _sys
if _sys.platform == "win32":
    FONT_BOLD   = "C:/Windows/Fonts/malgunbd.ttf"
    FONT_NORMAL = "C:/Windows/Fonts/malgun.ttf"
else:
    FONT_BOLD   = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    FONT_NORMAL = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def _strip_emoji(text: str) -> str:
    """PIL이 렌더링 못 하는 이모지 제거"""
    pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF]+",
        flags=re.UNICODE,
    )
    return pattern.sub("", text).strip()


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_NORMAL
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _make_gradient(w: int, h: int, top_hex: str, bottom_hex: str) -> Image.Image:
    """수직 그라디언트 배경 생성"""
    c1 = np.array(_hex_to_rgb(top_hex),    dtype=np.float32)
    c2 = np.array(_hex_to_rgb(bottom_hex), dtype=np.float32)
    t   = np.linspace(0, 1, h).reshape(-1, 1)          # (h, 1)
    row = (c1 * (1 - t) + c2 * t).astype(np.uint8)    # (h, 3)
    arr = np.broadcast_to(row.reshape(h, 1, 3), (h, w, 3)).copy()  # (h, w, 3)
    return Image.fromarray(arr, "RGB")


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    """텍스트 줄 바꿈"""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines or [""]


def _draw_text_shadow(draw: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill, shadow_offset=3, shadow_alpha=160):
    """그림자 효과 텍스트"""
    sx, sy = xy[0] + shadow_offset, xy[1] + shadow_offset
    draw.text((sx, sy), text, font=font, fill=(0, 0, 0))
    draw.text(xy, text, font=font, fill=fill)


def _accent_color(hex_c: str) -> tuple:
    return _hex_to_rgb(hex_c) if hex_c else (255, 204, 0)


def render_cover(slide: dict, canvas: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    W, H = canvas.size
    pad  = 80
    tw   = W - pad * 2

    heading  = _strip_emoji(slide.get("heading",  ""))
    subtitle = _strip_emoji(slide.get("subtitle", "") or "")
    accent   = _accent_color(slide.get("accent_color", "#ffcc00"))

    # 상단 브랜드 바
    draw.rectangle([pad, 60, pad + 6, 100], fill=accent)

    # 메인 제목 (가운데 약간 위)
    font_h = _get_font(76, bold=True)
    lines  = _wrap_text(heading, font_h, tw, draw)
    line_h = 92
    total  = len(lines) * line_h
    y = H // 2 - total // 2 - 60
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_h)
        x = (W - (bbox[2] - bbox[0])) // 2
        _draw_text_shadow(draw, (x, y), line, font_h, fill=(255, 255, 255))
        y += line_h

    # 부제목
    if subtitle:
        y += 24
        font_s = _get_font(38)
        bbox = draw.textbbox((0, 0), subtitle, font=font_s)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), subtitle, font=font_s, fill=(200, 200, 200))

    # 하단 스와이프 안내
    font_tip = _get_font(30)
    tip = ">> 스와이프해서 확인하세요"
    bbox = draw.textbbox((0, 0), tip, font=font_tip)
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x, H - 110), tip, font=font_tip, fill=(*accent, 200))

    # 하단 구분선
    draw.rectangle([pad, H - 70, W - pad, H - 66], fill=(*accent, 120))

    return canvas


def render_content(slide: dict, slide_num: int, total: int, canvas: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    W, H = canvas.size
    pad  = 72
    tw   = W - pad * 2

    heading = _strip_emoji(slide.get("heading", ""))
    body    = _strip_emoji(slide.get("body", "") or "")
    accent  = _accent_color(slide.get("accent_color", "#ff6b6b"))

    # 우상단 슬라이드 번호
    font_num = _get_font(28)
    num_txt  = f"{slide_num} / {total}"
    bbox = draw.textbbox((0, 0), num_txt, font=font_num)
    draw.text((W - pad - (bbox[2] - bbox[0]), 54), num_txt, font=font_num, fill=(140, 140, 140))

    # 좌측 세로 강조 바
    bar_h = 180
    bar_y = H // 2 - bar_h // 2 - 60
    draw.rectangle([pad, bar_y, pad + 7, bar_y + bar_h], fill=accent)

    # 제목
    font_h  = _get_font(62, bold=True)
    lines_h = _wrap_text(heading, font_h, tw - 20, draw)
    y = bar_y
    for line in lines_h:
        _draw_text_shadow(draw, (pad + 24, y), line, font_h, fill=(255, 255, 255))
        y += 74

    # 구분선
    y += 16
    draw.rectangle([pad + 24, y, pad + 24 + 60, y + 3], fill=accent)
    y += 22

    # 본문
    if body:
        font_b  = _get_font(40)
        lines_b = _wrap_text(body, font_b, tw - 20, draw)
        for line in lines_b:
            draw.text((pad + 24, y), line, font=font_b, fill=(210, 210, 210))
            y += 54

    # 하단 도트 네비게이터
    dot_r  = 6
    dot_gap = 20
    total_dots_w = total * (dot_r * 2) + (total - 1) * dot_gap
    dx = (W - total_dots_w) // 2
    dy = H - 70
    for i in range(total):
        color = accent if i == slide_num - 1 else (80, 80, 80)
        draw.ellipse([dx, dy - dot_r, dx + dot_r * 2, dy + dot_r], fill=color)
        dx += dot_r * 2 + dot_gap

    return canvas


def render_cta(slide: dict, canvas: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(canvas)
    W, H = canvas.size
    pad  = 80
    tw   = W - pad * 2

    heading = _strip_emoji(slide.get("heading", "저장하고 나중에 보세요"))
    body    = _strip_emoji(slide.get("body", "") or "")
    accent  = _accent_color(slide.get("accent_color", "#ffcc00"))

    # 큰 원형 배경 장식
    circle_size = 320
    cx, cy = W // 2, H // 2 - 80
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.ellipse(
        [cx - circle_size, cy - circle_size, cx + circle_size, cy + circle_size],
        fill=(*accent, 18),
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 저장 아이콘 대체 텍스트 (bookmark)
    font_icon = _get_font(90, bold=True)
    icon_txt  = "[SAVE]"
    bbox = draw.textbbox((0, 0), icon_txt, font=font_icon)
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x, H // 2 - 240), icon_txt, font=font_icon, fill=accent)

    # 제목
    font_h = _get_font(66, bold=True)
    lines  = _wrap_text(heading, font_h, tw, draw)
    y = H // 2 - 60
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_h)
        x = (W - (bbox[2] - bbox[0])) // 2
        _draw_text_shadow(draw, (x, y), line, font_h, fill=accent)
        y += 80

    # 본문
    if body:
        y += 20
        font_b  = _get_font(36)
        lines_b = _wrap_text(body, font_b, tw, draw)
        for line in lines_b:
            bbox = draw.textbbox((0, 0), line, font=font_b)
            x = (W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=font_b, fill=(190, 190, 190))
            y += 50

    return canvas


def render_slide(slide: dict, slide_num: int, total: int, job_dir: Path) -> Path:
    """슬라이드 1개 렌더링 → PNG 저장"""
    bg_top    = slide.get("bg_top",    "#1a1a2e")
    bg_bottom = slide.get("bg_bottom", "#0f3460")
    canvas    = _make_gradient(CAROUSEL_W, CAROUSEL_H, bg_top, bg_bottom)

    slide_type = slide.get("type", "content")
    if slide_type == "cover":
        canvas = render_cover(slide, canvas)
    elif slide_type == "cta":
        canvas = render_cta(slide, canvas)
    else:
        canvas = render_content(slide, slide_num, total, canvas)

    out_path = job_dir / f"slide_{slide_num:02d}.png"
    canvas.save(out_path, "PNG")
    return out_path


def render_all_slides(slides: list, job_dir: Path) -> list:
    """모든 슬라이드 렌더링, Path 리스트 반환"""
    total = len(slides)
    paths = []
    for i, slide in enumerate(slides, 1):
        path = render_slide(slide, i, total, job_dir)
        paths.append(path)
    return paths


def pack_zip(slide_paths: list, zip_path: Path):
    """슬라이드 이미지들을 ZIP으로 묶기"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in slide_paths:
            zf.write(p, p.name)
