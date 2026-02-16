from __future__ import annotations


def split_for_discord(text: str, limit: int) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ["(sem resposta do Codex)"]
    if len(normalized) <= limit:
        return [normalized]

    chunks: list[str] = []
    remaining = normalized

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_index = remaining.rfind("\n", 0, limit + 1)
        if split_index < limit // 2:
            split_index = remaining.rfind(" ", 0, limit + 1)
        if split_index < limit // 2:
            split_index = limit

        chunk = remaining[:split_index].rstrip()
        if not chunk:
            chunk = remaining[:limit]
            split_index = limit

        chunks.append(chunk)
        remaining = remaining[split_index:].lstrip("\n ")

    return chunks
