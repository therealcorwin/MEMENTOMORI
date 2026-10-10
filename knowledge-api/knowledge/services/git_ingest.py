"""Pipeline d'ingestion Git & Documentation Technique (Sprint 13, Tâche 13.1).

Synchronise les documentations techniques (README, guides, architecture, docs)
depuis des dépôts Git vers le workspace 'dev' (collection 'documentation-technique').
Gère l'idempotence via hachage SHA-256 et la traçabilité des commits/branches.
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.services.ingestion import ingest_single_document
from knowledge.services.dedup import check_duplicate

logger = get_logger(__name__)

IGNORE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    ".pytest_cache",
    ".idea",
    ".vscode",
    ".gemini",
    "graphify-out",
}


@dataclass
class GitDocItem:
    """Représentation d'un document extrait d'un dépôt Git."""
    path: str
    title: str
    content: str
    commit_hash: Optional[str] = None
    branch: Optional[str] = None


@dataclass
class GitSyncResult:
    """Résultat de la synchronisation d'un dépôt Git."""
    repo_name: str
    scanned_files: int = 0
    ingested_count: int = 0
    skipped_count: int = 0
    doc_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def extract_markdown_title(content: str, fallback_filename: str) -> str:
    """Extrait le premier titre de niveau 1 (# Titre) ou utilise le nom de fichier."""
    for line in content.splitlines():
        line_s = line.strip()
        if line_s.startswith("# "):
            title = line_s[2:].strip()
            # Nettoyer les emojis éventuels ou formatage excessif
            if title:
                return title
    # Fallback sur le nom de fichier nettoyé
    clean_name = Path(fallback_filename).stem.replace("_", " ").replace("-", " ")
    return clean_name.title()


def get_git_metadata(repo_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Tente d'extraire le hash du commit HEAD et la branche courante."""
    commit_hash: Optional[str] = None
    branch: Optional[str] = None

    try:
        # Commit hash
        res_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if res_commit.returncode == 0:
            commit_hash = res_commit.stdout.strip()

        # Branche
        res_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
        if res_branch.returncode == 0:
            branch = res_branch.stdout.strip()
    except Exception as exc:
        logger.debug("git_metadata_extraction_fallback", path=repo_path, error=str(exc))

    return commit_hash, branch


def scan_git_repository(
    repo_path: str,
    branch: Optional[str] = None,
    extensions: tuple[str, ...] = (".md", ".markdown"),
) -> List[GitDocItem]:
    """Scanne récursivement les fichiers Markdown dans un dépôt Git."""
    root_p = Path(repo_path)
    if not root_p.exists() or not root_p.is_dir():
        logger.error("git_repo_path_not_found", path=repo_path)
        return []

    commit_hash, detected_branch = get_git_metadata(str(root_p))
    effective_branch = branch or detected_branch or "main"

    items: List[GitDocItem] = []

    for dirpath, dirnames, filenames in os.walk(root_p):
        # Exclure les répertoires ignorés
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]

        for fn in filenames:
            if any(fn.lower().endswith(ext) for ext in extensions):
                full_path = Path(dirpath) / fn
                try:
                    rel_path = full_path.relative_to(root_p).as_posix()
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    if not content.strip():
                        continue

                    title = extract_markdown_title(content, fn)
                    items.append(
                        GitDocItem(
                            path=rel_path,
                            title=title,
                            content=content,
                            commit_hash=commit_hash,
                            branch=effective_branch,
                        )
                    )
                except Exception as exc:
                    logger.warning("git_scan_file_error", file=str(full_path), error=str(exc))

    return items


async def ingest_git_repository(
    repo_path: str,
    db: AsyncSession,
    repo_name: Optional[str] = None,
    branch: Optional[str] = None,
    workspace_slug: str = "dev",
    collection_name: str = "documentation-technique",
    sensitivity: str = "interne",
) -> GitSyncResult:
    """Ingère l'ensemble des documentations techniques d'un dépôt Git dans le workspace 'dev'."""
    path_obj = Path(repo_path)
    effective_repo_name = repo_name or path_obj.name

    doc_items = scan_git_repository(repo_path=str(path_obj), branch=branch)
    result = GitSyncResult(repo_name=effective_repo_name, scanned_files=len(doc_items))

    for item in doc_items:
        try:
            full_title = f"[{effective_repo_name}] {item.title}"
            original_ref = f"git://{effective_repo_name}/{item.path}"
            metadata = {
                "repo": effective_repo_name,
                "branch": item.branch,
                "path": item.path,
                "commit": item.commit_hash,
                "source_type": "git",
            }

            doc_id, is_new = await ingest_single_document(
                title=full_title,
                content=item.content,
                workspace_slug=workspace_slug,
                collection_name=collection_name,
                db=db,
                source_type="git",
                scope="dev",
                sensitivity=sensitivity,
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
            err_msg = f"Erreur sur {item.path}: {exc}"
            logger.error("git_ingest_file_failure", file=item.path, error=str(exc))
            result.errors.append(err_msg)

    logger.info(
        "git_sync_completed",
        repo=effective_repo_name,
        scanned=result.scanned_files,
        ingested=result.ingested_count,
        skipped=result.skipped_count,
    )
    return result


async def ingest_git_file(
    title: str,
    content: str,
    rel_path: str,
    repo_name: str,
    db: AsyncSession,
    branch: Optional[str] = "main",
    commit_hash: Optional[str] = None,
    workspace_slug: str = "dev",
    collection_name: str = "documentation-technique",
    sensitivity: str = "interne",
) -> Optional[uuid.UUID]:
    """Ingère un fichier de documentation Git unitaire (ex: webhook GitHub push)."""
    full_title = f"[{repo_name}] {title}"
    original_ref = f"git://{repo_name}/{rel_path}"
    metadata = {
        "repo": repo_name,
        "branch": branch,
        "path": rel_path,
        "commit": commit_hash,
        "source_type": "git",
    }

    return await ingest_single_document(
        title=full_title,
        content=content,
        workspace_slug=workspace_slug,
        collection_name=collection_name,
        db=db,
        source_type="git",
        scope="dev",
        sensitivity=sensitivity,
        original_ref=original_ref,
        metadata_=metadata,
        auto_approve=True,
        status="actif",
    )
