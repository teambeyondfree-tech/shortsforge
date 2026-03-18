"""
최종 영상 합성 모듈
영상 클립 + 음성 + 자막 + BGM → 완성 mp4
"""
import subprocess
import random
import os
from pathlib import Path
import config

_SCOOP_SHIMS = os.path.expanduser("~/scoop/shims")
if _SCOOP_SHIMS not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _SCOOP_SHIMS + os.pathsep + os.environ.get("PATH", "")


def _get_random_bgm() -> Path | None:
    """BGM 폴더에서 랜덤 BGM 선택"""
    bgm_files = list(config.BGM_DIR.glob("*.mp3")) + list(config.BGM_DIR.glob("*.wav"))
    if not bgm_files:
        return None
    return random.choice(bgm_files)


def _apply_lut(input_path: Path, output_path: Path, lut_name: str | None) -> Path:
    """LUT 색보정 적용 (선택사항)"""
    if not lut_name:
        return input_path

    lut_path = config.LUTS_DIR / lut_name
    if not lut_path.exists():
        return input_path

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", f"lut3d='{lut_path}'",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return output_path
    return input_path  # LUT 실패 시 원본 반환


def compose_final(
    video_path: Path,
    audio_path: Path,
    subtitle_path: Path,
    output_path: Path,
    lut_name: str | None = None,
) -> Path:
    """
    영상 + 음성 + 자막 + BGM 합성 → 최종 mp4.
    """
    print("  최종 합성 중...")
    bgm_path = _get_random_bgm()

    # 자막 필터
    sub_filter = f"ass='{subtitle_path.resolve()}'"
    # Windows 경로 역슬래시 이스케이프
    sub_filter = sub_filter.replace("\\", "/").replace(":", "\\:")

    if bgm_path:
        # 영상 + 목소리 + BGM 믹싱
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),          # 영상 (음성 없음)
            "-i", str(audio_path),          # 나레이션
            "-stream_loop", "-1",
            "-i", str(bgm_path),            # BGM (루프)
            "-filter_complex",
            f"[1:a]volume=1.0[voice];"
            f"[2:a]volume={config.BGM_VOLUME}[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[audio];"
            f"[0:v]{sub_filter}[v]",
            "-map", "[v]",
            "-map", "[audio]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_path),
        ]
    else:
        # BGM 없이 합성
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-filter_complex",
            f"[0:v]{sub_filter}[v];"
            f"[1:a]volume=1.0[audio]",
            "-map", "[v]",
            "-map", "[audio]",
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
        raise RuntimeError(f"최종 합성 오류:\n{stderr[-800:]}")

    # LUT 적용 (선택사항)
    if lut_name:
        lut_output = output_path.parent / f"final_lut_{output_path.name}"
        lut_result = _apply_lut(output_path, lut_output, lut_name)
        if lut_result != output_path:
            import shutil
            shutil.move(str(lut_output), str(output_path))

    print(f"  [완성] {output_path}")
    return output_path
