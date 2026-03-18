"""
Ken Burns 효과 모듈
정적 이미지 → 줌/패닝 효과가 있는 영상 클립
"""
import subprocess
import os
from pathlib import Path
import config

# scoop 등으로 설치된 ffmpeg PATH 추가
_SCOOP_SHIMS = os.path.expanduser("~/scoop/shims")
if _SCOOP_SHIMS not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _SCOOP_SHIMS + os.pathsep + os.environ.get("PATH", "")

W   = config.VIDEO_W
H   = config.VIDEO_H
FPS = config.VIDEO_FPS


def _make_zoompan_filter(effect: str, duration: float) -> str:
    """FFmpeg zoompan 필터 문자열 반환"""
    d = int(duration * FPS)  # 총 프레임 수

    # 스케일된 이미지 크기 (W*2 x H*2)
    sw, sh = W * 2, H * 2
    # 줌 1.3일 때 출력창 크기
    vw = int(sw / 1.3)  # 가시 영역 폭
    vh = int(sh / 1.3)  # 가시 영역 높이
    # 패닝 가능 최대 범위
    px = sw - vw  # 가로 패닝 최대값
    py = sh - vh  # 세로 패닝 최대값
    # 프레임당 이동량 (d 프레임에 걸쳐 전체 범위 이동)
    step_x = px / d if d > 0 else 0
    step_y = py / d if d > 0 else 0

    filters = {
        "zoom_in": (
            f"scale={sw}:{sh},"
            f"zoompan=z=zoom+0.0012:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2):"
            f"d={d}:s={W}x{H}:fps={FPS}"
        ),
        "zoom_out": (
            f"scale={sw}:{sh},"
            f"zoompan=z=2-(zoom*0.0012):x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2):"
            f"d={d}:s={W}x{H}:fps={FPS}"
        ),
        "pan_right": (
            f"scale={sw}:{sh},"
            f"zoompan=z=1.3:x=time*{px}/{int(duration)}:y=ih/2-(ih/zoom/2):"
            f"d={d}:s={W}x{H}:fps={FPS}"
        ),
        "pan_left": (
            f"scale={sw}:{sh},"
            f"zoompan=z=1.3:x={px}-time*{px}/{int(duration)}:y=ih/2-(ih/zoom/2):"
            f"d={d}:s={W}x{H}:fps={FPS}"
        ),
        "pan_up": (
            f"scale={sw}:{sh},"
            f"zoompan=z=1.3:x=iw/2-(iw/zoom/2):y=time*{py}/{int(duration)}:"
            f"d={d}:s={W}x{H}:fps={FPS}"
        ),
        "shake": (
            f"scale={sw}:{sh},"
            f"zoompan=z=1.15:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2):"
            f"d={d}:s={W}x{H}:fps={FPS}"
        ),
    }
    return filters.get(effect, filters["zoom_in"])


def apply_ken_burns(image_path: Path, output_path: Path, duration: float, effect: str) -> Path:
    """
    이미지에 Ken Burns 효과 적용 → 영상 클립 생성
    """
    vf = _make_zoompan_filter(effect, duration)

    # 경로를 forward slash로 정규화 (Windows FFmpeg 호환)
    img_str = str(image_path).replace("\\", "/")
    out_str = str(output_path).replace("\\", "/")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", img_str,
        "-t", str(duration + 0.5),
        "-vf", vf,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        out_str,
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"FFmpeg 오류:\n{stderr[-600:]}")

    return output_path


def apply_all_motion(scene_images: list, job_dir: Path) -> list:
    """
    모든 장면 이미지에 Ken Burns 적용.
    반환: [{"scene_id": 1, "clip_path": Path}, ...]
    """
    clips = []
    for item in scene_images:
        clip_path = job_dir / f"clip_{item['scene_id']:02d}.mp4"
        print(f"  움직임 효과 적용 중... 장면 {item['scene_id']} ({item['motion']})")
        apply_ken_burns(
            image_path=item["image_path"],
            output_path=clip_path,
            duration=float(item["duration"]),
            effect=item["motion"],
        )
        clips.append({
            "scene_id": item["scene_id"],
            "clip_path": clip_path,
        })
    return clips


def concat_clips(clips: list, output_path: Path, crossfade_sec: float = 0.5) -> Path:
    """
    모든 클립을 크로스페이드로 연결.
    """
    if len(clips) == 1:
        import shutil
        shutil.copy(clips[0]["clip_path"], output_path)
        return output_path

    # concat demuxer 방식 (가장 안정적)
    list_file = output_path.parent / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{c['clip_path'].resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"클립 연결 오류:\n{result.stderr[-500:]}")

    return output_path
