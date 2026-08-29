# core/auth.py
#
# Authentification par magic link (pas de mot de passe) + sessions
# cookie. Envoi d'email via Resend (https://resend.com).
#
# Variables d'environnement :
#   RESEND_API_KEY       — clé API Resend
#   RESEND_FROM_EMAIL     — ex: "Pelify <login@pelify.app>" (domaine vérifié sur Resend)
#   APP_BASE_URL          — ex: "https://pelify.app" (pour construire le lien du mail)
#   SESSION_COOKIE_SECURE — "false" en local, "true" en prod (défaut: true)

import os
import httpx
from fastapi import Request

from storage.cache_engine import users_db

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "Pelify <login@pelify.app>")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://pelify.app")
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() != "false"

SESSION_COOKIE_NAME = "pelify_session"


async def send_magic_link_email(email: str, token: str, code: str) -> bool:
    """Envoie le mail de connexion via Resend. Retourne False si l'envoi échoue
    (l'appelant doit alors répondre une erreur claire à l'utilisateur, pas
    faire semblant que ça a marché)."""
    if not RESEND_API_KEY:
        print("⚠️ auth: RESEND_API_KEY manquant, email non envoyé", flush=True)
        return False

    link = f"{APP_BASE_URL}/auth/verify?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2>Connexion à Pelify</h2>
      <p>Clique sur le lien ci-dessous pour te connecter (valable 15 minutes) :</p>
      <p><a href="{link}" style="background:#6c5ce7;color:#fff;padding:12px 20px;
         border-radius:8px;text-decoration:none;display:inline-block">Se connecter</a></p>
      <p style="color:#888;font-size:13px;margin-top:16px">
        Le lien s'ouvre parfois dans le navigateur intégré de ton app mail, qui
        ne te reconnaît pas ensuite sur ton navigateur habituel. Dans ce cas,
        entre plutôt ce code directement sur pelify.app :
      </p>
      <p style="font-size:28px;font-weight:700;letter-spacing:4px;
         background:#f4f4f4;padding:12px 16px;border-radius:8px;text-align:center;
         color:#111">{code}</p>
      <p style="color:#888;font-size:13px">Si tu n'es pas à l'origine de cette demande, ignore cet email.</p>
    </div>
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": RESEND_FROM_EMAIL,
                    "to": [email],
                    "subject": "Ton lien de connexion Pelify",
                    "html": html,
                },
            )
            if resp.status_code >= 300:
                print(f"⚠️ auth: Resend KO {resp.status_code} {resp.text[:200]}", flush=True)
                return False
            return True
    except Exception as e:
        print(f"⚠️ auth: envoi email KO ({e})", flush=True)
        return False


def get_current_user(request: Request) -> dict | None:
    """Dependency FastAPI : retourne l'utilisateur (dict) si session valide, sinon None.
    Ne lève jamais — les routes décident elles-mêmes si l'auth est obligatoire."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return users_db.get_user_from_session(token)


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=users_db.SESSION_TTL_DAYS * 86400,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    # Doit reprendre EXACTEMENT les mêmes attributs (secure, httponly,
    # samesite) que set_session_cookie — certains navigateurs n'écrasent
    # pas un cookie Secure si l'ordre de suppression ne matche pas ces
    # attributs, laissant la session active malgré la déconnexion.
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )