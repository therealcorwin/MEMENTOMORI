"""
Configuration de la passerelle d'ingestion email IMAP dans Paperless-ngx (Sprint 11, Tâche 11.4).
Configure le compte IMAP sécurisé (si renseigné dans .env ou placeholder modèle) et les règles
automatiques de routage des pièces jointes (factures d'énergie, contrats de maintenance, devis, PV d'AG).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ajout du chemin knowledge-api
sys.path.insert(0, str(Path(__file__).parent.parent / "knowledge-api"))

load_dotenv()


def setup_paperless_mail():
    from documents.models import DocumentType, Tag
    from paperless_mail.models import MailAccount, MailRule

    print("=" * 70)
    print("MEMENTOMORI - Configuration Passerelle Ingestion IMAP / Email (Pipeline-Email)")
    print("=" * 70)

    # 1. Configuration / Récupération du Compte IMAP
    imap_host = os.getenv("PAPERLESS_EMAIL_HOST") or "imap.csrgb.ovh"
    imap_user = os.getenv("PAPERLESS_EMAIL_USER") or "factures@csrgb.ovh"
    imap_password = os.getenv("PAPERLESS_EMAIL_PASSWORD") or "change_me_imap_password"
    imap_port = int(os.getenv("PAPERLESS_EMAIL_PORT", "993"))

    has_real_creds = bool(os.getenv("PAPERLESS_EMAIL_HOST") and os.getenv("PAPERLESS_EMAIL_USER"))
    mode_str = "RÉEL" if has_real_creds else "MODÈLE D'INTÉGRATION"
    print(f"[+] Compte IMAP [{mode_str}] : {imap_user} @ {imap_host}:{imap_port}...")

    mail_account, created = MailAccount.objects.get_or_create(
        name="Boîte Mail Factures Copropriété",
        defaults={
            "imap_server": imap_host,
            "imap_port": imap_port,
            "imap_security": 1,  # SSL
            "username": imap_user,
            "password": imap_password,
        }
    )
    if not created and has_real_creds:
        mail_account.imap_server = imap_host
        mail_account.imap_port = imap_port
        mail_account.username = imap_user
        mail_account.password = imap_password
        mail_account.save()
    print(f"  [OK] Compte IMAP ID [{mail_account.id}] prêt.")

    # 2. Récupération des tags et types
    tag_copro, _ = Tag.objects.get_or_create(name="ws:copro")
    tag_cs, _ = Tag.objects.get_or_create(name="scope:cs")
    tag_coll, _ = Tag.objects.get_or_create(name="scope:collectif")
    tag_interne, _ = Tag.objects.get_or_create(name="sens:interne")
    tag_public, _ = Tag.objects.get_or_create(name="sens:public")

    type_facture, _ = DocumentType.objects.get_or_create(name="Facture")
    type_contrat, _ = DocumentType.objects.get_or_create(name="Contrat")
    type_pv, _ = DocumentType.objects.get_or_create(name="Procès-Verbal")

    # 3. Règle 1 : Factures des prestataires et syndic
    print("\n[+] Configuration de la règle : Factures Fournisseurs & Syndic...")
    rule_factures, created_f = MailRule.objects.get_or_create(
        name="Règle Factures Fournisseurs & Syndic",
        account=mail_account,
        defaults={
            "order": 1,
            "enabled": True,
            "folder": "INBOX",
            "filter_attachment_filename_include": "*.pdf,*.PDF",
            "consumption_scope": 1,  # Pièces jointes uniquement
            "assign_document_type": type_facture,
            "action": 1,  # Marquer comme lu
        }
    )
    rule_factures.assign_tags.set([tag_copro, tag_cs, tag_interne])
    rule_factures.save()
    print(f"  [OK] Règle Factures ({'créée' if created_f else 'mise à jour'}) : taguée ws:copro, scope:cs, Facture.")

    # 4. Règle 2 : Contrats et devis
    print("\n[+] Configuration de la règle : Contrats & Devis de Maintenance...")
    rule_contrats, created_c = MailRule.objects.get_or_create(
        name="Règle Contrats & Devis",
        account=mail_account,
        defaults={
            "order": 2,
            "enabled": True,
            "folder": "INBOX",
            "filter_subject": "contrat,devis,avenant",
            "filter_attachment_filename_include": "*.pdf,*.PDF",
            "consumption_scope": 1,
            "assign_document_type": type_contrat,
            "action": 1,
        }
    )
    rule_contrats.assign_tags.set([tag_copro, tag_cs, tag_interne])
    rule_contrats.save()
    print(f"  [OK] Règle Contrats ({'créée' if created_c else 'mise à jour'}) : taguée ws:copro, scope:cs, Contrat.")

    # 5. Règle 3 : PV d'Assemblées Générales et convocations
    print("\n[+] Configuration de la règle : Convocations & PV d'Assemblées Générales...")
    rule_pv, created_p = MailRule.objects.get_or_create(
        name="Règle Assemblées Générales & PV",
        account=mail_account,
        defaults={
            "order": 3,
            "enabled": True,
            "folder": "INBOX",
            "filter_subject": "ag,assemblee,convocation,pv,proces-verbal",
            "filter_attachment_filename_include": "*.pdf,*.PDF",
            "consumption_scope": 1,
            "assign_document_type": type_pv,
            "action": 1,
        }
    )
    rule_pv.assign_tags.set([tag_copro, tag_coll, tag_public])
    rule_pv.save()
    print(f"  [OK] Règle AG/PV ({'créée' if created_p else 'mise à jour'}) : taguée ws:copro, scope:collectif, Procès-Verbal.")

    print("\n" + "=" * 70)
    print("[SUCCÈS] Règles de routage email Paperless opérationnelles !")
    print("=" * 70)


setup_paperless_mail()

