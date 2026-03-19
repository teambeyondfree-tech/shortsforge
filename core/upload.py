"""
YouTube 자동 업로드 모듈
Google OAuth2 + YouTube Data API v3
최초 1회: 브라우저 인증 → youtube_token.json 저장
이후: 저장된 토큰으로 자동 업로드
"""
from pathlib import Path
import config


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_credentials():
    """OAuth2 자격증명 반환 (토큰 자동 갱신)"""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        raise RuntimeError(
            "google-api-python-client, google-auth-oauthlib 패키지가 없습니다.\n"
            "pip install google-api-python-client google-auth-oauthlib"
        )

    token_file = config.YOUTUBE_TOKEN_FILE
    creds_file = config.YOUTUBE_CREDENTIALS_FILE

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_file.exists():
                raise FileNotFoundError(
                    f"YouTube 인증 파일이 없습니다.\n"
                    f"Google Cloud Console → OAuth2 클라이언트 ID → credentials.json 다운로드 후\n"
                    f"다음 경로에 놓으세요: {creds_file}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)

        token_file.write_text(creds.to_json())

    return creds


def get_youtube_service():
    """YouTube Data API 서비스 객체 반환"""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("google-api-python-client 패키지가 없습니다.")

    creds = _get_credentials()
    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str = "",
    tags: list | None = None,
    privacy: str = "private",   # private | unlisted | public
    category_id: str = "22",    # 22 = People & Blogs
) -> str:
    """
    YouTube에 영상 업로드.
    반환: 업로드된 영상 URL (https://www.youtube.com/watch?v=...)
    """
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise RuntimeError("google-api-python-client 패키지가 없습니다.")

    service = get_youtube_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"  [YouTube] 업로드 중... ({video_path.name})")
    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"    업로드 진행: {pct}%")

    video_id  = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"  [YouTube] 업로드 완료: {video_url}")
    return video_url


def is_authenticated() -> bool:
    """YouTube 인증 토큰이 유효한지 확인"""
    token_file = config.YOUTUBE_TOKEN_FILE
    if not token_file.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_file.write_text(creds.to_json())
        return creds.valid
    except Exception:
        return False
