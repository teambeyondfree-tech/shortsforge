"""
장면별 이미지 프롬프트 생성 모듈
선택된 스타일 + 장면 정보 → Imagen용 프롬프트
후킹 장면(role=후킹 or id=1, duration=3)은 드라마틱 비주얼 강화
"""
from styles import STYLES

# 후킹 장면 전용 비주얼 수식어 — 시선을 강제로 잡는 구도/조명
_HOOK_VISUAL = (
    "extreme close-up dramatic shot, "
    "ultra high contrast lighting, "
    "cinematic tension, sharp focus on subject, "
    "dark vignette edges, "
    "visually striking and attention-grabbing, "
    "thumbnail-worthy composition"
)

# 장르별 후킹 장면 배경 강화
_GENRE_HOOK_BG = {
    "범죄":    "dark crime scene atmosphere, red and black tones, ominous shadows",
    "공포":    "eerie horror atmosphere, deep shadows, cold blue lighting, unsettling",
    "재테크":  "money and wealth visual, gold and green tones, aspirational",
    "교육":    "mind-blowing visual, bright spotlight, dramatic reveal",
    "자기계발": "powerful motivational scene, warm golden light, determined energy",
}


def build_image_prompt(scene: dict, style_key: str, genre: str = "") -> str:
    """장면 1개에 대한 이미지 생성 프롬프트 반환."""
    style = STYLES[style_key]

    base      = style["base_prompt"]
    character = style["character_template"]
    bg        = style["bg_style"]
    mood_map  = style["mood_prompts"]

    mood     = scene.get("mood", "설명")
    mood_str = mood_map.get(mood, mood_map.get("설명", ""))
    desc     = scene.get("description", "")

    is_hook = (scene.get("role") == "후킹") or (scene.get("id") == 1 and scene.get("duration", 99) <= 3)

    if is_hook:
        genre_hook_bg = _GENRE_HOOK_BG.get(genre, "dramatic atmospheric background, intense")
        prompt = (
            f"{base}, "
            f"{character}, "
            f"{desc}, "
            f"{_HOOK_VISUAL}, "
            f"{genre_hook_bg}, "
            f"{mood_str}, "
            "vertical composition 9:16, ultra high quality, 4K"
        )
    else:
        prompt = (
            f"{base}, "
            f"{character}, "
            f"{desc}, "
            f"{mood_str}, "
            f"{bg}, "
            "vertical composition 9:16, high quality, detailed"
        )

    return prompt


def build_all_prompts(scenes: list, style_key: str, genre: str = "") -> list:
    """모든 장면의 프롬프트 리스트 반환"""
    return [
        {
            "scene_id":    scene["id"],
            "prompt":      build_image_prompt(scene, style_key, genre=genre),
            "duration":    scene.get("duration", 10),
            "motion":      scene.get("motion", "zoom_in"),
            "description": scene.get("description", ""),
        }
        for scene in scenes
    ]
