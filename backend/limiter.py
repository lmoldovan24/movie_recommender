"""
backend/limiter.py — Rate limiting configurabil și rezistent la XFF spoofing.

Problema get_ipaddr (slowapi default):
  Citește primul IP din X-Forwarded-For, pe care clientul îl poate seta liber
  (ex: X-Forwarded-For: 1.2.3.4) → bypass complet al rate limiting-ului.

Soluție implementată:
  Funcție _get_client_ip care aplică logica corectă în funcție de context:
  - Fără proxy configurat → IP-ul conexiunii directe (cel mai sigur)
  - Cu proxy de încredere (TRUSTED_PROXIES în .env):
      * Cloudflare → CF-Connecting-IP (header proprietar, mai greu de spoof-uit)
      * Nginx/ALB  → ultimul IP din XFF (adăugat de proxy, nu de client)

Configurare în .env:
  TRUSTED_PROXIES=127.0.0.1,10.0.0.1    # IP-urile serverelor proxy
  # Fără TRUSTED_PROXIES → fără proxy (localhost direct sau dev)
"""

from fastapi import Request
from slowapi import Limiter

from backend.config import settings


def _get_client_ip(request: Request) -> str:
    """
    Extrage IP-ul real al clientului cu protecție împotriva XFF spoofing.

    Logica:
    1. Fără proxy de încredere configurat → IP direct (request.client.host).
    2. Cu proxy de încredere și IP direct în TRUSTED_PROXIES:
       a. Cloudflare: header CF-Connecting-IP (proprietar, nu e trimis de clienți obișnuiți)
       b. Nginx/ALB: ultimul IP din X-Forwarded-For (adăugat de proxy, nu de client)
       c. Fallback: IP-ul conexiunii directe
    3. IP direct NU e în TRUSTED_PROXIES → ignor XFF (posibil spoofing)
    """
    direct_ip = request.client.host if request.client else "unknown"
    trusted = settings.trusted_proxies_set

    if not trusted or direct_ip not in trusted:
        # Conexiune directă sau proxy necunoscut — folosim IP-ul real al conexiunii
        return direct_ip

    # Cloudflare: header proprietar, injectat de Cloudflare, ignorat de browsere
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # Nginx / AWS ALB: proxy adaugă IP-ul clientului la SFÂRȘITUL X-Forwarded-For.
    # Luăm ultimul IP — cel adăugat de proxy-ul nostru de încredere.
    # Clientul poate falsifica primele IP-uri din XFF, dar nu ultimul.
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[-1].strip()

    return direct_ip


limiter = Limiter(key_func=_get_client_ip)
