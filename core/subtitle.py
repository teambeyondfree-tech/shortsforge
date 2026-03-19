"""
자막 생성 모듈 v2
ASS 파일(libass 의존) → drawtext 방식으로 변경.
폰트 파일을 직접 지정해 Streamlit Cloud / Windows 모두 정상 렌더링.
"""
import wave
from pathlib import Path
import config


def _get_audio_duration(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def _group_words(words: list, chars_per_line: int = 10) -> list:
    """어절을 한 줄에 표시할 그룹으로 묶기"""
    groups, cur, cur_len = [], [], 0
    for w in words:
        if cur_len + len(w) > chars_per_line and cur:
            groups.append(cur)
            cur, cur_len = [w], len(w)
        else:
            cur.append(w)
            cur_len += len(w)
    if cur:
        groups.append(cur)
    return groups


def generate_subtitle_data(
    narration: str,
    audio_path: Path,
    job_dir: Path,
) -> list:
    """
    나레이션 + 음성 길이 → 자막 세그먼트 생성 + 텍스트 파일 저장.

    반환: [{text, start, end, file}, ...]
    """
    duration = _get_audio_duration(audio_path)
    words = [w for w in narration.split() if w.strip()]
    if not words:
        return []

    # 음절 기준으로 단어별 타이밍 계산
    total_syllables = sum(len(w) for w in words)
    t_per_syl = duration / max(total_syllables, 1)

    timed = []
    cursor = 0.0
    for w in words:
        dur = len(w) * t_per_syl
        timed.append({"word": w, "start": cursor, "end": cursor + dur})
        cursor += dur

    # 2-3 어절씩 그룹화
    groups = _group_words(words, chars_per_line=11)

    segments = []
    word_idx = 0
    for group in groups:
        g_start = timed[word_idx]["start"]
        g_end   = timed[word_idx + len(group) - 1]["end"]
        text    = " ".join(group)

        # 텍스트를 파일로 저장 (한국어 커맨드라인 인코딩 이슈 회피)
        seg_file = job_dir / f"sub_{len(segments):03d}.txt"
        seg_file.write_text(text, encoding="utf-8")

        segments.append({
            "text":  text,
            "start": round(g_start, 3),
            "end":   round(g_end, 3),
            "file":  seg_file,
        })
        word_idx += len(group)

    return segments


def generate_subtitles(audio_path: Path, output_path: Path, narration: str) -> Path:
    """하위 호환용 — pipeline.py가 이 함수를 호출하므로 유지."""
    # job_dir = output_path 부모 폴더
    segs = generate_subtitle_data(narration, audio_path, output_path.parent)
    # 세그먼트 정보를 output_path에 JSON으로 저장 (compose에서 읽음)
    import json
    data = [{"text": s["text"], "start": s["start"], "end": s["end"],
             "file": str(s["file"])} for s in segs]
    output_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return output_path
