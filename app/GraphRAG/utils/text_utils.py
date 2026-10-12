import re


def clean_text(raw_text: str) -> str:
    if raw_text is None:
        raise ValueError("Text must not be None.")
    cleaned = re.sub(r"\s+", " ", raw_text.strip())
    return cleaned.strip()


def chunk_text(text: str, chunk_size: int = 1800, overlap: int = 180) -> list[str]:
    if not text or not text.strip():
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if overlap < 0:
        raise ValueError("chunk_overlap must be non-negative.")
    if overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size.")

    cleaned = clean_text(text)
    if len(cleaned) <= chunk_size:
        if len(cleaned) <= 1:
            return [cleaned]
        split_at = max(1, len(cleaned) // 2)
        left = cleaned[:split_at].strip()
        right = cleaned[split_at:].strip()
        return [chunk for chunk in (left, right) if chunk]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            sentinel = max(cleaned.rfind(". ", start + max(1, chunk_size // 2), end), cleaned.rfind("; ", start + max(1, chunk_size // 2), end), cleaned.rfind("\n", start + max(1, chunk_size // 2), end), cleaned.rfind(" ", start + max(1, chunk_size // 2), end))
            if sentinel > start:
                end = sentinel + 1
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks if chunks else [cleaned]
