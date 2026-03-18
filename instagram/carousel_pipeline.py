"""
인스타그램 캐러셀 파이프라인
script → render → zip
"""
import shutil
import time
import uuid
from pathlib import Path
from typing import Callable

import config
from instagram.carousel_script import generate_carousel_script
from instagram.carousel_render import render_all_slides, pack_zip


def run(
    topic: str,
    genre: str,
    slide_count: int = 7,
    progress_cb: Callable[[str, float], None] | None = None,
) -> tuple[Path, dict]:
    """
    캐러셀 파이프라인 실행.

    반환: (zip_path, script_data)
    - zip_path: 슬라이드 이미지 ZIP 파일 경로
    - script_data: 캡션, 해시태그 포함 스크립트 dict
    """
    def progress(msg: str, pct: float):
        print(f"[{int(pct*100):3d}%] {msg}")
        if progress_cb:
            progress_cb(msg, pct)

    job_id  = f"carousel_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    job_dir = config.TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. 스크립트 생성
        progress("캐러셀 스크립트 생성 중...", 0.05)
        script_data = generate_carousel_script(topic, genre, slide_count)
        slides = script_data.get("slides", [])
        title  = script_data.get("title", topic)
        print(f"  제목: {title} / 슬라이드: {len(slides)}개")

        # 2. 슬라이드 렌더링
        progress("슬라이드 이미지 렌더링 중... (AI 배경 생성 중)", 0.30)
        slide_paths = render_all_slides(slides, job_dir, genre=genre)
        progress(f"{len(slide_paths)}개 슬라이드 완성", 0.85)

        # 3. ZIP 패키징
        progress("ZIP 파일 생성 중...", 0.92)
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip()
        zip_path   = config.OUTPUT_DIR / f"{safe_title}_{job_id[:8]}.zip"
        pack_zip(slide_paths, zip_path)

        progress("완성!", 1.0)
        return zip_path, script_data

    finally:
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass
