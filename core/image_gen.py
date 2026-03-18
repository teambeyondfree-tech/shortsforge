"""
이미지 생성 모듈
Gemini Imagen API → 장면별 이미지 생성
실패 시 Pollinations.ai (무료 폴백) 사용
"""
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from google import genai
from google.genai import types
import config


def _generate_imagen(prompt: str, output_path: Path) -> bool:
    """Gemini Imagen 3으로 이미지 생성 (무료 500장/일)"""
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
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
        print(f"    [Imagen 실패] {e} → Pollinations 폴백 사용")
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

    # 1차: Gemini Imagen
    if _generate_imagen(prompt, output_path):
        _resize_to_video(output_path)
        return output_path

    # 2차: Pollinations 폴백
    time.sleep(1)
    if _generate_pollinations(prompt, output_path):
        _resize_to_video(output_path)
        return output_path

    raise RuntimeError(f"장면 {scene_id} 이미지 생성 실패")


def generate_all_images(scene_prompts: list, job_dir: Path, max_workers: int = 3) -> list:
    """
    모든 장면 이미지를 병렬 생성.
    반환: [{"scene_id": 1, "image_path": Path, "duration": 10, "motion": "zoom_in"}, ...]
    """
    results = []

    def _task(item):
        image_path = generate_scene_image(
            prompt=item["prompt"],
            scene_id=item["scene_id"],
            job_dir=job_dir,
        )
        return {
            "scene_id": item["scene_id"],
            "image_path": image_path,
            "duration": item["duration"],
            "motion": item["motion"],
        }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_task, item): item["scene_id"]
            for item in scene_prompts
        }
        for future in as_completed(futures):
            results.append(future.result())

    # scene_id 순서대로 정렬
    results.sort(key=lambda x: x["scene_id"])
    return results
