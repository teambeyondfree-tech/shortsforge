"""
최종 영상 합성 모듈 v2
drawtext 필터로 자막 직접 렌더링 (libass/fontconfig 의존 제거)
Pretendard 폰트 파일 직접 지정 → Windows/Linux 모두 정상
"""
import json
import subprocess
import random
import sys
import os
from pathlib import Path
import config

_SCOOP_SHIMS = os.path.expanduser("~/scoop/shims")
if _SCOOP_SHIMS not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _SCOOP_SHIMS + os.pathsep + os.environ.get("PATH", "")

# 자막 폰트 — Pretendard ExtraBold (항상 파일 직접 지정)
_FONT_FILE = config.BASE_DIR / "assets" / "fonts" / "Pretendard-ExtraBold.ttf"
_FONT_FALLBACK = config.BASE_DIR / "assets" / "fonts" / "malgunbd.ttf"


def _get_font_path() -> Path:
    return _FONT_FILE if _FONT_FILE.exists() else _FONT_FALLBACK


def _esc(path: Path) -> str:
    """ffmpeg 필터 문자열용 경로 이스케이프 (Windows/Linux 공통)"""
    s = str(path).replace("\\", "/")
    # Windows 드라이브 문자 콜론 이스케이프 (C:/path → C\:/path)
    if len(s) >= 2 and s[1] == ":":
        s = s[0] + "\\:" + s[2:]
    # 나머지 콜론 및 작은따옴표 이스케이프
    s = s.replace("'", "\\'")
    return s


def _build_drawtext_filter(segments: list, font_path: Path) -> str:
    """
    세그먼트 리스트 → ffmpeg drawtext 필터 문자열.
    각 세그먼트 텍스트는 파일로 저장돼 있음 (한국어 인코딩 안전).
    """
    if not segments:
        return "null"

    font_esc = _esc(font_path)
    parts = []
    for seg in segments:
        file_esc = _esc(Path(seg["file"]))
        s, e = seg["start"], seg["end"]
        part = (
            f"drawtext="
            f"fontfile='{font_esc}':"
            f"textfile='{file_esc}':"
            f"fontsize=82:"
            f"fontcolor=white:"
            f"borderw=7:"
            f"bordercolor=black:"
            f"line_spacing=12:"
            f"x=(w-text_w)/2:"
            f"y=h-340:"
            f"enable='between(t,{s},{e})'"
        )
        parts.append(part)

    return ",".join(parts)


def _get_random_bgm() -> Path | None:
    bgm_files = list(config.BGM_DIR.glob("*.mp3")) + list(config.BGM_DIR.glob("*.wav"))
    return random.choice(bgm_files) if bgm_files else None


def compose_final(
    video_path: Path,
    audio_path: Path,
    subtitle_path: Path,   # 이제 JSON 파일
    output_path: Path,
    lut_name: str | None = None,
) -> Path:
    print("  최종 합성 중...")

    # 자막 세그먼트 로드
    try:
        segments = json.loads(subtitle_path.read_text(encoding="utf-8"))
    except Exception:
        segments = []

    font_path  = _get_font_path()
    sub_filter = _build_drawtext_filter(segments, font_path)
    bgm_path   = _get_random_bgm()

    # 영상 필터: drawtext만 (null이면 vf 없음)
    vf = sub_filter if sub_filter != "null" else None

    if bgm_path:
        audio_filter = (
            f"[1:a]volume=1.0[voice];"
            f"[2:a]volume={config.BGM_VOLUME}[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[audio]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-stream_loop", "-1",
            "-i", str(bgm_path),
            "-filter_complex", audio_filter,
            "-map", "0:v",
            "-map", "[audio]",
        ]
        if vf:
            cmd += ["-vf", vf]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v",
            "-map", "1:a",
        ]
        if vf:
            cmd += ["-vf", vf]

    cmd += [
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"최종 합성 오류:\n{stderr[-1000:]}")

    print(f"  [완성] {output_path}")
    return output_path
