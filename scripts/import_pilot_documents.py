"""
Script d'importation des 5 documents pilotes de copropriété pour Paperless-ngx (Sprint 2).
Génère 5 PDF réalistes et les envoie via l'API REST de Paperless.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
import urllib.parse
import urllib.request
import uuid
from dotenv import dotenv_values


def make_pdf(lines: list[str], title: str) -> bytes:
    """Génère un PDF standard v1.4 propre sans dépendance externe."""
    stream_content = "BT /F1 14 Tf 50 780 Td 20 TL\n"
    safe_title = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream_content += f"({safe_title}) Tj T* T*\n/F1 10 Tf 14 TL\n"

    for line in lines:
        safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        # Remplacement des caractères non-latin1 pour conformité PDF Type1 Helvetica
        safe_line = (
            safe_line.replace("é", "e")
            .replace("è", "e")
            .replace("ê", "e")
            .replace("à", "a")
            .replace("ç", "c")
            .replace("ù", "u")
            .replace("î", "i")
            .replace("ï", "i")
            .replace("ô", "o")
            .replace("°", "o")
            .replace("€", "EUR")
            .replace("’", "'")
        )
        stream_content += f"({safe_line}) Tj T*\n"
    stream_content += "ET"
    stream_bytes = stream_content.encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
        + stream_bytes
        + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    out = b"%PDF-1.4\n"
    offsets = []
    for obj in objects:
        offsets.append(len(out))
        out += obj

    xref_offset = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    return out


PILOT_DOCUMENTS = [
    {
        "filename": "reglement_copro_jardins_provence.pdf",
        "title": "Reglement de Copropriete - Les Jardins de Provence",
        "doc_type": "Règlement",
        "tags": ["ws:copro-jardins", "scope:collectif", "sens:public"],
        "lines": [
            "COPROPRIETE LES JARDINS DE PROVENCE - 12 Rue des Fleurs, 13000 Marseille",
            "REGLEMENT DE COPROPRIETE ET ETAT DESCRIPTIF DE DIVISION",
            "--------------------------------------------------------------------------------",
            "CHAPITRE I : DESTINATION DE L'IMMEUBLE",
            "Article 1 : L'immeuble est destine a l'usage exclusif d'habitation bourgeoise.",
            "L'exercice de professions liberales est autorise sous reserve d'absence de nuisances.",
            "",
            "CHAPITRE II : PARTIES COMMUNES ET PARTIES PRIVATIVES",
            "Article 4 : Sont communes les parties comprenant le gros oeuvre, les coursives,",
            "les halls d'entree, les escaliers, l'ascenseur, le local velos et les espaces verts.",
            "",
            "CHAPITRE III : REPARTITION DES CHARGES",
            "Article 12 : Les charges generales sont reparties selon la quote-part des parties communes.",
            "Lot 42 : Appartement de type 3 au 2eme etage du Batiment A.",
            "- Quote-part charges generales de copropriete : 45 / 1000emes.",
            "- Quote-part charges d'ascenseur : 52 / 1000emes.",
            "- Quote-part chauffage collectif : 48 / 1000emes.",
            "",
            "CHAPITRE IV : VIE COMMUNE",
            "Article 18 : Les animaux domestiques sont toleres a condition de ne causer aucun trouble.",
            "Tout encombrement des paliers et des parties communes est strictement prohibe.",
        ],
    },
    {
        "filename": "contrat_maintenance_ascenseur_otis_2026.pdf",
        "title": "Contrat de maintenance ascenseur OTIS 2026",
        "doc_type": "Contrat",
        "tags": ["ws:copro-jardins", "scope:cs", "sens:interne"],
        "lines": [
            "CONTRAT DE MAINTENANCE COMPLETE D'ASCENSEUR",
            "Ref Contrat: OTIS-MARS-2026-78492",
            "--------------------------------------------------------------------------------",
            "ENTRE LES SOUSSIGNES :",
            "- Le Syndicat des Coproprietaires Les Jardins de Provence, represente par son Syndic.",
            "- La Societe OTIS Ascenseurs SAS, 14 Avenue des Artisans, 13008 Marseille.",
            "",
            "OBJET DU CONTRAT :",
            "Maintenance preventive et corrective de l'ascenseur electrique 8 personnes Batiment A.",
            "",
            "CONDITIONS GENERALES D'INTERVENTION :",
            "- Telealarme reliee au centre de telesurveillance 24h/24 et 7j/7.",
            "- Assistance depannage prioritaire : intervention garantie sous 45 minutes pour desincarceration.",
            "- Visites de controle preventif : 1 passage toutes les 6 semaines (8 visites annuelles).",
            "",
            "CONDITIONS FINANCIERES :",
            "- Redevance forfaitaire annuelle : 3 600,00 EUR HT (soit 4 320,00 EUR TTC).",
            "- Facturation trimestrielle echue : 900,00 EUR HT par trimestre.",
            "- Duree : Contrat initial de 3 ans prenant effet le 01/01/2026 jusqu'au 31/12/2028.",
        ],
    },
    {
        "filename": "facture_vert_avenir_espaces_verts_2026_T1.pdf",
        "title": "Facture Entretien Espaces Verts - Vert Avenir T1 2026",
        "doc_type": "Facture",
        "tags": ["ws:copro-jardins", "scope:cs", "sens:interne"],
        "lines": [
            "VERT AVENIR SARL - Paysagiste & Espaces Verts",
            "FACTURE N° FAC-2026-089 - Date : 15/03/2026",
            "--------------------------------------------------------------------------------",
            "DOIT : Syndicat des Coproprietaires Les Jardins de Provence",
            "Adresse : 12 Rue des Fleurs, 13000 Marseille",
            "",
            "DESIGNATION DES PRESTATIONS REALISEES (Trimestre 1 - 2026) :",
            "1. Tonte des pelouses et ramassage des dechets verts (2 passages en mars) : 450,00 EUR HT",
            "2. Taille des haies de lauriers et des arbustes d'ornement : 380,00 EUR HT",
            "3. Desherbage manuel et binage des massifs fleuris de l'entree : 211,67 EUR HT",
            "",
            "RECAPITULATIF FINANCIER :",
            "- Total Hors Taxes (HT) : 1 041,67 EUR",
            "- Taux TVA 20.0% : 208,33 EUR",
            "- TOTAL NET A PAYER TTC : 1 250,00 EUR",
            "",
            "Conditions de reglement : sous 30 jours, virement a l'ordre de Vert Avenir SARL.",
            "IBAN : FR76 3000 4000 1234 5678 9012 345 - BIC : BNPAFRPP",
        ],
    },
    {
        "filename": "pv_ag_ordinaire_2025_jardins_provence.pdf",
        "title": "Proces-Verbal Assemblee Generale Ordinaire 20 juin 2025",
        "doc_type": "Procès-Verbal",
        "tags": ["ws:copro-jardins", "scope:collectif", "sens:public"],
        "lines": [
            "SYNDICAT DES COPROPRIETAIRES LES JARDINS DE PROVENCE",
            "PROCES-VERBAL DE L'ASSEMBLEE GENERALE ORDINAIRE DU 20 JUIN 2025",
            "--------------------------------------------------------------------------------",
            "L'Assemblee Generale s'est tenue a Marseille au siege du syndic.",
            "Nombre total de tantiemes presents ou representes : 820 / 1000emes. Le quorum est atteint.",
            "",
            "RESOLUTION N° 1 : Approbation des comptes de l'exercice 2024 clos au 31/12/2024.",
            "Comptes arretes a la somme de 46 210 EUR. Resolution approuvee a l'unanimite (820 voix).",
            "",
            "RESOLUTION N° 2 : Quitus au syndic Cabinet Mer & Soleil pour sa gestion 2024.",
            "Resolution approuvee a la majorite de l'article 24 avec 780 voix pour et 40 voix contre.",
            "",
            "RESOLUTION N° 3 : Vote du budget previsionnel pour l'exercice 2026.",
            "Montant total du budget approuve : 48 000,00 EUR. Resolution adoptee a l'unanimite.",
            "",
            "RESOLUTION N° 4 : Renouvellement du Conseil Syndical.",
            "Sont elus membres titulaires : M. Pierre Dupont (Lot 12), Mme Sophie Laurent (Lot 28),",
            "et M. Alexandre Garcia (proprietaire du Lot 42). Resolution approuvee a 820 voix.",
            "",
            "RESOLUTION N° 5 : Travaux de refection de la toiture terrasse.",
            "Apres examen des devis, l'assemblee decide de reporter le vote a l'AG de 2026.",
        ],
    },
    {
        "filename": "declaration_sinistre_dde_lot42_fevrier2026.pdf",
        "title": "Declaration sinistre degat des eaux Lot 42 - Fevrier 2026",
        "doc_type": "Sinistre",
        "tags": ["ws:copro-jardins", "scope:cs", "sens:interne"],
        "lines": [
            "DECLARATION DE SINISTRE - DEGAT DES EAUX",
            "Ref Dossier : DDE-2026-4412 / Police AXA Assurances N° 987654321",
            "--------------------------------------------------------------------------------",
            "Date du sinistre : Constate le 10 fevrier 2026 a 09h00.",
            "Lieu du sinistre : Appartement Lot 42 (2eme etage Bat A, occupant : M. Garcia).",
            "",
            "ORIGINE DE LA FUITE :",
            "Rupture d'un joint d'evacuation sous le bac a douche de l'appartement Lot 52 (3eme etage).",
            "Fuite accidentelle d'eau propre ayant traverse la dalle de separation.",
            "",
            "DEGATS CONSTATES :",
            "- Peintures cloquees et platre degrade sur le plafond de l'entree du Lot 42.",
            "- Infiltration le long de la cloison separative cuisine / sejour.",
            "",
            "MESURES PRISES ET SUIVI :",
            "- Intervention d'urgence de la societe Plomberie Express le 10/02 a 14h (vanne coupee).",
            "- Constat amiable DDE signe conjointement entre le Lot 42 et le Lot 52 le 11/02/2026.",
            "- Devis de remise en etat de la plomberie : 480,00 EUR TTC pris en charge.",
            "- Devis peinture et remise en etat des embellissements : 1 150,00 EUR TTC (en cours d'expertise).",
        ],
    },
]


def post_to_paperless(api_url: str, token: str, doc: dict) -> dict:
    pdf_bytes = make_pdf(doc["lines"], doc["title"])

    # 1. Obtenir les IDs des tags et du document_type
    req_tags = urllib.request.Request(
        f"{api_url}/api/tags/", headers={"Authorization": f"Token {token}"}
    )
    with urllib.request.urlopen(req_tags) as resp:
        tags_data = json.loads(resp.read().decode("utf-8"))
        tag_map = {t["name"]: t["id"] for t in tags_data.get("results", [])}

    req_types = urllib.request.Request(
        f"{api_url}/api/document_types/", headers={"Authorization": f"Token {token}"}
    )
    with urllib.request.urlopen(req_types) as resp:
        types_data = json.loads(resp.read().decode("utf-8"))
        type_map = {dt["name"]: dt["id"] for dt in types_data.get("results", [])}

    tag_ids = [tag_map[t] for t in doc["tags"] if t in tag_map]
    doc_type_id = type_map.get(doc["doc_type"])

    # 2. Construction d'une requête multipart/form-data
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    def add_field(name: str, value: str):
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    def add_file(name: str, filename: str, file_bytes: bytes):
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(
                "utf-8"
            )
        )
        body.extend(b"Content-Type: application/pdf\r\n\r\n")
        body.extend(file_bytes)
        body.extend(b"\r\n")

    add_field("title", doc["title"])
    if doc_type_id:
        add_field("document_type", str(doc_type_id))
    for tid in tag_ids:
        add_field("tags", str(tid))
    add_file("document", doc["filename"], pdf_bytes)
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        f"{api_url}/api/documents/post_document/",
        data=body,
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    config = dotenv_values(root_dir / ".env")
    token = config.get("PAPERLESS_API_TOKEN")
    api_url = "http://localhost:8000"

    if not token:
        print("Erreur: PAPERLESS_API_TOKEN introuvable dans .env")
        return

    print("=== Importation des 5 documents pilotes dans Paperless-ngx ===")
    for doc in PILOT_DOCUMENTS:
        try:
            task_id = post_to_paperless(api_url, token, doc)
            print(f"Envoyé : '{doc['title']}' -> Tâche Paperless ID: {task_id}")
        except Exception as e:
            print(f"Erreur pour '{doc['title']}': {e}")

    print("\nTous les documents ont été soumis au moteur d'ingestion et d'OCR de Paperless.")


if __name__ == "__main__":
    main()
