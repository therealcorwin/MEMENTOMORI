import os
import sys
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
ACCOUNT_ID = "bbeaa39b8331a6a70f64dd002f2eced8"
TUNNEL_ID = "17e82e96-cdc8-4f57-8a7b-8d97f8c9dbf5"

if not API_TOKEN or not ZONE_ID:
    print("Error: Missing credentials in .env")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# 1. Delete DNS records from zone
to_delete = ["dashboard.csrgb.ovh", "paperless.csrgb.ovh"]
req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records", headers=headers)
records = json.loads(urllib.request.urlopen(req).read().decode()).get("result", [])

deleted_count = 0
for r in records:
    if r.get("name") in to_delete:
        rec_id = r["id"]
        rec_name = r["name"]
        del_req = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{rec_id}",
            headers=headers,
            method="DELETE"
        )
        del_res = json.loads(urllib.request.urlopen(del_req).read().decode())
        print(f"DNS CNAME supprime: {rec_name} (succes: {del_res.get('success')})")
        deleted_count += 1

if deleted_count == 0:
    print("Aucun enregistrement DNS a supprimer trouve dans la zone.")

# 2. Update Tunnel Ingress configuration
print("\n--- Mise a jour des regles Ingress du Tunnel ---")
ingress_rules = [
    {
        "hostname": "api.csrgb.ovh",
        "service": "https://traefik:443",
        "originRequest": {"noTLSVerify": True}
    },
    {
        "hostname": "auth.csrgb.ovh",
        "service": "https://traefik:443",
        "originRequest": {"noTLSVerify": True}
    },
    {
        "service": "http_status:404"
    }
]

payload = json.dumps({"config": {"ingress": ingress_rules}}).encode("utf-8")
put_req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}/configurations",
    data=payload,
    headers=headers,
    method="PUT"
)
put_res = json.loads(urllib.request.urlopen(put_req).read().decode())
print(f"Regles Ingress du tunnel mises a jour (succes: {put_res.get('success')})")

print("\n=== SUCCES : dashboard et paperless retires de Cloudflare ! ===")

