"""
자막 생성 모듈 v3
① Whisper (faster-whisper) — 실제 음성 기반 정확한 타이밍 (권장)
② 음절 타이밍 — Whisper 불가 시 폴백
"""
import json
import wave
from pathlib import Path
import config

# Whisper 모델 캐시 (프로세스 내 1회만 로딩)
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("  [Whisper] 모델 로딩 중... (최초 1회, 이후 캐시)")
        # base 모델: 한국어 정확도 좋음, CPU에서 ~10초 내 처리
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        print("  [Whisper] 모델 로딩 완료")
    return _whisper_model


def _get_audio_duration(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def _group_timed_words(words: list, chars_per_line: int = 11) -> list[list]:
    """단어 목록을 한 줄 표시 그룹으로 묶기"""
    groups, cur, cur_len = [], [], 0
    for w in words:
        text = w["word"]
        if cur_len + len(text) > chars_per_line and cur:
            groups.append(cur)
            cur, cur_len = [w], len(text)
        else:
            cur.append(w)
            cur_len += len(text)
    if cur:
        groups.append(cur)
    return groups


def _generate_with_whisper(audio_path: Path, job_dir: Path) -> list:
    """Whisper로 실제 음성 타이밍 추출 → 자막 세그먼트 생성"""
    model = _get_whisper_model()

    print("  [Whisper] 음성 분석 중...")
    segments_iter, _ = model.transcribe(
        str(audio_path),
        language="ko",
        word_timestamps=True,
        vad_filter=True,          # 무음 구간 필터
        vad_parameters={"min_silence_duration_ms": 200},
    )

    # 단어별 타이밍 수집
    words = []
    for seg in segments_iter:
        if seg.words:
            for w in seg.words:
                clean = w.word.strip()
                if clean:
                    words.append({"word": clean, "start": w.start, "end": w.end})

    if not words:
        raise ValueError("Whisper가 단어를 인식하지 못했습니다")

    print(f"  [Whisper] 단어 {len(words)}개 인식 완료")

    # 2-3어절씩 그룹화
    groups = _group_timed_words(words, chars_per_line=11)

    segments_out = []
    for group in groups:
        text  = " ".join(w["word"] for w in group)
        start = group[0]["start"]
        end   = group[-1]["end"]

        seg_file = job_dir / f"sub_{len(segments_out):03d}.txt"
        seg_file.write_text(text, encoding="utf-8")

        segments_out.append({
            "text":  text,
            "start": round(start, 3),
            "end":   round(end + 0.05, 3),  # 약간 여유
            "file":  seg_file,
        })

    return segments_out


def _generate_syllable_based(narration: str, audio_path: Path, job_dir: Path) -> list:
    """폴백: 음절 수 기반 타이밍 계산"""
    duration = _get_audio_duration(audio_path)
    words = [w for w in narration.split() if w.strip()]
    if not words:
        return []

    total_syllables = sum(len(w) for w in words)
    t_per_syl = duration / max(total_syllables, 1)

    timed = []
    cursor = 0.0
    for w in words:
        dur = len(w) * t_per_syl
        timed.append({"word": w, "start": cursor, "end": cursor + dur})
        cursor += dur

    groups, cur, cur_len = [], [], 0
    for w in words:
        if cur_len + len(w) > 11 and cur:
            groups.append(cur)
            cur, cur_len = [w], len(w)
        else:
            cur.append(w)
            cur_len += len(w)
    if cur:
        groups.append(cur)

    segments, word_idx = [], 0
    for group in groups:
        g_start = timed[word_idx]["start"]
        g_end   = timed[word_idx + len(group) - 1]["end"]
        text    = " ".join(group)

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


def generate_subtitle_data(narration: str, audio_path: Path, job_dir: Path) -> list:
    """
    자막 세그먼트 생성.
    Whisper 우선, 실패 시 음절 타이밍으로 폴백.
    """
    try:
        return _generate_with_whisper(audio_path, job_dir)
    except Exception as e:
        print(f"  [Whisper 실패 → 음절 타이밍 사용] {e}")
        return _generate_syllable_based(narration, audio_path, job_dir)


def generate_subtitles(audio_path: Path, output_path: Path, narration: str) -> Path:
    """pipeline.py 호환용"""
    segs = generate_subtitle_data(narration, audio_path, output_path.parent)
    data = [{"text": s["text"], "start": s["start"], "end": s["end"],
             "file": str(s["file"])} for s in segs]
    output_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return output_path
