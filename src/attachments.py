from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import discord


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}

AUDIO_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".oga",
    ".ogg",
    ".wav",
    ".webm",
    ".wma",
}

SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class DownloadedAttachment:
    original_name: str
    saved_path: Path
    size_bytes: int
    content_type: str
    is_image: bool
    is_audio: bool


@dataclass(frozen=True)
class AttachmentCollection:
    request_dir: Path
    downloaded: list[DownloadedAttachment]
    skipped: list[str]


def _sanitize_filename(filename: str, index: int) -> str:
    cleaned = SAFE_NAME_PATTERN.sub("_", filename.strip())
    if not cleaned:
        cleaned = f"attachment_{index}"
    return f"{index:02d}_{cleaned}"


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    return Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS


def _is_audio_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("audio/"):
        return True
    return Path(attachment.filename).suffix.lower() in AUDIO_EXTENSIONS


async def download_attachments(
    attachments: list[discord.Attachment],
    temp_root: Path,
    request_id: str,
    max_bytes: int,
) -> AttachmentCollection:
    request_dir = temp_root / request_id
    request_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[DownloadedAttachment] = []
    skipped: list[str] = []

    for index, attachment in enumerate(attachments, start=1):
        size = int(getattr(attachment, "size", 0) or 0)
        if size > max_bytes:
            skipped.append(
                f"{attachment.filename} (ignorado: {size} bytes > limite {max_bytes} bytes)"
            )
            continue

        safe_name = _sanitize_filename(attachment.filename, index)
        saved_path = request_dir / safe_name
        await attachment.save(saved_path)

        downloaded.append(
            DownloadedAttachment(
                original_name=attachment.filename,
                saved_path=saved_path,
                size_bytes=size,
                content_type=attachment.content_type or "",
                is_image=_is_image_attachment(attachment),
                is_audio=_is_audio_attachment(attachment),
            )
        )

    return AttachmentCollection(
        request_dir=request_dir,
        downloaded=downloaded,
        skipped=skipped,
    )


def cleanup_attachments(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
