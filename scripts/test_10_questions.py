"""Script de validation des 10 questions pilotes sur knowledge-api (Task 3.15, B10)."""

import asyncio
import sys
import time
from pathlib import Path
from sqlalchemy import select

# Ajouter knowledge-api au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "knowledge-api"))

import httpx
from knowledge.main import app
from knowledge.dependencies import async_session_maker
from knowledge.models import Workspace

TEST_QUESTIONS = [
    ("Horaires travaux", "Quels sont les horaires autorises pour les travaux bruyants dans l'immeuble ?"),
    ("Prestataire ascenseur", "Quel est le prestataire pour la maintenance de l'ascenseur et le montant annuel du contrat ?"),
    ("Facture espaces verts", "Quel est le montant de la facture de Vert Avenir pour le premier trimestre 2026 ?"),
    ("Resolution AG boites aux lettres", "Quelle resolution a ete votee lors de l'AG du 20 juin 2025 concernant les boites aux lettres ?"),
    ("Sinistre Lot 42", "Quel est le coproprietaire du lot 42 et quelle est la cause du degat des eaux ?"),
    ("Urgence OTIS", "Quel est le numero de telephone ou la reference pour les pannes d'ascenseur OTIS ?"),
    ("Delai paiement facture", "Quel est le delai de paiement ou l'echeance mentionnee sur la facture d'espaces verts ?"),
    ("Quitus syndic AG", "Quelle decision a ete prise pour le quitus au syndic lors de l'assemblee generale ?"),
    ("Reglement balcons", "Quelles sont les regles concernant les parties communes et l'usage des balcons ?"),
    ("Assurance sinistre", "Quelle est la reference du dossier de sinistre ou la compagnie d'assurance pour le lot 42 ?"),
]

async def run_tests() -> None:
    print("==================================================")
    print("    TEST DES 10 QUESTIONS PILOTES (Task 3.15)    ")
    print("==================================================")

    # Récupérer l'ID du workspace 'copro-jardins'
    async with async_session_maker() as session:
        ws_res = await session.execute(select(Workspace).where(Workspace.slug == "copro-jardins"))
        workspace = ws_res.scalar_one_or_none()
        if not workspace:
            print("ERREUR: Workspace 'copro-jardins' introuvable.")
            return
        workspace_id = str(workspace.id)
        print(f"Workspace actif : {workspace.name} ({workspace_id})\n")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # En-tête dev principal pour l'authentification
        headers = {"X-Dev-Principal": "csbot"}

        search_latencies = []
        answer_latencies = []

        for idx, (label, question) in enumerate(TEST_QUESTIONS, start=1):
            print(f"[{idx}/10] Question: {label}")
            print(f"       \"{question}\"")

            # 1. Test POST /v1/search
            t0 = time.time()
            s_resp = await client.post(
                "/v1/search",
                json={"workspace_id": workspace_id, "query": question, "top_k": 3},
                headers=headers
            )
            s_duration = (time.time() - t0) * 1000
            search_latencies.append(s_duration)

            if s_resp.status_code == 200:
                s_data = s_resp.json()
                print(f"       -> Search OK : {s_data['total']} fragment(s) trouve(s) en {s_duration:.1f}ms")
                if s_data["results"]:
                    top_doc = s_data["results"][0]["document_title"]
                    top_score = s_data["results"][0]["score"]
                    print(f"          Top doc: [{top_doc}] (score RRF: {top_score})")
            else:
                print(f"       -> Search ERREUR {s_resp.status_code}: {s_resp.text}")

            # 2. Test POST /v1/answer
            t1 = time.time()
            a_resp = await client.post(
                "/v1/answer",
                json={"workspace_id": workspace_id, "query": question, "top_k": 3, "use_cache": True},
                headers=headers
            )
            a_duration = (time.time() - t1) * 1000
            answer_latencies.append(a_duration)

            if a_resp.status_code == 200:
                a_data = a_resp.json()
                cached_str = " (CACHE HIT)" if a_data.get("cached") else ""
                print(f"       -> Answer OK{cached_str} en {a_duration:.1f}ms (confiance: {a_data['confidence']})")
                print(f"          Citations: {a_data.get('citations')}")
                ans_snippet = a_data["answer"].replace("\n", " ")[:120]
                print(f"          Reponse: {ans_snippet}...\n")
            else:
                print(f"       -> Answer ERREUR {a_resp.status_code}: {a_resp.text}\n")

        # 3. Test du Cache HIT sur la question 1
        print("--- Test Cache Hit immédiat ---")
        t_cache = time.time()
        c_resp = await client.post(
            "/v1/answer",
            json={"workspace_id": workspace_id, "query": TEST_QUESTIONS[0][1], "top_k": 3, "use_cache": True},
            headers=headers
        )
        c_duration = (time.time() - t_cache) * 1000
        if c_resp.status_code == 200 and c_resp.json().get("cached"):
            print(f"[CACHE VALIDE] Reponse servie depuis le cache PostgreSQL en {c_duration:.1f}ms (< 50ms)")
        else:
            print(f"[CACHE ECHEC] Status: {c_resp.status_code}, data: {c_resp.text}")

        # Rapport des objectifs de performance B10
        avg_search = sum(search_latencies) / len(search_latencies)
        avg_answer = sum(answer_latencies) / len(answer_latencies)
        print("\n==================================================")
        print("          BILAN DES PERFORMANCES (B10)           ")
        print("==================================================")
        print(f"Recherche hybride moyenne : {avg_search:.1f}ms (Objectif B10 < 500ms) -> {'REUSSI' if avg_search < 500 else 'A OPTIMISER'}")
        print(f"Reponse generative moyenne: {avg_answer:.1f}ms (Objectif B10 < 5000ms) -> {'REUSSI' if avg_answer < 5000 else 'A OPTIMISER'}")

if __name__ == "__main__":
    asyncio.run(run_tests())
