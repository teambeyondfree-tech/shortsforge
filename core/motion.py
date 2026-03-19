"""
영상 모션 모듈
① Ken Burns 효과 (기본, 무료 — ffmpeg zoompan)
② Runway Gen-3 Alpha Turbo (AI 영상, RUNWAY_API_KEY 필요)
"""
import subprocess
import os
import time
import base64
import requests
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


def _generate_clip_runway(image_path: Path, output_path: Path, duration: float, prompt: str = "") -> Path:
    """
    Runway Gen-3 Alpha Turbo: 이미지 → AI 영상 클립 생성.
    duration은 5초 또는 10초로 반올림 (Runway API 제한).
    Runway 실패 시 호출부에서 Ken Burns로 대체.
    """
    try:
        import runwayml
    except ImportError:
        raise RuntimeError("runwayml 패키지 없음. pip install runwayml")

    if not config.RUNWAY_API_KEY:
        raise RuntimeError("RUNWAY_API_KEY 없음")

    clip_duration = 10 if duration >= 7 else 5

    img_b64  = base64.b64encode(image_path.read_bytes()).decode()
    data_uri = f"data:image/png;base64,{img_b64}"

    client = runwayml.RunwayML(api_key=config.RUNWAY_API_KEY)
    print(f"    [Runway] 요청 중... ({clip_duration}초)")

    task = client.image_to_video.create(
        model="gen3a_turbo",
        prompt_image=data_uri,
        prompt_text=prompt or "smooth cinematic motion, vertical 9:16",
        duration=clip_duration,
        ratio="768:1280",
    )

    for _ in range(60):  # 최대 5분 대기
        task = client.tasks.retrieve(task.id)
        if task.status == "SUCCEEDED":
            break
        if task.status == "FAILED":
            raise RuntimeError(f"Runway 실패: {task.failure}")
        print(f"    [Runway] 처리 중... ({task.status})")
        time.sleep(5)
    else:
        raise RuntimeError("Runway 시간 초과")

    video_bytes = requests.get(task.output[0], timeout=120).content
    output_path.write_bytes(video_bytes)

    # 원하는 duration에 맞게 트림
    trimmed = output_path.with_suffix(".trim.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(output_path),
        "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(trimmed),
    ], capture_output=True)
    if trimmed.exists():
        trimmed.replace(output_path)

    return output_path


def apply_all_motion(scene_images: list, job_dir: Path, engine: str = "ken_burns") -> list:
    """
    모든 장면 이미지에 모션 적용.
    engine="ken_burns" → ffmpeg zoompan (기본, 무료)
    engine="runway"    → Runway Gen-3 Alpha Turbo (AI 영상, 유료)
    반환: [{"scene_id": 1, "clip_path": Path}, ...]
    """
    clips = []
    for item in scene_images:
        clip_path = job_dir / f"clip_{item['scene_id']:02d}.mp4"
        scene_id  = item["scene_id"]
        duration  = float(item["duration"])

        if engine == "runway":
            print(f"  [Runway] AI 영상 생성 중... 장면 {scene_id}")
            try:
                _generate_clip_runway(
                    image_path=item["image_path"],
                    output_path=clip_path,
                    duration=duration,
                    prompt=item.get("description", ""),
                )
            except Exception as e:
                print(f"    [Runway 실패 → Ken Burns 대체] {e}")
                apply_ken_burns(item["image_path"], clip_path, duration, item["motion"])
        else:
            print(f"  움직임 효과 적용 중... 장면 {scene_id} ({item['motion']})")
            apply_ken_burns(item["image_path"], clip_path, duration, item["motion"])

        clips.append({"scene_id": scene_id, "clip_path": clip_path})
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
