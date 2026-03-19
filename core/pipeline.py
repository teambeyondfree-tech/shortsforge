"""
전체 파이프라인 오케스트레이터
script → scene_prompt → image_gen → motion → voice → subtitle → compose
"""
import shutil
import time
import uuid
import sys
import os
from pathlib import Path
from typing import Callable

# scoop PATH 추가
_SCOOP_SHIMS = os.path.expanduser("~/scoop/shims")
if _SCOOP_SHIMS not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _SCOOP_SHIMS + os.pathsep + os.environ.get("PATH", "")

def _safe_print(msg: str):
    """Windows cp949 환경에서 이모지/특수문자 인코딩 오류 방지"""
    try:
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        pass

import config
from core import script as script_mod
from core import scene_prompt as prompt_mod
from core import image_gen as image_mod
from core import motion as motion_mod
from core import voice as voice_mod
from core import subtitle as subtitle_mod
from core import compose as compose_mod


def _adjust_durations(scenes: list, voice_duration: float) -> list:
    """
    TTS 실제 음성 길이에 맞춰 장면별 duration을 비례 조정.
    """
    total_script = sum(s["duration"] for s in scenes)
    if total_script <= 0:
        return scenes

    ratio = voice_duration / total_script
    for scene in scenes:
        scene["duration"] = round(scene["duration"] * ratio, 2)

    return scenes


def run(
    topic: str,
    genre: str,
    style: str,
    voice_name: str,
    duration: int = 60,
    progress_cb: Callable[[str, float], None] | None = None,
) -> Path:
    """
    전체 파이프라인 실행.

    progress_cb(message, progress_0_to_1) 형태로 진행 상황 콜백.
    최종 완성 mp4 경로 반환.
    """
    def progress(msg: str, pct: float):
        _safe_print(f"[{int(pct*100):3d}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    # 작업 폴더 생성
    job_id  = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    job_dir = config.TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── 1. 스크립트 생성
        progress("스크립트 생성 중...", 0.05)
        script_data   = script_mod.generate_script(topic, genre, duration)
        full_narration = script_mod.get_full_narration(script_data)
        title          = script_data.get("title", topic)
        scenes         = script_data["scenes"]
        _safe_print(f"  제목: {title} / 장면 수: {len(scenes)}")

        # ── 2. 음성 합성 (먼저 실행해서 실제 길이 측정)
        progress("음성 합성 중...", 0.12)
        audio_path = job_dir / "voice.wav"
        voice_mod.generate_voice(full_narration, voice_name, audio_path)
        voice_duration = voice_mod.get_voice_duration(audio_path)
        _safe_print(f"  음성 실제 길이: {voice_duration:.1f}초")

        # ── 3. 음성 길이에 맞춰 장면 duration 조정
        scenes = _adjust_durations(scenes, voice_duration)

        # ── 4. 장면별 이미지 프롬프트 생성
        progress("이미지 프롬프트 생성 중...", 0.18)
        scene_prompts = prompt_mod.build_all_prompts(scenes, style)

        # ── 5. 장면별 이미지 생성 (병렬)
        progress("이미지 생성 중...", 0.22)
        scene_images = image_mod.generate_all_images(scene_prompts, job_dir)

        # ── 6. Ken Burns 효과 적용 → 클립
        progress("영상 움직임 효과 적용 중...", 0.50)
        clips = motion_mod.apply_all_motion(scene_images, job_dir)

        # ── 7. 클립 연결
        progress("클립 연결 중...", 0.65)
        concat_path = job_dir / "concat.mp4"
        motion_mod.concat_clips(clips, concat_path)

        # ── 8. 자막 생성
        progress("자막 생성 중...", 0.78)
        subtitle_path = job_dir / "subtitle.json"
        subtitle_mod.generate_subtitles(audio_path, subtitle_path, full_narration)

        # ── 9. 최종 합성
        progress("최종 영상 합성 중...", 0.90)
        safe_title  = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip()
        output_path = config.OUTPUT_DIR / f"{safe_title}_{job_id[:8]}.mp4"
        compose_mod.compose_final(
            video_path=concat_path,
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
        )

        progress("완성!", 1.0)
        return output_path

    finally:
        # 작업 완료/실패 시 temp 폴더 정리
        try:
            shutil.rmtree(job_dir)
            _safe_print(f"  [정리] temp 폴더 삭제: {job_dir.name}")
        except Exception:
            pass
