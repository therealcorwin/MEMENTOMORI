"""Service de chunking hybride (structurel, sémantique, enregistrement) selon §16.1 (Task 3.6)."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

class ChunkStrategy(str, Enum):
    STRUCTURAL = "structural"   # Markdown, HTML
    SEMANTIC = "semantic"       # PDF, texte brut
    RECORD = "record"           # Données structurées JSON/CSV

@dataclass
class ChunkConfig:
    target_size: int = 500      # mots / tokens approximatifs
    min_size: int = 100
    max_size: int = 1000
    overlap: int = 50

@dataclass
class Chunk:
    content: str
    context_prefix: str         # [Document: ... | Section: ... | Workspace: ...]
    position: int               # Index dans le document
    token_count: int
    page_number: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


def detect_strategy(content: str, mime_type: Optional[str] = None) -> ChunkStrategy:
    """Détecte la stratégie optimale de découpage."""
    if mime_type in ("text/markdown", "text/x-markdown", "text/html"):
        return ChunkStrategy.STRUCTURAL
    if mime_type in ("application/json", "text/csv"):
        return ChunkStrategy.RECORD
    # Heuristique sur le contenu
    if content.startswith(("# ", "## ", "### ")) or "\n## " in content:
        return ChunkStrategy.STRUCTURAL
    return ChunkStrategy.SEMANTIC


def estimate_tokens(text: str) -> int:
    """Estime grossièrement le nombre de tokens (ratio ~ 1.3 token par mot en français)."""
    words = len(text.split())
    return max(1, int(words * 1.3))


def split_into_chunks(
    text: str,
    document_title: str,
    workspace_slug: str,
    mime_type: Optional[str] = None,
    config: Optional[ChunkConfig] = None
) -> List[Chunk]:
    """Découpe un texte en chunks enrichis avec contexte et overlap selon la stratégie hybride (§16.1)."""
    cfg = config or ChunkConfig()
    strategy = detect_strategy(text, mime_type)
    
    raw_blocks: List[tuple[str, str]] = [] # (section_title, text_block)

    if strategy == ChunkStrategy.STRUCTURAL:
        # Découpage par sections Markdown
        pattern = r"(^#{1,3}\s+[^\n]+)"
        parts = re.split(pattern, text, flags=re.MULTILINE)
        current_section = "Introduction"
        
        i = 0
        if parts and not parts[0].startswith("#"):
            if parts[0].strip():
                raw_blocks.append((current_section, parts[0].strip()))
            i = 1

        while i < len(parts):
            if parts[i].startswith("#"):
                current_section = parts[i].lstrip("#").strip()
                content = parts[i+1].strip() if (i+1) < len(parts) else ""
                if content:
                    raw_blocks.append((current_section, content))
                i += 2
            else:
                if parts[i].strip():
                    raw_blocks.append((current_section, parts[i].strip()))
                i += 1

    elif strategy == ChunkStrategy.RECORD:
        # 1 ligne ou 1 objet = 1 bloc
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            raw_blocks.append((f"Enregistrement #{idx+1}", line))

    else:
        # Stratégie SEMANTIC : Paragraphes
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for p in paragraphs:
            raw_blocks.append(("Général", p))

    # Regroupement et gestion des overlaps
    chunks: List[Chunk] = []
    current_text = ""
    current_section = raw_blocks[0][0] if raw_blocks else "Contenu"
    previous_overlap = ""

    for section_name, block in raw_blocks:
        block_tokens = estimate_tokens(block)

        # Si le bloc seul dépasse max_size, découpage par phrases
        if block_tokens > cfg.max_size:
            sentences = re.split(r"(?<=[.!?])\s+", block)
            sub_text = ""
            for s in sentences:
                if estimate_tokens(sub_text + " " + s) > cfg.target_size and sub_text:
                    prefix = f"[Document: {document_title} | Section: {section_name} | Workspace: {workspace_slug}]"
                    full_content = (previous_overlap + " " + sub_text).strip()
                    chunks.append(Chunk(
                        content=full_content,
                        context_prefix=prefix,
                        position=len(chunks),
                        token_count=estimate_tokens(full_content)
                    ))
                    # Overlap: 2 dernières phrases
                    last_sentences = re.split(r"(?<=[.!?])\s+", sub_text)
                    previous_overlap = " ".join(last_sentences[-2:]) if len(last_sentences) >= 2 else sub_text
                    sub_text = s
                else:
                    sub_text = (sub_text + " " + s).strip()
            if sub_text:
                prefix = f"[Document: {document_title} | Section: {section_name} | Workspace: {workspace_slug}]"
                full_content = (previous_overlap + " " + sub_text).strip()
                chunks.append(Chunk(
                    content=full_content,
                    context_prefix=prefix,
                    position=len(chunks),
                    token_count=estimate_tokens(full_content)
                ))
            continue

        # Regroupement si < target_size
        cand = (current_text + "\n\n" + block).strip() if current_text else block
        if estimate_tokens(cand) < cfg.target_size:
            current_text = cand
            current_section = section_name
        else:
            # Finaliser le chunk en cours
            if current_text:
                prefix = f"[Document: {document_title} | Section: {current_section} | Workspace: {workspace_slug}]"
                full_content = (previous_overlap + "\n" + current_text).strip() if previous_overlap else current_text
                chunks.append(Chunk(
                    content=full_content,
                    context_prefix=prefix,
                    position=len(chunks),
                    token_count=estimate_tokens(full_content)
                ))
                # Calculer overlap pour le prochain chunk
                words = current_text.split()
                previous_overlap = " ".join(words[-cfg.overlap:]) if len(words) > cfg.overlap else current_text

            current_text = block
            current_section = section_name

    # Dernier bloc restant
    if current_text:
        prefix = f"[Document: {document_title} | Section: {current_section} | Workspace: {workspace_slug}]"
        full_content = (previous_overlap + "\n" + current_text).strip() if previous_overlap else current_text
        chunks.append(Chunk(
            content=full_content,
            context_prefix=prefix,
            position=len(chunks),
            token_count=estimate_tokens(full_content)
        ))

    return chunks
