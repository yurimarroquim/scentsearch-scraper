"""
Mercado Livre OAuth2 - Authorization Code Flow
Documentação: https://developers.mercadolibre.com.br/documentacao/autorizacao

Fluxo de autorização:
  1. Usuário clica no link de autorização gerado por get_authorization_url()
  2. ML redireciona para CONFIGURED_REDIRECT_URI?code=XXX após aprovação
  3. Usuário copia o código da URL e cola no dashboard
  4. exchange_code_for_token(code) troca o código por access+refresh tokens
"""
import json
import logging
import os
import time
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TOKEN_FILE = Path(__file__).parent.parent / "ml_token.json"
AUTHORIZE_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

# URI configurada no app do ML (callback_url atual)
CONFIGURED_REDIRECT_URI = "https://scentsearch.com.br"


def get_client_id() -> str:
    return os.getenv("ML_CLIENT_ID", "")


def get_client_secret() -> str:
    return os.getenv("ML_CLIENT_SECRET", "")


def is_app_configured() -> bool:
    return bool(get_client_id() and get_client_secret())


def get_authorization_url() -> str:
    """Gera a URL de autorização usando o redirect_uri já configurado no app ML.
    O escopo offline_access é necessário para receber o refresh_token e renovar
    automaticamente sem exigir reautorização manual.
    """
    params = {
        "response_type": "code",
        "client_id": get_client_id(),
        "redirect_uri": CONFIGURED_REDIRECT_URI,
        "scope": "offline_access read write",
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def load_token() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def save_token(data: dict) -> None:
    data["saved_at"] = int(time.time())
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("[ML OAuth] Token salvo em ml_token.json")


def delete_token() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    logger.info("[ML OAuth] Token removido")


def get_valid_access_token() -> str | None:
    """Retorna token válido, renovando via refresh_token se necessário."""
    token_data = load_token()
    if not token_data:
        return None

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    saved_at = token_data.get("saved_at", 0)
    expires_in = token_data.get("expires_in", 21600)

    if not access_token:
        return None

    elapsed = int(time.time()) - saved_at
    if elapsed < (expires_in - 300):
        return access_token

    if not refresh_token:
        logger.warning("[ML OAuth] Token expirado e sem refresh_token.")
        return None

    logger.info("[ML OAuth] Token expirado — renovando via refresh_token...")
    return _refresh_access_token(refresh_token)


def _refresh_access_token(refresh_token: str) -> str | None:
    try:
        r = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": get_client_id(),
            "client_secret": get_client_secret(),
            "refresh_token": refresh_token,
        }, timeout=15)

        if r.status_code == 200:
            data = r.json()
            save_token(data)
            logger.info("[ML OAuth] Token renovado com sucesso.")
            return data.get("access_token")
        else:
            logger.error(f"[ML OAuth] Falha no refresh: {r.status_code} {r.text[:200]}")
            delete_token()
            return None
    except Exception as e:
        logger.error(f"[ML OAuth] Erro no refresh: {e}")
        return None


def exchange_code_for_token(code: str) -> dict | None:
    """Troca o código de autorização por access + refresh tokens."""
    code = code.strip()
    try:
        r = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": get_client_id(),
            "client_secret": get_client_secret(),
            "code": code,
            "redirect_uri": CONFIGURED_REDIRECT_URI,
        }, timeout=15)

        if r.status_code == 200:
            data = r.json()
            save_token(data)
            logger.info("[ML OAuth] Token obtido com sucesso via Authorization Code.")
            return data
        else:
            logger.error(f"[ML OAuth] Falha na troca: {r.status_code} {r.text[:300]}")
            return None
    except Exception as e:
        logger.error(f"[ML OAuth] Erro ao trocar código: {e}")
        return None


def get_token_status() -> dict:
    """Status resumido para o dashboard."""
    if not is_app_configured():
        return {"status": "not_configured", "label": "Credenciais não configuradas"}

    token_data = load_token()
    if not token_data:
        return {"status": "not_authorized", "label": "Aguardando autorização"}

    saved_at = token_data.get("saved_at", 0)
    expires_in = token_data.get("expires_in", 21600)
    elapsed = int(time.time()) - saved_at
    remaining = max(0, expires_in - elapsed)

    if remaining < 300 and not token_data.get("refresh_token"):
        return {"status": "expired", "label": "Token expirado — reautorize"}

    user_id = token_data.get("user_id", "")
    return {
        "status": "authorized",
        "label": f"Autorizado (user_id={user_id})",
        "expires_in_minutes": remaining // 60,
        "has_refresh": bool(token_data.get("refresh_token")),
    }
