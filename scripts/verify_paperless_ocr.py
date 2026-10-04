import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("PAPERLESS_API_TOKEN")
headers = {"Authorization": f"Token {token}"}

url = "http://localhost:8000/api/documents/"
resp = requests.get(url, headers=headers)

if resp.status_code == 200:
    data = resp.json()
    print(f"Total documents dans Paperless : {data['count']}\n")
    for doc in data["results"]:
        content_snippet = (doc.get("content") or "").replace("\n", " ")[:120]
        print(f"- [ID {doc['id']}] {doc['title']}")
        print(f"  Type doc: {doc.get('document_type')}, Tags: {doc.get('tags')}")
        print(f"  Extrait OCR: {content_snippet}...\n")
        
    # Test recherche plein texte
    test_queries = ["ascenseur", "lot 42", "Vert Avenir", "copropriété"]
    print("--- Test Recherche Plein Texte ---")
    for query in test_queries:
        search_resp = requests.get(f"{url}?query={query}", headers=headers)
        if search_resp.status_code == 200:
            s_data = search_resp.json()
            print(f"Requête '{query}' -> {s_data['count']} résultat(s)")
            for r in s_data["results"]:
                print(f"   -> Trouvé dans doc ID {r['id']}: {r['title']}")
        else:
            print(f"Erreur recherche '{query}': {search_resp.status_code}")
else:
    print(f"Erreur HTTP {resp.status_code} : {resp.text}")
