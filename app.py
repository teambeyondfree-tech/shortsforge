"""
ShortsForge — AI 콘텐츠 생성기
유튜브 쇼츠 | 인스타 캐러셀 | 인스타 릴스
실행: streamlit run app.py
"""
import os
import streamlit as st

# Streamlit Cloud secrets → 환경변수로 먼저 주입 (config.py import 전에)
try:
    if "GEMINI_API_KEY" in st.secrets:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass

from pathlib import Path
from styles import STYLES
from core.voice import VOICES
from core.script import INSTA_GENRE_SYSTEM
from instagram.carousel_script import CAROUSEL_GENRES
import config

# ───────────────────────────────────────────
# 페이지 설정
# ───────────────────────────────────────────
st.set_page_config(
    page_title="ShortsForge",
    page_icon="🎬",
    layout="centered",
)

st.markdown("""
<style>
    .main { max-width: 700px; margin: auto; }
    .stButton button {
        width: 100%;
        height: 3.2rem;
        font-size: 1.15rem;
        font-weight: bold;
        color: white;
        border: none;
        border-radius: 12px;
    }
    .stButton button:hover { opacity: 0.85; }
    div[data-testid="stTabs"] button {
        font-size: 1rem;
        font-weight: bold;
        padding: 0.5rem 1.2rem;
    }
</style>
""", unsafe_allow_html=True)

# ───────────────────────────────────────────
# 헤더
# ───────────────────────────────────────────
st.title("🎬 ShortsForge")
st.caption("AI가 만드는 유튜브 쇼츠 · 인스타 캐러셀 · 인스타 릴스")
st.divider()

# ───────────────────────────────────────────
# API 키 확인
# ───────────────────────────────────────────
if not config.GEMINI_API_KEY:
    st.error("⚠️ Gemini API 키가 없습니다. `.env` 파일에 `GEMINI_API_KEY=...` 를 추가하세요.")
    st.stop()

# ───────────────────────────────────────────
# 탭 UI
# ───────────────────────────────────────────
tab_shorts, tab_carousel, tab_reels = st.tabs([
    "🎬 유튜브 쇼츠",
    "📸 인스타 캐러셀",
    "🎥 인스타 릴스",
])


# ═══════════════════════════════════════════
# TAB 1 — 유튜브 쇼츠 (기존 기능)
# ═══════════════════════════════════════════
with tab_shorts:
    st.subheader("유튜브 쇼츠 생성")
    st.caption("주제를 입력하면 AI가 스크립트 → 이미지 → 음성 → 영상을 자동 생성합니다.")

    col1, col2 = st.columns(2)
    with col1:
        shorts_genre = st.selectbox(
            "장르",
            options=["재테크", "범죄", "공포", "교육", "자기계발"],
            key="shorts_genre",
        )
    with col2:
        shorts_style = st.selectbox(
            "스타일",
            options=list(STYLES.keys()),
            key="shorts_style",
        )

    shorts_topic = st.text_input(
        "주제 또는 키워드",
        placeholder="예: 전세 사기 예방법, 한국 실제 귀신 사건, 재테크 30대 필수 지식",
        max_chars=100,
        key="shorts_topic",
    )

    col3, col4 = st.columns(2)
    with col3:
        shorts_voice = st.selectbox(
            "목소리",
            options=list(VOICES.keys()),
            format_func=lambda k: f"{k} — {VOICES[k]}",
            key="shorts_voice",
        )
    with col4:
        shorts_duration = st.selectbox(
            "영상 길이",
            options=[30, 45, 60],
            index=2,
            format_func=lambda x: f"{x}초",
            key="shorts_duration",
        )

    st.markdown("")
    if st.button("🚀 쇼츠 만들기", disabled=not shorts_topic.strip(), key="btn_shorts",
                 help="클릭하면 AI가 자동으로 영상을 만들어줍니다"):

        status   = st.empty()
        progress = st.progress(0)
        log_area = st.empty()
        logs     = []

        def on_progress_shorts(msg: str, pct: float):
            logs.append(msg)
            status.markdown(f"**{msg}**")
            progress.progress(min(pct, 1.0))
            log_area.text("\n".join(f"  ✓ {l}" for l in logs[:-1]) + f"\n→ {logs[-1]}")

        try:
            from core.pipeline import run as run_pipeline

            output_path = run_pipeline(
                topic=shorts_topic.strip(),
                genre=shorts_genre,
                style=shorts_style,
                voice_name=shorts_voice,
                duration=shorts_duration,
                progress_cb=on_progress_shorts,
            )

            progress.progress(1.0)
            status.markdown("**✅ 완성!**")
            st.success("영상이 만들어졌습니다!")

            with open(output_path, "rb") as f:
                video_bytes = f.read()

            col_dl, col_pv = st.columns(2)
            with col_dl:
                st.download_button(
                    label="⬇️ 다운로드",
                    data=video_bytes,
                    file_name=output_path.name,
                    mime="video/mp4",
                    use_container_width=True,
                )
            with col_pv:
                if st.button("▶️ 미리보기", use_container_width=True, key="pv_shorts"):
                    st.video(str(output_path))

            st.info(f"저장 위치: `{output_path}`")

        except Exception as e:
            progress.empty()
            st.error(f"오류 발생: {e}")
            with st.expander("오류 상세"):
                import traceback
                st.code(traceback.format_exc())


# ═══════════════════════════════════════════
# TAB 2 — 인스타그램 캐러셀
# ═══════════════════════════════════════════
with tab_carousel:
    st.subheader("인스타그램 캐러셀 생성")
    st.caption("후킹 표지 + 핵심 슬라이드 + CTA — ZIP으로 다운로드 후 인스타에 업로드하세요.")

    col1, col2 = st.columns(2)
    with col1:
        carousel_genre = st.selectbox(
            "카테고리",
            options=list(CAROUSEL_GENRES.keys()),
            key="carousel_genre",
        )
    with col2:
        carousel_slides = st.selectbox(
            "슬라이드 수",
            options=[5, 7, 10],
            index=1,
            format_func=lambda x: f"{x}장",
            key="carousel_slides",
        )

    carousel_topic = st.text_input(
        "주제 또는 키워드",
        placeholder="예: 직장인 재테크 5가지, 아침 루틴으로 인생이 바뀐다, 창업 전 알아야 할 것들",
        max_chars=100,
        key="carousel_topic",
    )

    st.markdown("")
    if st.button("📸 캐러셀 만들기", disabled=not carousel_topic.strip(), key="btn_carousel"):

        status   = st.empty()
        progress = st.progress(0)
        log_area = st.empty()
        logs     = []

        def on_progress_carousel(msg: str, pct: float):
            logs.append(msg)
            status.markdown(f"**{msg}**")
            progress.progress(min(pct, 1.0))
            log_area.text("\n".join(f"  ✓ {l}" for l in logs[:-1]) + f"\n→ {logs[-1]}")

        try:
            from instagram.carousel_pipeline import run as run_carousel

            zip_path, script_data = run_carousel(
                topic=carousel_topic.strip(),
                genre=carousel_genre,
                slide_count=carousel_slides,
                progress_cb=on_progress_carousel,
            )

            progress.progress(1.0)
            status.markdown("**✅ 캐러셀 완성!**")
            st.success(f"{carousel_slides}장 슬라이드가 완성됐습니다!")

            with open(zip_path, "rb") as f:
                zip_bytes = f.read()

            st.download_button(
                label="⬇️ 슬라이드 ZIP 다운로드",
                data=zip_bytes,
                file_name=zip_path.name,
                mime="application/zip",
                use_container_width=True,
            )

            # 캡션 + 해시태그 복사용 표시
            with st.expander("📋 인스타 캡션 & 해시태그 (복사해서 사용)", expanded=True):
                caption   = script_data.get("caption", "")
                hashtags  = " ".join(script_data.get("hashtags", []))
                full_text = f"{caption}\n\n{hashtags}"
                st.text_area("캡션 + 해시태그", value=full_text, height=160, key="caption_out")

            # 슬라이드 미리보기
            with st.expander("🖼️ 슬라이드 내용 미리보기"):
                for slide in script_data.get("slides", []):
                    s_type = slide.get("type", "content")
                    icon   = {"cover": "🎯", "content": "📌", "cta": "🔖"}.get(s_type, "📌")
                    st.markdown(f"**{icon} 슬라이드 {slide['id']}** — {slide.get('heading', '')}")
                    if slide.get("body"):
                        st.caption(slide["body"])

            st.info(f"저장 위치: `{zip_path}`")

        except Exception as e:
            progress.empty()
            st.error(f"오류 발생: {e}")
            with st.expander("오류 상세"):
                import traceback
                st.code(traceback.format_exc())


# ═══════════════════════════════════════════
# TAB 3 — 인스타그램 릴스
# ═══════════════════════════════════════════
with tab_reels:
    st.subheader("인스타그램 릴스 생성")
    st.caption("인스타 감성 후킹 + 짧고 임팩트 있는 릴스 — 9:16 MP4로 바로 업로드 가능합니다.")

    insta_genre_labels = {
        "인스타_재테크": "재테크/금융",
        "인스타_자기계발": "자기계발/동기",
        "인스타_라이프": "라이프스타일",
        "인스타_정보": "정보/지식",
        "인스타_비즈": "비즈니스",
    }

    col1, col2 = st.columns(2)
    with col1:
        reels_genre_label = st.selectbox(
            "카테고리",
            options=list(insta_genre_labels.values()),
            key="reels_genre",
        )
        reels_genre_key = {v: k for k, v in insta_genre_labels.items()}[reels_genre_label]

    with col2:
        reels_style = st.selectbox(
            "비주얼 스타일",
            options=list(STYLES.keys()),
            key="reels_style",
        )

    reels_topic = st.text_input(
        "주제 또는 키워드",
        placeholder="예: 월 100만원 더 버는 법, 아침 30분이 하루를 바꾼다, 직장인 투잡 현실",
        max_chars=100,
        key="reels_topic",
    )

    col3, col4 = st.columns(2)
    with col3:
        reels_voice = st.selectbox(
            "목소리",
            options=list(VOICES.keys()),
            format_func=lambda k: f"{k} — {VOICES[k]}",
            key="reels_voice",
        )
    with col4:
        reels_duration = st.selectbox(
            "릴스 길이",
            options=[15, 30],
            index=1,
            format_func=lambda x: f"{x}초",
            key="reels_duration",
        )

    st.markdown("")
    if st.button("🎥 릴스 만들기", disabled=not reels_topic.strip(), key="btn_reels"):

        status   = st.empty()
        progress = st.progress(0)
        log_area = st.empty()
        logs     = []

        def on_progress_reels(msg: str, pct: float):
            logs.append(msg)
            status.markdown(f"**{msg}**")
            progress.progress(min(pct, 1.0))
            log_area.text("\n".join(f"  ✓ {l}" for l in logs[:-1]) + f"\n→ {logs[-1]}")

        try:
            from core.pipeline import run as run_pipeline

            output_path = run_pipeline(
                topic=reels_topic.strip(),
                genre=reels_genre_key,
                style=reels_style,
                voice_name=reels_voice,
                duration=reels_duration,
                progress_cb=on_progress_reels,
            )

            progress.progress(1.0)
            status.markdown("**✅ 릴스 완성!**")
            st.success("릴스 영상이 완성됐습니다!")

            with open(output_path, "rb") as f:
                video_bytes = f.read()

            col_dl, col_pv = st.columns(2)
            with col_dl:
                st.download_button(
                    label="⬇️ 다운로드",
                    data=video_bytes,
                    file_name=output_path.name,
                    mime="video/mp4",
                    use_container_width=True,
                )
            with col_pv:
                if st.button("▶️ 미리보기", use_container_width=True, key="pv_reels"):
                    st.video(str(output_path))

            st.info(f"저장 위치: `{output_path}`")

        except Exception as e:
            progress.empty()
            st.error(f"오류 발생: {e}")
            with st.expander("오류 상세"):
                import traceback
                st.code(traceback.format_exc())


# ───────────────────────────────────────────
# 사이드바
# ───────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

    st.markdown("**API 상태**")
    if config.GEMINI_API_KEY:
        st.success("Gemini API 연결됨")
    else:
        st.error("Gemini API 키 없음")

    st.divider()
    st.markdown("**무료 한도 (일별)**")
    st.markdown("""
    - 스크립트 생성: 1,500회
    - 음성 합성: 250회
    - 이미지 생성: 500장
    """)

    st.divider()
    st.markdown("**완성 파일 위치**")
    st.code(str(config.OUTPUT_DIR))

    st.divider()
    st.markdown("**기능 안내**")
    st.markdown("""
    🎬 **쇼츠**: 유튜브 최적화 세로 영상
    📸 **캐러셀**: 인스타 슬라이드 이미지 ZIP
    🎥 **릴스**: 인스타 후킹 스타일 세로 영상
    """)
