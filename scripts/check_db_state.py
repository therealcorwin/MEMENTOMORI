import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def main():
    pw = os.getenv("KNOWLEDGE_DB_PASSWORD")
    conn = await asyncpg.connect(f"postgresql://knowledge_app:{pw}@localhost:5433/knowledge")
    try:
        workspaces = await conn.fetch("SELECT id, slug, name FROM workspaces")
        print(f"Workspaces ({len(workspaces)}):")
        for w in workspaces:
            print(f"  - {w['slug']} ({w['id']}): {w['name']}")

        principals = await conn.fetch("SELECT id, external_id, display_name, type FROM principals")
        print(f"\nPrincipals ({len(principals)}):")
        for p in principals:
            print(f"  - {p['external_id']} ({p['id']}): type={p['type']}, name={p['display_name']}")

        policies = await conn.fetch("SELECT id, workspace_id, principal_id, role, allowed_scopes, max_sensitivity FROM policies")
        print(f"\nPolicies ({len(policies)}):")
        for pol in policies:
            print(f"  - ws={pol['workspace_id']} principal={pol['principal_id']} role={pol['role']} scopes={pol['allowed_scopes']} max_sens={pol['max_sensitivity']}")

        docs = await conn.fetch("SELECT id, title, scope, sensitivity, status FROM documents")
        print(f"\nDocuments ({len(docs)}):")
        for d in docs:
            print(f"  - {d['title']}: scope={d['scope']}, sens={d['sensitivity']}, status={d['status']}")

        audits = await conn.fetchval("SELECT count(*) FROM audit_log")
        print(f"\nAudit log entries: {audits}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
