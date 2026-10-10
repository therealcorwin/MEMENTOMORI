"""Tests automatisés du Sprint 13 : Nouveaux Pipelines d'Alimentation Automatique.

Vérifie :
1. Pipeline Git & Documentation Technique (ingestion, déduplication SHA-256, routage 'dev')
2. Pipeline Markdown / Obsidian (frontmatter YAML, wikilinks [[Note]], routage dynamique 'formation' / 'dev')
3. Pipeline de Veille RSS & Web (Règle P5 : auto_approve=False, statut 'a_verifier')
4. Points de terminaison API (/v1/ingest/git, /v1/ingest/markdown, /v1/ingest/rss, /v1/ingest/web-article)
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from knowledge.models import (
    Workspace,
    Collection,
    Source,
    Document,
    DocumentVersion,
    Fragment,
)
from knowledge.services.git_ingest import (
    scan_git_repository,
    ingest_git_repository,
    ingest_git_file,
)
from knowledge.services.markdown_sync import (
    parse_markdown_note,
    sync_markdown_directory,
    ingest_single_markdown_note,
)
from knowledge.services.feed_harvester import (
    parse_feed_xml,
    harvest_feed_content,
    harvest_web_article,
)

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Tech &amp; AI Security News</title>
    <link>https://example.com/feed</link>
    <description>Veille technologique et cybersécurité</description>
    <item>
      <title>Nouvelle vulnérabilité détectée dans OpenSSH</title>
      <link>https://example.com/articles/openssh-cve-2026</link>
      <description>&lt;p&gt;Un correctif critique &lt;b&gt;v9.8p1&lt;/b&gt; a été déployé pour contrer une régression de type race condition.&lt;/p&gt;</description>
      <pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate>
      <author>Alice Rossi</author>
    </item>
    <item>
      <title>Lancement officiel de Python 3.14</title>
      <link>https://example.com/articles/python-314-release</link>
      <description>&lt;div&gt;Python 3.14 apporte le support expérimental du JIT et la finalisation du mode free-threading.&lt;/div&gt;</description>
      <pubDate>Wed, 07 Oct 2026 14:30:00 GMT</pubDate>
      <author>Guido Team</author>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Deep Learning Research Papers</title>
  <link href="https://example.org/atom"/>
  <updated>2026-10-06T12:00:00Z</updated>
  <entry>
    <title>Scaling Laws for Reasoning Models</title>
    <link href="https://example.org/papers/scaling-laws"/>
    <summary>Étude expérimentale démontrant les gains de performance du test-time compute.</summary>
    <published>2026-10-06T09:00:00Z</published>
    <author>
      <name>Dr. Turing</name>
    </author>
  </entry>
</feed>
"""


@pytest.mark.asyncio
async def test_git_pipeline_ingestion_and_deduplication(db_session):
    """Vérifie le scan, l'ingestion dans 'dev' et l'idempotence SHA-256 du pipeline Git (Task 13.1)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        run_id = uuid.uuid4().hex[:6]
        repo_name = f"alpha-core-{run_id}"
        (tmp_path / "README.md").write_text(f"# Projet Alpha Core {run_id}\n\nArchitecture du moteur principal.", encoding="utf-8")
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "architecture.md").write_text(f"# Spécification Microservices {run_id}\n\nDiagrammes et flux d'échanges.", encoding="utf-8")
        # Fichier ignoré
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "junk.md").write_text("# Ignore me", encoding="utf-8")

        # 1. Scan des fichiers
        items = scan_git_repository(str(tmp_path))
        paths = [it.path for it in items]
        assert "README.md" in paths
        assert "docs/architecture.md" in paths
        assert not any("__pycache__" in p for p in paths)

        # 2. Ingestion initiale
        res1 = await ingest_git_repository(
            repo_path=str(tmp_path),
            db=db_session,
            repo_name=repo_name,
            workspace_slug="dev",
            collection_name="documentation-technique",
        )
        assert res1.scanned_files == 2
        assert res1.ingested_count == 2
        assert res1.skipped_count == 0
        assert len(res1.doc_ids) == 2

        # Vérification en base
        doc_q = await db_session.execute(
            select(Document).where(Document.title.like(f"%{repo_name}%"))
        )
        docs = doc_q.scalars().all()
        assert len(docs) >= 2
        for d in docs:
            assert d.scope == "dev"
            assert d.sensitivity == "interne"
            assert d.status == "actif"
            assert d.metadata_.get("repo") == repo_name

        # 3. Ré-ingestion (idempotence SHA-256)
        res2 = await ingest_git_repository(
            repo_path=str(tmp_path),
            db=db_session,
            repo_name=repo_name,
            workspace_slug="dev",
            collection_name="documentation-technique",
        )
        assert res2.scanned_files == 2
        assert res2.ingested_count == 0
        assert res2.skipped_count == 2


@pytest.mark.asyncio
async def test_markdown_obsidian_parsing_and_routing(db_session):
    """Vérifie l'analyse de frontmatter YAML, les wikilinks et le routage dynamique (Task 13.2)."""
    run_id = uuid.uuid4().hex[:6]
    # 1. Note avec frontmatter explicite et wikilinks
    note1_text = f"""---
title: Fiche de Cadrage Client ACME {run_id}
workspace: consulting
collection: livrables
sensitivity: confidentiel
tags: [consulting, cadrage, acme]
---
# Synthèse du Cadrage {run_id}
Rencontre avec le DSI d'ACME. Voir également [[Architecture Technique]] et [[Contrat Cadre]].
"""
    parsed1 = parse_markdown_note(note1_text, "cadrage_acme.md")
    assert parsed1.title == f"Fiche de Cadrage Client ACME {run_id}"
    assert parsed1.workspace == "consulting"
    assert parsed1.collection == "livrables"
    assert parsed1.sensitivity == "confidentiel"
    assert "Architecture Technique" in parsed1.wikilinks
    assert "Contrat Cadre" in parsed1.wikilinks
    assert "acme" in parsed1.tags

    # 2. Note sans frontmatter avec tags de formation -> routage 'formation'
    note2_text = f"""# Théorie de l'Attention et Self-Attention {run_id}
Introduction aux transformers. Tags: #cours #formation #deeplearning
Voir les bases dans [[Algèbre Linéaire]].
"""
    parsed2 = parse_markdown_note(note2_text, "transformers.md")
    assert parsed2.title == f"Théorie de l'Attention et Self-Attention {run_id}"
    assert parsed2.workspace == "formation"
    assert parsed2.collection == "cours-et-notes"
    assert "Algèbre Linéaire" in parsed2.wikilinks

    # 3. Synchronisation de dossier
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "cours_ia.md").write_text(note2_text, encoding="utf-8")
        (tmp_path / "cadrage.md").write_text(note1_text, encoding="utf-8")

        sync_res = await sync_markdown_directory(str(tmp_path), db=db_session)
        assert sync_res.scanned_notes == 2
        assert sync_res.ingested_count == 2
        assert len(sync_res.errors) == 0


@pytest.mark.asyncio
async def test_feed_harvester_rule_p5_and_validation_queue(db_session):
    """Vérifie le moissonnage RSS/Atom et la conformité stricte à la Règle P5 (Task 13.3)."""
    run_id = uuid.uuid4().hex[:6]
    sample_rss = SAMPLE_RSS_XML.replace("OpenSSH", f"OpenSSH {run_id}").replace("Python 3.14", f"Python 3.14 {run_id}")
    sample_atom = SAMPLE_ATOM_XML.replace("Scaling Laws", f"Scaling Laws {run_id}")

    # 1. Parsing RSS et détection de balises HTML nettoyées
    title, entries = parse_feed_xml(sample_rss)
    assert title == "Tech & AI Security News"
    assert len(entries) == 2
    assert f"Nouvelle vulnérabilité détectée dans OpenSSH {run_id}" == entries[0].title
    assert "<p>" not in entries[0].summary
    assert "v9.8p1" in entries[0].summary
    assert entries[0].author == "Alice Rossi"

    # 2. Parsing Atom
    atom_title, atom_entries = parse_feed_xml(sample_atom)
    assert atom_title == "Deep Learning Research Papers"
    assert len(atom_entries) == 1
    assert f"Scaling Laws {run_id} for Reasoning Models" == atom_entries[0].title
    assert atom_entries[0].author == "Dr. Turing"

    # 3. Ingestion dans 'veille' : validation de la RÈGLE P5 (status='a_verifier', auto_approve=False)
    harvest_res = await harvest_feed_content(
        xml_content=sample_rss,
        db=db_session,
        feed_name=f"Tech & AI News {run_id}",
        workspace_slug="veille",
        collection_name="flux-rss",
    )
    assert harvest_res.scanned_entries == 2
    assert harvest_res.ingested_count == 2
    assert harvest_res.skipped_count == 0

    # Vérification en base : statut impératif 'a_verifier'
    for doc_id_str in harvest_res.doc_ids:
        doc = await db_session.get(Document, uuid.UUID(doc_id_str))
        assert doc is not None
        assert doc.status == "a_verifier", f"Règle P5 violée : statut attendu 'a_verifier', obtenu '{doc.status}'"
        assert doc.is_active is True
        assert doc.source_id is not None

        # Vérification source auto_approve = False
        src = await db_session.get(Source, doc.source_id)
        assert src is not None
        assert src.auto_approve is False, "Règle P5 violée : la source doit avoir auto_approve=False"

    # 4. Ingestion Web Article unitaire
    web_doc_id = await harvest_web_article(
        url=f"https://cyber.gouv.fr/avis-anssi-2026-{run_id}",
        title=f"Avis de sécurité ANSSI CERT-FR {run_id}",
        text_content="Recommandations sur le durcissement des tunnels VPN et proxys.",
        db=db_session,
        author="CERT-FR",
    )
    assert web_doc_id is not None
    web_doc = await db_session.get(Document, web_doc_id)
    assert web_doc.status == "a_verifier"


@pytest.mark.asyncio
async def test_ingest_api_endpoints(async_client: AsyncClient):
    """Vérifie les points de terminaison HTTP /v1/ingest/* (Task 13.4)."""
    headers = {"X-Dev-Principal": "admin_user"}
    run_id = uuid.uuid4().hex[:6]

    # 1. POST /v1/ingest/git (Mode fichier unitaire)
    git_payload = {
        "title": f"Architecture Pipeline Ingestion {run_id}",
        "content": f"# Pipeline Ingestion V2 {run_id}\n\nDétail des services git, markdown et rss.",
        "path": f"docs/pipeline_{run_id}.md",
        "repo_name": f"mementomori-{run_id}",
        "workspace_slug": "dev",
        "collection_name": "documentation-technique",
    }
    resp_git = await async_client.post("/v1/ingest/git", json=git_payload, headers=headers)
    assert resp_git.status_code == 200
    data_git = resp_git.json()
    assert data_git["status"] == "success"
    assert data_git["mode"] == "single_file"
    assert data_git["workspace"] == "dev"

    # 2. POST /v1/ingest/markdown (Mode note unitaire)
    md_payload = {
        "content": f"---\ntitle: Synthèse Modèles Autoregressifs {run_id}\ntags: [cours, ia]\n---\n# Autoregression {run_id}\nExplications pas-à-pas.",
        "filename": f"autoregression_{run_id}.md",
        "vault_name": "vault-formation",
    }
    resp_md = await async_client.post("/v1/ingest/markdown", json=md_payload, headers=headers)
    assert resp_md.status_code == 200
    data_md = resp_md.json()
    assert data_md["status"] == "success"
    assert data_md["mode"] == "single_note"

    # 3. POST /v1/ingest/rss (Mode flux XML avec conformité Règle P5)
    sample_atom = SAMPLE_ATOM_XML.replace("Scaling Laws", f"Scaling Laws {run_id}")
    rss_payload = {
        "xml_content": sample_atom,
        "feed_name": f"Arxiv Deep Learning {run_id}",
        "workspace_slug": "veille",
        "collection_name": "flux-rss",
    }
    resp_rss = await async_client.post("/v1/ingest/rss", json=rss_payload, headers=headers)
    assert resp_rss.status_code == 200
    data_rss = resp_rss.json()
    assert data_rss["status"] == "success"
    assert data_rss["ingested_pending_validation"] >= 1
    assert "a_verifier" in data_rss["rule_p5_applied"]

    # 4. POST /v1/ingest/web-article
    article_payload = {
        "url": f"https://example.com/blog/rag-guide-{run_id}",
        "title": f"Guide Pratique d'Évaluation RAG {run_id}",
        "content": "Comprendre les métriques Ragas, TruLens et Recall@K.",
        "author": "Data Scientist",
        "source_name": "Blog RAG",
    }
    resp_art = await async_client.post("/v1/ingest/web-article", json=article_payload, headers=headers)
    assert resp_art.status_code == 200
    data_art = resp_art.json()
    assert data_art["status"] == "success"
    assert "a_verifier" in data_art["rule_p5_applied"]
