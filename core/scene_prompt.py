"""
장면별 이미지 프롬프트 생성 모듈
선택된 스타일 + 장면 정보 → Imagen용 프롬프트
"""
from styles import STYLES


def build_image_prompt(scene: dict, style_key: str) -> str:
    """
    장면 1개에 대한 이미지 생성 프롬프트 반환.
    """
    style = STYLES[style_key]

    base      = style["base_prompt"]
    character = style["character_template"]
    bg        = style["bg_style"]
    mood_map  = style["mood_prompts"]

    mood     = scene.get("mood", "설명")
    mood_str = mood_map.get(mood, mood_map.get("설명", ""))
    desc     = scene.get("description", "")

    prompt = (
        f"{base}, "
        f"{character}, "
        f"{desc}, "
        f"{mood_str}, "
        f"{bg}, "
        "vertical composition 9:16, high quality, detailed"
    )

    return prompt


def build_all_prompts(scenes: list, style_key: str) -> list:
    """모든 장면의 프롬프트 리스트 반환"""
    return [
        {
            "scene_id": scene["id"],
            "prompt": build_image_prompt(scene, style_key),
            "duration": scene.get("duration", 10),
            "motion": scene.get("motion", "zoom_in"),
        }
        for scene in scenes
    ]
