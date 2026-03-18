"""
자막 생성 모듈
나레이션 텍스트 + 음성 길이 → 어절 단위 카라오케 스타일 ASS 자막
"""
import wave
from pathlib import Path
import config


def _get_audio_duration(audio_path: Path) -> float:
    """WAV 파일의 재생 길이(초) 반환"""
    with wave.open(str(audio_path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def _seconds_to_ass_time(sec: float) -> str:
    """초 → ASS 타임코드 (H:MM:SS.cc)"""
    h  = int(sec // 3600)
    m  = int((sec % 3600) // 60)
    s  = int(sec % 60)
    cs = int((sec - int(sec)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _make_ass_header(font: str, font_size: int) -> str:
    """ASS 파일 헤더 (스타일 정의)"""
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.VIDEO_W}
PlayResY: {config.VIDEO_H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,Strikeout,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,{config.SUBTITLE_OUTLINE_W},0,2,40,40,120,1
Style: Highlight,{font},{font_size},&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,{config.SUBTITLE_OUTLINE_W},0,2,40,40,120,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def _split_to_words(narration: str) -> list[str]:
    """나레이션을 어절(공백 기준) 단위로 분리, 빈 문자열 제거"""
    return [w for w in narration.split() if w.strip()]


def _group_words(words: list[str], max_chars: int = 14) -> list[list[str]]:
    """어절들을 한 줄에 표시할 그룹으로 묶기 (max_chars 글자 이하)"""
    groups = []
    current = []
    current_len = 0

    for word in words:
        word_len = len(word)
        if current_len + word_len > max_chars and current:
            groups.append(current)
            current = [word]
            current_len = word_len
        else:
            current.append(word)
            current_len += word_len

    if current:
        groups.append(current)

    return groups


def generate_subtitles(audio_path: Path, output_path: Path, narration: str) -> Path:
    """
    나레이션 텍스트를 음성 길이에 맞춰 어절 단위 카라오케 ASS 자막으로 생성.
    """
    print("  자막 생성 중... (나레이션 텍스트 기반)")

    duration = _get_audio_duration(audio_path)
    words = _split_to_words(narration)

    if not words:
        # 빈 나레이션이면 빈 자막 파일만 생성
        header = _make_ass_header(config.SUBTITLE_FONT, config.SUBTITLE_FONT_SIZE)
        output_path.write_text(header, encoding="utf-8")
        return output_path

    # 총 음절 수 기준으로 어절별 시간 배분
    total_syllables = sum(len(w) for w in words)
    time_per_syllable = duration / total_syllables if total_syllables > 0 else 0.1

    # 어절별 타임스탬프 계산
    timed_words = []
    cursor = 0.0
    for word in words:
        word_dur = len(word) * time_per_syllable
        timed_words.append({
            "word": word,
            "start": cursor,
            "end": cursor + word_dur,
        })
        cursor += word_dur

    # 그룹으로 묶어서 카라오케 자막 생성
    word_texts = [w["word"] for w in timed_words]
    groups_text = _group_words(word_texts, max_chars=14)

    header = _make_ass_header(config.SUBTITLE_FONT, config.SUBTITLE_FONT_SIZE)
    lines = [header]

    idx = 0
    for group in groups_text:
        if not group:
            continue

        g_start = timed_words[idx]["start"]
        g_end = timed_words[idx + len(group) - 1]["end"]
        s = _seconds_to_ass_time(g_start)
        e = _seconds_to_ass_time(g_end)

        # 카라오케 태그: {\k<centiseconds>}어절
        kara_parts = []
        for i, word in enumerate(group):
            tw = timed_words[idx + i]
            dur_cs = max(1, int((tw["end"] - tw["start"]) * 100))
            kara_parts.append(f"{{\\k{dur_cs}}}{word}")

        text = " ".join(kara_parts)
        lines.append(f"Dialogue: 0,{s},{e},Default,,0,0,0,Karaoke,{text}")
        idx += len(group)

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
