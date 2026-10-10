"""
Seed des agents spécialisés et de leurs politiques RBAC pour les 9 workspaces (Sprint 14).
Permet à l'orchestrateur central de déléguer en toute sécurité selon le modèle d'architecture (§8, §16.5, §16.13).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-api"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from knowledge.dependencies import async_session_maker
from knowledge.models import Workspace, Principal, Policy


AGENT_SPECS = [
    {
        "agent_id": "csbot",
        "agent_name": "CSBOT Copropriété Assistant",
        "workspace_slug": "copro",
        "role": "cs",
        "scopes": ["public", "copro", "collectif", "conseil_syndical"],
        "max_sensitivity": "interne",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-finances",
        "agent_name": "Agent Finances Personnelles",
        "workspace_slug": "finances-perso",
        "role": "reader",
        "scopes": ["finances", "owner", "public"],
        "max_sensitivity": "confidentiel",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-admin",
        "agent_name": "Agent Administratif Personnel",
        "workspace_slug": "admin-perso",
        "role": "reader",
        "scopes": ["admin", "owner", "public"],
        "max_sensitivity": "confidentiel",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-sante",
        "agent_name": "Agent Santé Privé",
        "workspace_slug": "sante-perso",
        "role": "reader",
        "scopes": ["sante", "owner", "public"],
        "max_sensitivity": "confidentiel",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-entreprise",
        "agent_name": "Agent Entreprise & Professionnel",
        "workspace_slug": "entreprise",
        "role": "reader",
        "scopes": ["pro", "owner", "public"],
        "max_sensitivity": "confidentiel",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-dev",
        "agent_name": "Agent Développement & Technique",
        "workspace_slug": "dev",
        "role": "reader",
        "scopes": ["dev", "equipe", "public"],
        "max_sensitivity": "interne",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-formation",
        "agent_name": "Agent Formation & Connaissances",
        "workspace_slug": "formation",
        "role": "reader",
        "scopes": ["formation", "pedagogique", "prive", "public"],
        "max_sensitivity": "interne",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-consulting",
        "agent_name": "Agent Consulting & Prestations",
        "workspace_slug": "consulting",
        "role": "reader",
        "scopes": ["consulting", "prestation", "equipe", "public"],
        "max_sensitivity": "confidentiel",
        "actions": ["read", "search"]
    },
    {
        "agent_id": "agent-veille",
        "agent_name": "Agent Veille & Prospective",
        "workspace_slug": "veille",
        "role": "reader",
        "scopes": ["veille", "equipe", "public"],
        "max_sensitivity": "interne",
        "actions": ["read", "search"]
    },
]


async def seed_agents():
    print("🌱 Démarrage du seed des Principals Agents & Politiques RBAC pour les 9 workspaces...")
    async with async_session_maker() as db:
        # Récupérer les workspaces existants
        ws_list = (await db.execute(select(Workspace))).scalars().all()
        ws_by_slug = {w.slug: w for w in ws_list}

        for spec in AGENT_SPECS:
            agent_id = spec["agent_id"]
            name = spec["agent_name"]
            ws_slug = spec["workspace_slug"]

            ws = ws_by_slug.get(ws_slug)
            if not ws:
                print(f"  ⚠️ Workspace introuvable : '{ws_slug}', ignoré.")
                continue

            # 1. Vérifier ou créer le Principal
            p = (await db.execute(select(Principal).where(Principal.external_id == agent_id))).scalar_one_or_none()
            if not p:
                p = Principal(external_id=agent_id, type="app", display_name=name)
                db.add(p)
                await db.flush()
                print(f"  [+] Principal créé : {agent_id} ({p.id})")
            else:
                p.display_name = name
                print(f"  [=] Principal existant : {agent_id} ({p.id})")

            # 2. Vérifier ou mettre à jour la Policy
            pol = (await db.execute(
                select(Policy).where(
                    Policy.workspace_id == ws.id,
                    Policy.principal_id == p.id
                )
            )).scalar_one_or_none()

            if not pol:
                pol = Policy(
                    workspace_id=ws.id,
                    principal_id=p.id,
                    role=spec["role"],
                    allowed_scopes=spec["scopes"],
                    max_sensitivity=spec["max_sensitivity"],
                    actions=spec["actions"]
                )
                db.add(pol)
                print(f"  [+] Policy créée : agent={agent_id} -> ws={ws_slug} (scopes={spec['scopes']})")
            else:
                pol.role = spec["role"]
                pol.allowed_scopes = spec["scopes"]
                pol.max_sensitivity = spec["max_sensitivity"]
                pol.actions = spec["actions"]
                print(f"  [*] Policy mise à jour : agent={agent_id} -> ws={ws_slug} (scopes={spec['scopes']})")

        await db.commit()
        print("\n✅ Tous les agents spécialisés et politiques RBAC sont configurés avec succès !")


if __name__ == "__main__":
    asyncio.run(seed_agents())
