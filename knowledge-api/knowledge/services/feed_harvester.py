"""Pipeline de Veille RSS & Web (Sprint 13, Tâche 13.3).

Moissonne les flux RSS / Atom et articles web pour le workspace 'veille'
(collections 'flux-rss' et 'veille-techno').
Applique rigoureusement la Règle P5 et §3.3 :
- auto_approve = False
- status = 'a_verifier' (sas de validation humaine)
- Ingestion idempotente via SHA-256
"""

from __future__ import annotations

import html
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.logging import get_logger
from knowledge.services.ingestion import ingest_single_document

logger = get_logger(__name__)

HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class FeedEntry:
    """Entrée d'un flux RSS ou Atom."""
    title: str
    link: str
    summary: str
    published: Optional[str] = None
    author: Optional[str] = None
    feed_name: Optional[str] = None


@dataclass
class FeedHarvestResult:
    """Résultat du moissonnage d'un flux."""
    feed_name: str
    feed_url: Optional[str] = None
    scanned_entries: int = 0
    ingested_count: int = 0
    skipped_count: int = 0
    doc_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def strip_html_tags(raw_html: str) -> str:
    """Nettoie les balises HTML et convertit les entités HTML en texte brut propre."""
    if not raw_html:
        return ""
    # Remplacer les retours à la ligne HTML
    cleaned = re.sub(r"<(br|p|div|/p|/div)[^>]*>", "\n", raw_html, flags=re.IGNORECASE)
    cleaned = HTML_TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    # Réduire les espaces et lignes vides multiples
    lines = [re.sub(r"\s+", " ", l).strip() for l in cleaned.splitlines()]
    return "\n".join(l for l in lines if l)


def parse_feed_xml(xml_content: str, default_feed_name: str = "Flux RSS") -> Tuple[str, List[FeedEntry]]:
    """Parse le XML d'un flux (RSS 2.0 ou Atom 1.0) et extrait les entrées."""
    entries: List[FeedEntry] = []
    feed_title = default_feed_name

    try:
        root = ET.fromstring(xml_content.strip())
    except Exception as exc:
        logger.error("xml_feed_parse_error", error=str(exc))
        return feed_title, entries

    # Détection du tag racine (en ignorant l'éventuel namespace XML)
    tag_clean = root.tag.split("}")[-1].lower()

    if tag_clean == "rss" or root.find("channel") is not None:
        # --- Format RSS 2.0 ---
        channel = root.find("channel")
        if channel is None:
            channel = root
        ch_title = channel.find("title")
        if ch_title is not None and ch_title.text:
            feed_title = ch_title.text.strip()

        for item in channel.findall("item"):
            t_el = item.find("title")
            title = t_el.text.strip() if (t_el is not None and t_el.text) else "Article sans titre"

            l_el = item.find("link")
            link = l_el.text.strip() if (l_el is not None and l_el.text) else ""

            # Description ou encoded content
            desc_el = item.find("description")
            desc_text = desc_el.text if (desc_el is not None and desc_el.text) else ""

            # dc:creator ou author
            author = None
            for child in item:
                if child.tag.endswith("creator") or child.tag.endswith("author"):
                    if child.text:
                        author = child.text.strip()
                        break

            # pubDate
            pub_el = item.find("pubDate")
            published = pub_el.text.strip() if (pub_el is not None and pub_el.text) else None

            summary = strip_html_tags(desc_text)
            if not summary:
                summary = title

            entries.append(
                FeedEntry(
                    title=title,
                    link=link,
                    summary=summary,
                    published=published,
                    author=author,
                    feed_name=feed_title,
                )
            )

    elif tag_clean == "feed":
        # --- Format Atom 1.0 ---
        for child in root:
            if child.tag.endswith("title") and child.text:
                feed_title = child.text.strip()
                break

        for entry_el in root:
            if not entry_el.tag.endswith("entry"):
                continue

            title = "Article sans titre"
            link = ""
            summary = ""
            published = None
            author = None

            for child in entry_el:
                ctag = child.tag.split("}")[-1]
                if ctag == "title" and child.text:
                    title = child.text.strip()
                elif ctag == "link":
                    link = child.attrib.get("href", child.text or "")
                elif ctag in ("summary", "content") and child.text:
                    summary = strip_html_tags(child.text)
                elif ctag in ("published", "updated") and child.text:
                    published = child.text.strip()
                elif ctag == "author":
                    name_el = child.find("{http://www.w3.org/2005/Atom}name")
                    if name_el is None:
                        name_el = child.find("{*}name")
                    if name_el is None:
                        name_el = child.find("name")
                    if name_el is not None and name_el.text:
                        author = name_el.text.strip()
                    elif child.text and child.text.strip():
                        author = child.text.strip()

            if not summary:
                summary = title

            entries.append(
                FeedEntry(
                    title=title,
                    link=link,
                    summary=summary,
                    published=published,
                    author=author,
                    feed_name=feed_title,
                )
            )

    return feed_title, entries


async def harvest_feed_content(
    xml_content: str,
    db: AsyncSession,
    feed_name: Optional[str] = None,
    feed_url: Optional[str] = None,
    workspace_slug: str = "veille",
    collection_name: str = "flux-rss",
    sensitivity: str = "public",
) -> FeedHarvestResult:
    """Traite le contenu XML d'un flux et ingère les entrées dans le sas 'a_verifier'."""
    detected_title, entries = parse_feed_xml(xml_content, default_feed_name=feed_name or "Veille Flux")
    effective_name = feed_name or detected_title

    result = FeedHarvestResult(
        feed_name=effective_name,
        feed_url=feed_url,
        scanned_entries=len(entries),
    )

    for entry in entries:
        try:
            full_title = f"[{effective_name}] {entry.title}"
            original_ref = entry.link or f"rss://{effective_name}/{uuid.uuid4().hex[:8]}"

            # Formatage Markdown document structuré
            doc_content = (
                f"# {entry.title}\n\n"
                f"**Source** : {effective_name}\n"
                f"**URL** : {entry.link}\n"
                f"**Date** : {entry.published or 'Non spécifiée'}\n"
                f"**Auteur** : {entry.author or 'Non spécifié'}\n\n"
                f"## Synthèse du Contenu\n\n"
                f"{entry.summary}\n"
            )

            metadata = {
                "feed_name": effective_name,
                "feed_url": feed_url,
                "link": entry.link,
                "published": entry.published,
                "author": entry.author,
                "source_type": "rss_feed",
                "harvested_at": datetime.now(timezone.utc).isoformat(),
            }

            # RÈGLE P5 STRICTE : auto_approve = False, status = 'a_verifier'
            doc_id, is_new = await ingest_single_document(
                title=full_title,
                content=doc_content,
                workspace_slug=workspace_slug,
                collection_name=collection_name,
                db=db,
                source_type="rss_feed",
                scope="veille",
                sensitivity=sensitivity,
                original_ref=original_ref,
                metadata_=metadata,
                auto_approve=False,
                status="a_verifier",
                return_is_new=True,
            )

            if is_new:
                result.doc_ids.append(str(doc_id))
                result.ingested_count += 1
            else:
                result.skipped_count += 1
        except Exception as exc:
            err_msg = f"Erreur sur entrée '{entry.title}': {exc}"
            logger.error("feed_harvest_entry_error", title=entry.title, error=str(exc))
            result.errors.append(err_msg)

    logger.info(
        "feed_harvest_completed",
        feed=effective_name,
        scanned=result.scanned_entries,
        ingested=result.ingested_count,
        skipped=result.skipped_count,
    )
    return result


async def harvest_remote_feed(
    feed_url: str,
    db: AsyncSession,
    feed_name: Optional[str] = None,
    workspace_slug: str = "veille",
    collection_name: str = "flux-rss",
    sensitivity: str = "public",
) -> FeedHarvestResult:
    """Télécharge un flux RSS/Atom distant et ingère ses articles dans le sas 'a_verifier'."""
    headers = {
        "User-Agent": "MEMENTOMORI-Knowledge-Harvester/1.0 (+https://csrgb.ovh)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(feed_url, headers=headers)
            if resp.status_code != 200:
                logger.error("feed_fetch_http_error", url=feed_url, status=resp.status_code)
                return FeedHarvestResult(
                    feed_name=feed_name or feed_url,
                    feed_url=feed_url,
                    errors=[f"Erreur HTTP {resp.status_code}"],
                )
            xml_text = resp.text
    except Exception as exc:
        logger.error("feed_fetch_connection_error", url=feed_url, error=str(exc))
        return FeedHarvestResult(
            feed_name=feed_name or feed_url,
            feed_url=feed_url,
            errors=[f"Erreur réseau: {exc}"],
        )

    return await harvest_feed_content(
        xml_content=xml_text,
        db=db,
        feed_name=feed_name,
        feed_url=feed_url,
        workspace_slug=workspace_slug,
        collection_name=collection_name,
        sensitivity=sensitivity,
    )


async def harvest_web_article(
    url: str,
    title: str,
    text_content: str,
    db: AsyncSession,
    author: Optional[str] = None,
    source_name: Optional[str] = "Web",
    workspace_slug: str = "veille",
    collection_name: str = "articles-web",
    sensitivity: str = "public",
) -> Optional[uuid.UUID]:
    """Ingère un article web ou une dépêche dans le sas 'a_verifier' (Règle P5)."""
    full_title = f"[{source_name}] {title}"
    doc_content = (
        f"# {title}\n\n"
        f"**Source** : {source_name}\n"
        f"**URL** : {url}\n"
        f"**Auteur** : {author or 'Non spécifié'}\n\n"
        f"## Contenu\n\n"
        f"{text_content}\n"
    )

    metadata = {
        "url": url,
        "author": author,
        "source_name": source_name,
        "source_type": "web_harvester",
        "harvested_at": datetime.now(timezone.utc).isoformat(),
    }

    # RÈGLE P5 STRICTE : auto_approve = False, status = 'a_verifier'
    return await ingest_single_document(
        title=full_title,
        content=doc_content,
        workspace_slug=workspace_slug,
        collection_name=collection_name,
        db=db,
        source_type="web_harvester",
        scope="veille",
        sensitivity=sensitivity,
        original_ref=url,
        metadata_=metadata,
        auto_approve=False,
        status="a_verifier",
    )
