from __future__ import annotations
import math

def chunk_text(text: str, chunk_size: int = 600, overlap: float = 0.15) -> list[dict]:
    """
    Chunks text into smaller pieces while trying to preserve paragraph boundaries.
    """
    if not text:
        return []

    overlap_size = int(chunk_size * overlap)
    chunks = []
    chunk_index = 0
    start = 0
    text_len = len(text)

    # Simplified chunking: just split by size for now, trying to find spaces or newlines near the end
    while start < text_len:
        end = min(start + chunk_size, text_len)
        
        # If not at the end of the text, try to find a natural break
        if end < text_len:
            # Look for paragraph break
            natural_break = text.rfind('\n\n', start + chunk_size // 2, end)
            if natural_break == -1:
                # Look for sentence break
                natural_break = text.rfind('. ', start + chunk_size // 2, end)
            if natural_break == -1:
                # Look for word break
                natural_break = text.rfind(' ', start + chunk_size // 2, end)
                
            if natural_break != -1:
                end = natural_break + (1 if text[natural_break] == ' ' else 2)
                
        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            chunks.append({
                "text": chunk_text_str,
                "chunk_index": chunk_index,
                "start_char": start,
                "end_char": end
            })
            chunk_index += 1
            
        new_start = end - overlap_size
        if new_start <= start:
            start = end
        else:
            start = new_start

    return chunks
