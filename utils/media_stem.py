"""미디어 파일명 stem: 문장/이름에서 경로에 쓰지 않는 특수문자 제거."""
from __future__ import annotations

import re

_MEDIA_PATH_STRIP_RE = re.compile(r"[,，\?\？\s]+")


def media_path_stem(text: str) -> str:
    """경로 파일명 stem — `,` `，` `?` `？` 공백 등 제거 후 순수 문자만."""
    value = (text or "").strip()
    if not value:
        return ""
    return _MEDIA_PATH_STRIP_RE.sub("", value)
