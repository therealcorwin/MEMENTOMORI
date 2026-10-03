"""
Met à jour le mot de passe de l'administrateur akadmin dans Authentik
en utilisant la valeur définie dans le fichier .env.
"""

import subprocess
from dotenv import dotenv_values

config = dotenv_values(".env")
admin_pwd = config.get("AUTHENTIK_ADMIN_PASSWORD")

if not admin_pwd:
    print("Erreur: AUTHENTIK_ADMIN_PASSWORD non trouvé dans .env")
    exit(1)

code = f"""
from authentik.core.models import User
u = User.objects.get(username="akadmin")
u.set_password("{admin_pwd}")
u.save()
print("AKADMIN_PASSWORD_UPDATED_SUCCESS")
"""

proc = subprocess.run(
    ["docker", "exec", "-i", "mementomori-authentik-server", "ak", "shell"],
    input=code.encode("utf-8"),
    capture_output=True,
)
output = proc.stdout.decode("utf-8", errors="ignore")
print(output)
if "AKADMIN_PASSWORD_UPDATED_SUCCESS" in output:
    print("Succès : Le mot de passe de akadmin a été synchronisé avec .env !")
else:
    print("Erreur lors de la mise à jour :", proc.stderr.decode("utf-8", errors="ignore"))
