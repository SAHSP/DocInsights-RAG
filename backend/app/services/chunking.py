"""
Chunking Service — Hierarchical Parent-Child Strategy
- Parent chunks: ~900 tokens, semantic/structural boundaries
- Child chunks: target 400 tokens, max 500, 20-token overlap
- Tokenizer (bge-large-en-v1.5 AutoTokenizer) is the ruler — word count is never used.
"""
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional

from transformers import AutoTokenizer

from app.core.config import settings
from app.services.extraction import ExtractedDocument, PageContent

logger = logging.getLogger(__name__)

# ── Tokenizer (loaded once, shared) ──────────────────────────────────────────
_tokenizer: Optional[AutoTokenizer] = None

def get_tokenizer() -> AutoTokenizer:
    global _tokenizer
    if _tokenizer is None:
        logger.info(f"Loading tokenizer: {settings.embedding_model}")
        _tokenizer = AutoTokenizer.from_pretrained(settings.embedding_model)
        logger.info("Tokenizer loaded.")
    return _tokenizer


def count_tokens(text: str) -> int:
    return len(get_tokenizer().encode(text, add_special_tokens=False))


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class ChildChunkData:
    parent_chunk_id: uuid.UUID
    file_id:         uuid.UUID
    page_number:     int
    child_number:    int           # position within parent (1-based, resets per parent)
    chunk_text:      str
    token_count:     int
    metadata:        dict = field(default_factory=dict)
    # Will be assigned after DB insert
    child_chunk_id:  uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class ParentChunkData:
    file_id:        uuid.UUID
    page_number:    int
    chunk_number:   int            # position within document (1-based)
    chunk_text:     str
    chunk_type:     str            # 'text' | 'table' | 'mixed'
    metadata:       dict = field(default_factory=dict)
    children:       list[ChildChunkData] = field(default_factory=list)
    # Will be assigned after DB insert
    parent_chunk_id: uuid.UUID = field(default_factory=uuid.uuid4)


# ── Child Chunk Splitter ──────────────────────────────────────────────────────

def split_into_children(
    parent_text: str,
    parent_chunk_id: uuid.UUID,
    file_id: uuid.UUID,
    page_number: int,
) -> list[ChildChunkData]:
    """
    Split a parent chunk text into child chunks using a sliding token window.
    - Target: settings.child_chunk_target_tokens (400)
    - Hard cap: settings.child_chunk_max_tokens (500)
    - Overlap: settings.child_chunk_overlap_tokens (20)

    The tokenizer measures exact token counts — no word-count approximation.
    """
    tokenizer  = get_tokenizer()
    target     = settings.child_chunk_target_tokens     # 400
    max_tokens = settings.child_chunk_max_tokens        # 500
    overlap    = settings.child_chunk_overlap_tokens    # 20
    stride     = target - overlap                       # 380

    all_tokens = tokenizer.encode(parent_text, add_special_tokens=False)

    # If parent fits in one child chunk, return as-is
    if len(all_tokens) <= max_tokens:
        return [
            ChildChunkData(
                parent_chunk_id=parent_chunk_id,
                file_id=file_id,
                page_number=page_number,
                child_number=1,
                chunk_text=tokenizer.decode(all_tokens, skip_special_tokens=True),
                token_count=len(all_tokens),
            )
        ]

    children: list[ChildChunkData] = []
    child_number = 1
    start = 0

    while start < len(all_tokens):
        end = min(start + target, len(all_tokens))
        window = all_tokens[start:end]
        chunk_text = tokenizer.decode(window, skip_special_tokens=True).strip()

        if chunk_text:
            children.append(
                ChildChunkData(
                    parent_chunk_id=parent_chunk_id,
                    file_id=file_id,
                    page_number=page_number,
                    child_number=child_number,
                    chunk_text=chunk_text,
                    token_count=len(window),
                )
            )
            child_number += 1

        if end == len(all_tokens):
            break
        start += stride

    return children


# ── Parent Chunk Builder ──────────────────────────────────────────────────────

def _build_content_blocks(page: PageContent) -> list[tuple[str, str]]:
    """
    Returns a list of (text, chunk_type) tuples from a page.
    Text blocks → 'text', table blocks → 'table'.
    """
    blocks: list[tuple[str, str]] = []
    for block in page.text_blocks:
        if block.strip():
            blocks.append((block.strip(), "text"))
    for table in page.table_blocks:
        if table.strip():
            blocks.append((table.strip(), "table"))
    return blocks


def chunk_document(extracted: ExtractedDocument) -> list[ParentChunkData]:
    """
    Main entry point. Takes an ExtractedDocument and returns a list of
    ParentChunkData, each containing its children (ChildChunkData).

    Parent chunking strategy:
    - Accumulate content blocks page by page
    - When accumulated token count reaches settings.parent_chunk_target_tokens (900),
      finalize the current parent and start a new one
    - Each parent is then split into child chunks via split_into_children()
    """
    file_id       = uuid.UUID(extracted.file_id)
    target_tokens = settings.parent_chunk_target_tokens   # 900
    parents: list[ParentChunkData] = []

    # Accumulation state
    current_lines:   list[str] = []
    current_tokens:  int       = 0
    current_page:    int       = 1
    current_types:   set[str]  = set()
    chunk_number:    int       = 1

    def finalize_parent() -> Optional[ParentChunkData]:
        nonlocal current_lines, current_tokens, current_types, chunk_number
        if not current_lines:
            return None

        parent_text = "\n\n".join(current_lines)
        chunk_type  = "mixed" if len(current_types) > 1 else (next(iter(current_types)) if current_types else "text")

        parent = ParentChunkData(
            file_id=file_id,
            page_number=current_page,
            chunk_number=chunk_number,
            chunk_text=parent_text,
            chunk_type=chunk_type,
            metadata={"source": extracted.filename},
        )

        # Build child chunks
        parent.children = split_into_children(
            parent_text=parent_text,
            parent_chunk_id=parent.parent_chunk_id,
            file_id=file_id,
            page_number=current_page,
        )

        # Reset accumulation
        current_lines  = []
        current_tokens = 0
        current_types  = set()
        chunk_number  += 1
        return parent

    for page in extracted.pages:
        blocks = _build_content_blocks(page)
        current_page = page.page_number

        for block_text, block_type in blocks:
            block_tokens = count_tokens(block_text)

            # If adding this block would overflow the parent target, finalize first
            if current_tokens + block_tokens > target_tokens and current_lines:
                parent = finalize_parent()
                if parent:
                    parents.append(parent)

            # If this single block is itself larger than target, add it as its own parent
            if block_tokens > target_tokens:
                # It will be split into multiple children by split_into_children
                parent = ParentChunkData(
                    file_id=file_id,
                    page_number=page.page_number,
                    chunk_number=chunk_number,
                    chunk_text=block_text,
                    chunk_type=block_type,
                    metadata={"source": extracted.filename},
                )
                parent.children = split_into_children(
                    parent_text=block_text,
                    parent_chunk_id=parent.parent_chunk_id,
                    file_id=file_id,
                    page_number=page.page_number,
                )
                chunk_number += 1
                parents.append(parent)
                continue

            # Accumulate
            current_lines.append(block_text)
            current_tokens += block_tokens
            current_types.add(block_type)

    # Flush remaining content
    parent = finalize_parent()
    if parent:
        parents.append(parent)

    total_children = sum(len(p.children) for p in parents)
    logger.info(
        f"[{extracted.filename}] Chunking complete: "
        f"{len(parents)} parent chunks, {total_children} child chunks."
    )
    return parents
