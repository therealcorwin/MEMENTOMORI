import os
import sys
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
DOMAIN = os.getenv("DOMAIN", "csrgb.ovh")
ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
ACCOUNT_ID = "bbeaa39b8331a6a70f64dd002f2eced8"
TUNNEL_ID = "17e82e96-cdc8-4f57-8a7b-8d97f8c9dbf5"

if not API_TOKEN:
    print("Error: CLOUDFLARE_API_TOKEN is missing in .env")
    sys.exit(1)

def cf_request(endpoint, method="GET", data=None):
    url = f"https://api.cloudflare.com/client/v4{endpoint}"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(error_body)
            print(f"HTTPError {e.code} on {endpoint}: {json.dumps(err_json, indent=2)}")
        except Exception:
            print(f"HTTPError {e.code} on {endpoint}: {error_body}")
        raise e

# 1. Update Ingress configuration on tunnel
print("--- 1. Configuration des routes Ingress du Tunnel ---")
subdomains = ["dashboard", "api", "auth", "paperless"]
ingress_rules = []
for sub in subdomains:
    ingress_rules.append({
        "hostname": f"{sub}.{DOMAIN}",
        "service": "https://traefik:443",
        "originRequest": {
            "noTLSVerify": True
        }
    })
ingress_rules.append({"service": "http_status:404"})

payload = {
    "config": {
        "ingress": ingress_rules
    }
}

try:
    res = cf_request(f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}/configurations", method="PUT", data=payload)
    print("SUCCESS: Ingress tunnel mis a jour sur Cloudflare !")
except Exception as e:
    print(f"Erreur ingress: {e}")

# 2. Add DNS CNAMEs if ZONE_ID is provided
cname_target = f"{TUNNEL_ID}.cfargotunnel.com"

if not ZONE_ID:
    print(f"\n--- Information DNS ---")
    print(f"Pour finaliser, les enregistrements CNAME suivants doivent pointer vers : {cname_target}")
    for sub in subdomains:
        print(f" - {sub}.{DOMAIN} -> {cname_target} (Proxy ON)")
    print("\nAstuce: Ajoutez CLOUDFLARE_ZONE_ID=... dans votre .env pour que je cree ces CNAMEs automatiquement !")
    sys.exit(0)

print(f"\n--- 2. Creation / Verification des CNAMEs dans la zone {ZONE_ID} ---")
try:
    res = cf_request(f"/zones/{ZONE_ID}/dns_records?type=CNAME")
    existing_cnames = {r["name"]: r for r in res.get("result", [])}

    for sub in subdomains:
        full_host = f"{sub}.{DOMAIN}"
        if full_host in existing_cnames:
            rec = existing_cnames[full_host]
            if rec["content"] != cname_target or not rec.get("proxied"):
                print(f"Mise a jour du CNAME pour {full_host} -> {cname_target}")
                cf_request(f"/zones/{ZONE_ID}/dns_records/{rec['id']}", method="PATCH", data={
                    "type": "CNAME",
                    "name": full_host,
                    "content": cname_target,
                    "proxied": True
                })
            else:
                print(f"CNAME {full_host} -> {cname_target} deja OK.")
        else:
            print(f"Creation du CNAME pour {full_host} -> {cname_target}")
            cf_request(f"/zones/{ZONE_ID}/dns_records", method="POST", data={
                "type": "CNAME",
                "name": full_host,
                "content": cname_target,
                "proxied": True
            })

    print("\n=== SUCCES TOTAL : Tous les sous-domaines et le tunnel sont operationnels ! ===")
except Exception as e:
    print(f"Erreur lors de la gestion DNS: {e}")

