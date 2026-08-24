"""업로드된 .sol 파일 안전장치.

업로드는 바로 slither/solc subprocess 실행으로 이어지는 신뢰 안 된 입력이라,
subprocess 진입 전 최소한의 방어선(크기/확장자/경로 조작/기초 내용 확인)을
둔다. CPU/메모리 ulimit 같은 진짜 리소스 격리는 알려진 한계로 남긴다 —
CLAUDE.md 참고.
"""

from pathlib import Path

from fastapi import UploadFile

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2MB
_CHUNK_SIZE = 64 * 1024
_SANITY_KEYWORDS = ("pragma", "contract", "interface", "library")


class UploadTooLarge(Exception):
    pass


class InvalidUpload(Exception):
    pass


async def read_and_validate_upload(upload: UploadFile) -> bytes:
    """업로드를 청크 단위로 읽으며 크기를 검증하고, 내용까지 확인한 뒤 bytes로 반환한다.
    Content-Length 헤더만 믿지 않는다 — 청크 전송 시 없거나 조작될 수 있다."""
    filename = upload.filename or ""
    if not filename.lower().endswith(".sol"):
        raise InvalidUpload(f"'.sol' 파일만 업로드할 수 있습니다: {filename}")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(
                f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_BYTES // 1024 // 1024}MB)"
            )
        chunks.append(chunk)

    content = b"".join(chunks)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InvalidUpload("텍스트(UTF-8) 파일이 아닙니다 — 올바른 .sol 파일인지 확인하세요.") from e

    if not any(kw in text for kw in _SANITY_KEYWORDS):
        raise InvalidUpload(
            "Solidity 파일처럼 보이지 않습니다 (pragma/contract/interface/library가 없음)."
        )

    return content


def safe_filename(upload: UploadFile) -> str:
    """클라이언트가 준 파일명에서 경로 조작 요소(../ 등)를 제거한다."""
    return Path(upload.filename or "upload.sol").name
