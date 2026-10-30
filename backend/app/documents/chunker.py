"""Deterministic Markdown policy parser and section-aware chunker.

Parses YAML-style frontmatter (`doc_key`, `title`, `category`, `version`, `effective_date`),
tracks `<!-- page: N -->` markers and `## Section` headings, and splits large sections on
paragraph boundaries while keeping chunk identifiers (`{doc_key}#C{01..NN}`) reproducible.
"""

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import cast

from app.db.models import POLICY_CATEGORIES
from app.documents.schemas import ParsedChunk, ParsedPolicyDocument, PolicyCategory

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_PAGE_MARKER_RE = re.compile(r"^\s*<!--\s*page:\s*(\d+)\s*-->\s*$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
MAX_CHUNK_WORDS = 260


class DocumentParseError(ValueError):
    """Raised when a policy document is missing required frontmatter or content."""


def estimate_token_count(text: str) -> int:
    """Approximate token count (1.3 tokens per whitespace word, minimum 1)."""
    words = len(text.split())
    return max(1, round(words * 1.3))


def parse_policy_markdown(raw_text: str, filename: str) -> ParsedPolicyDocument:
    """Parse a Markdown policy document into metadata and deterministic section chunks."""
    normalized = raw_text.replace("\r\n", "\n").strip()
    checksum = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    fm_match = _FRONTMATTER_RE.match(normalized)
    if not fm_match:
        raise DocumentParseError(f"{filename}: missing YAML frontmatter block.")

    meta: dict[str, str] = {}
    for line in fm_match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise DocumentParseError(f"{filename}: malformed frontmatter line '{stripped}'.")
        key, val = stripped.split(":", 1)
        meta[key.strip()] = val.strip().strip("\"'")

    required_keys = ("doc_key", "title", "category", "version", "effective_date")
    for req in required_keys:
        if not meta.get(req):
            raise DocumentParseError(f"{filename}: missing required frontmatter field '{req}'.")

    category_raw = meta["category"]
    if category_raw not in POLICY_CATEGORIES:
        raise DocumentParseError(
            f"{filename}: invalid category '{category_raw}'. Must be one of {POLICY_CATEGORIES}."
        )
    category = cast(PolicyCategory, category_raw)

    try:
        effective_date = date.fromisoformat(meta["effective_date"])
    except ValueError as exc:
        raise DocumentParseError(
            f"{filename}: invalid effective_date '{meta['effective_date']}'."
        ) from exc

    doc_key = meta["doc_key"]
    title = meta["title"]
    version = meta["version"]

    body = normalized[fm_match.end() :]
    current_page = 1
    current_section = "Overview"
    section_blocks: list[tuple[str, int, list[str]]] = []
    current_lines: list[str] = []

    def _flush_section() -> None:
        nonlocal current_lines
        text_block = "\n".join(current_lines).strip()
        if text_block:
            section_blocks.append((current_section, current_page, text_block.split("\n\n")))
        current_lines = []

    for line in body.splitlines():
        page_match = _PAGE_MARKER_RE.match(line)
        if page_match:
            _flush_section()
            current_page = max(1, int(page_match.group(1)))
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            _flush_section()
            current_section = heading_match.group(1).strip()
            continue

        current_lines.append(line)

    _flush_section()

    if not section_blocks:
        raise DocumentParseError(f"{filename}: document contains no body sections.")

    chunks: list[ParsedChunk] = []
    chunk_idx = 0

    for sec_title, page_num, paragraphs in section_blocks:
        buffer: list[str] = []
        buffer_words = 0

        def _emit_chunk(sec: str, pg: int, paras: list[str]) -> None:
            nonlocal chunk_idx
            body_text = "\n\n".join(p.strip() for p in paras if p.strip())
            if not body_text:
                return
            chunk_idx_1based = chunk_idx + 1
            cid = f"{doc_key}#C{chunk_idx_1based:02d}"
            formatted_content = f"[{title} ({version}) — {sec}]\n{body_text}"
            chunks.append(
                ParsedChunk(
                    chunk_id=cid,
                    chunk_index=chunk_idx,
                    section_title=sec,
                    page_number=pg,
                    content=formatted_content,
                    token_count=estimate_token_count(formatted_content),
                )
            )
            chunk_idx += 1

        for para in paragraphs:
            clean_para = para.strip()
            if not clean_para:
                continue
            para_words = len(clean_para.split())
            if buffer and (buffer_words + para_words > MAX_CHUNK_WORDS):
                _emit_chunk(sec_title, page_num, buffer)
                buffer = [clean_para]
                buffer_words = para_words
            else:
                buffer.append(clean_para)
                buffer_words += para_words

        if buffer:
            _emit_chunk(sec_title, page_num, buffer)

    if not chunks:
        raise DocumentParseError(f"{filename}: produced zero chunks.")

    return ParsedPolicyDocument(
        doc_key=doc_key,
        title=title,
        category=category,
        version=version,
        effective_date=effective_date,
        filename=filename,
        checksum_sha256=checksum,
        chunks=chunks,
    )


def load_policy_corpus(directory: Path) -> list[ParsedPolicyDocument]:
    """Load and parse all `.md` policy documents in deterministic filename order."""
    if not directory.is_dir():
        raise DocumentParseError(f"Policy directory does not exist: {directory}")
    files = sorted(directory.glob("*.md"))
    if not files:
        raise DocumentParseError(f"No markdown policy files found in {directory}")
    seen_keys: set[str] = set()
    docs: list[ParsedPolicyDocument] = []
    for path in files:
        parsed = parse_policy_markdown(path.read_text(encoding="utf-8"), path.name)
        if parsed.doc_key in seen_keys:
            raise DocumentParseError(f"Duplicate doc_key '{parsed.doc_key}' in {path.name}")
        seen_keys.add(parsed.doc_key)
        docs.append(parsed)
    return docs
