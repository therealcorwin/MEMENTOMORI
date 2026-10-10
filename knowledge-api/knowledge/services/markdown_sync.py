"""Pipeline de synchronisation Markdown & Obsidian (Sprint 13, Tâche 13.2).

Analyse les notes Markdown / Obsidian (coffre de notes), extrait le frontmatter YAML,
détecte les wikilinks ([[Note]]), résout intelligemment le routage vers les workspaces
('formation', 'dev', 'consulting'...) et assure l'ingestion idempotente via SHA-256.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.services.ingestion import ingest_single_document

logger = get_logger(__name__)

IGNORE_DIRS = {
    ".obsidian",
    ".trash",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
}

WIKILINK_PATTERN = re.compile(r"\[\[([^\|\]]+)(?:\|([^\]]+))?\]\]")


@dataclass
class ParsedMarkdownNote:
    """Note Markdown analysée avec son frontmatter et ses liens."""
    title: str
    body: str
    raw_content: str
    frontmatter: dict[str, Any]
    tags: List[str]
    wikilinks: List[str]
    workspace: str
    collection: str
    sensitivity: str = "interne"
    scope: str = "owner"
    relative_path: Optional[str] = None


@dataclass
class MarkdownSyncResult:
    """Bilan de la synchronisation d'un répertoire de notes Markdown."""
    vault_path: str
    scanned_notes: int = 0
    ingested_count: int = 0
    skipped_count: int = 0
    doc_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def extract_frontmatter_and_body(text: str) -> Tuple[dict[str, Any], str]:
    """Sépare le frontmatter YAML du corps Markdown (délimiteurs ---)."""
    text_stripped = text.strip()
    if not text_stripped.startswith("---"):
        return {}, text

    # Recherche du délimiteur fermant
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    closing_index = -1
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            closing_index = i
            break

    if closing_index == -1:
        return {}, text

    yaml_str = "".join(lines[1:closing_index])
    body_str = "".join(lines[closing_index + 1 :])

    try:
        parsed = yaml.safe_load(yaml_str)
        if isinstance(parsed, dict):
            return parsed, body_str
    except Exception as exc:
        logger.debug("markdown_yaml_frontmatter_parse_error", error=str(exc))

    return {}, text


def extract_wikilinks(text: str) -> List[str]:
    """Extrait la liste des notes cibles mentionnées via [[Note]] ou [[Note|Alias]]."""
    matches = WIKILINK_PATTERN.findall(text)
    links = []
    for target, _alias in matches:
        t_clean = target.strip()
        if t_clean and t_clean not in links:
            links.append(t_clean)
    return links


def resolve_routing(
    frontmatter: dict[str, Any],
    tags: List[str],
    path_hint: str = "",
    default_workspace: str = "formation",
    default_collection: str = "notes-personnelles",
) -> Tuple[str, str, str, str]:
    """Détermine dynamiquement (workspace, collection, sensitivity, scope) pour la note."""
    # 1. Respect strict des valeurs explicites du frontmatter
    ws = frontmatter.get("workspace")
    col = frontmatter.get("collection")
    sens = frontmatter.get("sensitivity", "interne")
    scope = frontmatter.get("scope", "owner")

    if ws and col:
        return str(ws).lower(), str(col), str(sens), str(scope)

    # 2. Analyse sémantique des tags et du chemin
    combined_tags = [t.lower().lstrip("#") for t in tags]
    path_lower = path_hint.lower()

    # Détection DEV
    dev_keywords = {"dev", "code", "architecture", "python", "docker", "api", "git", "backend", "frontend", "sql"}
    if any(k in combined_tags for k in dev_keywords) or any(k in path_lower for k in ["/dev/", "/code/", "/tech/"]):
        ws = ws or "dev"
        col = col or "notes-techniques"
        return ws, col, sens, "dev"

    # Détection CONSULTING
    consulting_keywords = {"consulting", "mission", "client", "audit", "livrable", "propale", "atelier"}
    if any(k in combined_tags for k in consulting_keywords) or "/consulting/" in path_lower:
        ws = ws or "consulting"
        col = col or "livrables"
        return ws, col, sens, "pro"

    # Détection FINANCES
    finances_keywords = {"finance", "finances", "budget", "fiscal", "banque", "impot", "placement", "epargne"}
    if any(k in combined_tags for k in finances_keywords) or "/finances/" in path_lower:
        ws = ws or "finances-perso"
        col = col or "notes-financieres"
        return ws, col, "confidentiel", "finances"

    # Détection SANTÉ
    sante_keywords = {"sante", "medical", "sport", "docteur", "ordonnance", "bilan"}
    if any(k in combined_tags for k in sante_keywords) or "/sante/" in path_lower:
        ws = ws or "sante-perso"
        col = col or "notes-sante"
        return ws, col, "secret", "owner"

    # Détection ENTREPRISE
    entreprise_keywords = {"entreprise", "urssaf", "facture", "kbis", "siret", "compta"}
    if any(k in combined_tags for k in entreprise_keywords) or "/entreprise/" in path_lower:
        ws = ws or "entreprise"
        col = col or "gestion"
        return ws, col, sens, "pro"

    # Détection VEILLE
    veille_keywords = {"veille", "ai-news", "benchmark", "rss", "tendance"}
    if any(k in combined_tags for k in veille_keywords) or "/veille/" in path_lower:
        ws = ws or "veille"
        col = col or "veille-techno"
        return ws, col, "public", "pro"

    # Détection FORMATION (Par défaut pour notes d'études, fiches de lecture, cours)
    ws = ws or default_workspace
    col = col or ("cours-et-notes" if ws == "formation" else default_collection)
    return ws, col, sens, scope


def parse_markdown_note(content: str, filename: str, path_hint: str = "") -> ParsedMarkdownNote:
    """Analyse complète d'une note Markdown."""
    fm, body = extract_frontmatter_and_body(content)

    # Extraction des tags (frontmatter tags ou listes)
    raw_tags = fm.get("tags", [])
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    else:
        tags = []

    # Extraction des wikilinks
    wikilinks = extract_wikilinks(content)

    # Titre : frontmatter -> premier # -> nom du fichier
    title = fm.get("title")
    if not title:
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("# "):
                title = s[2:].strip()
                break
    if not title:
        title = Path(filename).stem.replace("_", " ").replace("-", " ").title()

    # Routage dynamique
    ws, col, sens, scope = resolve_routing(
        frontmatter=fm,
        tags=tags,
        path_hint=path_hint or filename,
    )

    return ParsedMarkdownNote(
        title=str(title),
        body=body,
        raw_content=content,
        frontmatter=fm,
        tags=tags,
        wikilinks=wikilinks,
        workspace=ws,
        collection=col,
        sensitivity=sens,
        scope=scope,
        relative_path=path_hint or filename,
    )


async def sync_markdown_directory(
    directory_path: str,
    db: AsyncSession,
    default_workspace: str = "formation",
    default_collection: str = "notes-personnelles",
) -> MarkdownSyncResult:
    """Synchronise un répertoire complet de notes Markdown (coffre Obsidian)."""
    root_p = Path(directory_path)
    if not root_p.exists() or not root_p.is_dir():
        logger.error("markdown_directory_not_found", path=directory_path)
        return MarkdownSyncResult(vault_path=directory_path, errors=[f"Répertoire introuvable: {directory_path}"])

    result = MarkdownSyncResult(vault_path=str(root_p))

    for dirpath, dirnames, filenames in os.walk(root_p):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]

        for fn in filenames:
            if fn.lower().endswith((".md", ".markdown")):
                full_path = Path(dirpath) / fn
                result.scanned_notes += 1
                try:
                    rel_path = full_path.relative_to(root_p).as_posix()
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    if not content.strip():
                        result.skipped_count += 1
                        continue

                    note = parse_markdown_note(content, fn, path_hint=rel_path)
                    original_ref = f"obsidian://{rel_path}"

                    metadata = {
                        "vault": root_p.name,
                        "rel_path": rel_path,
                        "tags": note.tags,
                        "wikilinks": note.wikilinks,
                        "frontmatter": note.frontmatter,
                        "source_type": "obsidian",
                    }

                    doc_id, is_new = await ingest_single_document(
                        title=note.title,
                        content=note.raw_content,
                        workspace_slug=note.workspace,
                        collection_name=note.collection,
                        db=db,
                        source_type="obsidian",
                        scope=note.scope,
                        sensitivity=note.sensitivity,
                        original_ref=original_ref,
                        metadata_=metadata,
                        auto_approve=True,
                        status="actif",
                        return_is_new=True,
                    )

                    if is_new:
                        result.doc_ids.append(str(doc_id))
                        result.ingested_count += 1
                    else:
                        result.skipped_count += 1
                except Exception as exc:
                    err_msg = f"Erreur sur {fn}: {exc}"
                    logger.error("markdown_sync_file_error", file=fn, error=str(exc))
                    result.errors.append(err_msg)

    logger.info(
        "markdown_vault_sync_completed",
        vault=root_p.name,
        scanned=result.scanned_notes,
        ingested=result.ingested_count,
        skipped=result.skipped_count,
    )
    return result


async def ingest_single_markdown_note(
    content: str,
    filename: str,
    db: AsyncSession,
    vault_name: str = "notes",
    default_workspace: str = "formation",
    default_collection: str = "notes-personnelles",
) -> Optional[uuid.UUID]:
    """Ingère une note Markdown unitaire avec analyse du frontmatter et des wikilinks."""
    note = parse_markdown_note(content, filename)
    original_ref = f"obsidian://{vault_name}/{filename}"
    metadata = {
        "vault": vault_name,
        "filename": filename,
        "tags": note.tags,
        "wikilinks": note.wikilinks,
        "frontmatter": note.frontmatter,
        "source_type": "obsidian",
    }

    return await ingest_single_document(
        title=note.title,
        content=note.raw_content,
        workspace_slug=note.workspace,
        collection_name=note.collection,
        db=db,
        source_type="obsidian",
        scope=note.scope,
        sensitivity=note.sensitivity,
        original_ref=original_ref,
        metadata_=metadata,
        auto_approve=True,
        status="actif",
    )
