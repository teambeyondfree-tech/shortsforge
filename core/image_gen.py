"""
이미지 생성 모듈
Gemini Imagen API → 장면별 이미지 생성
실패 시 Pollinations.ai (무료 폴백) 사용
"""
import time
import requests
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types
import config


def _is_429(e: Exception) -> bool:
    msg = str(e)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()


def _generate_imagen(prompt: str, output_path: Path, max_retries: int = 4) -> bool:
    """Gemini Imagen으로 이미지 생성 — 429 발생 시 최대 4회 재시도"""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    for attempt in range(max_retries):
        try:
            response = client.models.generate_images(
                model=config.MODEL_IMAGE,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="9:16",
                ),
            )
            image_bytes = response.generated_images[0].image.image_bytes
            output_path.write_bytes(image_bytes)
            return True
        except Exception as e:
            if _is_429(e) and attempt < max_retries - 1:
                wait = 30 * (attempt + 1)   # 30s → 60s → 90s
                print(f"    [Imagen 429] 한도 초과 — {wait}초 대기 후 재시도 ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                print(f"    [Imagen 실패] {e} → Pollinations 폴백")
                return False
    return False


def _generate_pollinations(prompt: str, output_path: Path) -> bool:
    """Pollinations.ai 폴백 (완전 무료, API 키 불필요)"""
    try:
        import urllib.parse
        encoded = urllib.parse.quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={config.VIDEO_W}&height={config.VIDEO_H}"
            f"&nologo=true&enhance=true"
        )
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    [Pollinations 실패] {e}")
        return False


def _resize_to_video(image_path: Path):
    """생성된 이미지를 영상 해상도(1080x1920)로 리사이즈"""
    img = Image.open(image_path).convert("RGB")
    if img.size != (config.VIDEO_W, config.VIDEO_H):
        img = img.resize((config.VIDEO_W, config.VIDEO_H), Image.LANCZOS)
        img.save(image_path, "PNG")


def generate_scene_image(prompt: str, scene_id: int, job_dir: Path) -> Path:
    """
    장면 하나의 이미지 생성.
    Imagen 실패 시 Pollinations 자동 폴백.
    """
    output_path = job_dir / f"scene_{scene_id:02d}.png"
    print(f"  이미지 생성 중... 장면 {scene_id}")

    if _generate_imagen(prompt, output_path):
        _resize_to_video(output_path)
        return output_path

    time.sleep(2)
    if _generate_pollinations(prompt, output_path):
        _resize_to_video(output_path)
        return output_path

    raise RuntimeError(f"장면 {scene_id} 이미지 생성 실패")


def generate_all_images(scene_prompts: list, job_dir: Path, max_workers: int = 1) -> list:
    """
    모든 장면 이미지 생성 (순차 처리 — Imagen 429 방지).
    장면 사이 3초 간격으로 API 부하 분산.
    """
    results = []
    for i, item in enumerate(scene_prompts):
        if i > 0:
            time.sleep(3)   # 장면 간 3초 간격
        image_path = generate_scene_image(
            prompt=item["prompt"],
            scene_id=item["scene_id"],
            job_dir=job_dir,
        )
        results.append({
            "scene_id":    item["scene_id"],
            "image_path":  image_path,
            "duration":    item["duration"],
            "motion":      item["motion"],
            "description": item.get("description", ""),
        })

    return results
