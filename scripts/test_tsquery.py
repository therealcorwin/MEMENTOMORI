import asyncio
import os
import re
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def main():
    pw = os.getenv("KNOWLEDGE_DB_PASSWORD")
    conn = await asyncpg.connect(f"postgresql://knowledge_app:{pw}@localhost:5433/knowledge")
    try:
        q = "Quels degats ont ete constates dans le logement du Lot 42 ?"
        
        # Clean words
        stop_words = {"quel", "quelle", "quels", "quelles", "dans", "pour", "cette", "sont", "avec", "est", "les", "des", "une", "par", "sur", "ont", "ete", "qui"}
        tokens = re.findall(r'\b[a-zA-Z0-9_]{3,}\b', q.lower())
        meaningful = [t for t in tokens if t not in stop_words]
        print("Meaningful tokens:", meaningful)

        or_tsquery = " | ".join(meaningful)
        print("or_tsquery:", or_tsquery)

        hits = await conn.fetch(
            "SELECT f.id, d.title, ts_rank(f.search_vector, to_tsquery('french', $1)) as rank "
            "FROM fragments f JOIN document_versions dv ON f.document_version_id = dv.id "
            "JOIN documents d ON dv.document_id = d.id "
            "WHERE f.search_vector @@ to_tsquery('french', $1) "
            "ORDER BY rank DESC LIMIT 5",
            or_tsquery
        )
        print(f"Hits with OR tsquery ({len(hits)}):")
        for h in hits:
            print(f"  - {h['title']} (rank={h['rank']:.4f})")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
