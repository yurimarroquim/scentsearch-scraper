"""
ScentSearch — Alert Checker
Verifica diariamente se algum alerta de preço foi atingido
e dispara email via Brevo para o usuário cadastrado.

Agendar no Replit como cron: 0 8 * * *  (todo dia às 8h)
"""

import os
import logging
from datetime import datetime
from supabase import create_client, Client
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

SUPABASE_URL      = os.environ["SUPABASE_URL"]
SUPABASE_KEY      = os.environ["SUPABASE_SERVICE_KEY"]
BREVO_API_KEY     = os.environ["BREVO_API_KEY"]
BREVO_TEMPLATE_ID = int(os.environ.get("BREVO_TEMPLATE_ID", "1"))
FROM_EMAIL        = os.environ.get("FROM_EMAIL", "alertas@scentsearch.com.br")
FROM_NAME         = os.environ.get("FROM_NAME", "ScentSearch Alertas")
SITE_URL          = os.environ.get("SITE_URL", "https://scentsearch.com.br")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def buscar_alertas_pendentes():
    resp = (
        supabase.table("price_alerts")
        .select("id, email, perfume_id, perfume_nome, target_price")
        .eq("status", "pending")
        .execute()
    )
    return resp.data or []

def buscar_menor_preco(perfume_id):
    resp = (
        supabase.table("precos")
        .select("preco, loja, link_afiliado")
        .eq("perfume_id", perfume_id)
        .eq("disponivel", True)
        .order("preco", desc=False)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None

def marcar_como_notificado(alert_id):
    supabase.table("price_alerts").update({
        "status": "notified",
        "notified_at": datetime.utcnow().isoformat()
    }).eq("id", alert_id).execute()

def atualizar_lead_score(email, pontos=5):
    try:
        supabase.rpc("increment_lead_score", {"p_email": email, "p_points": pontos}).execute()
    except Exception:
        lead = supabase.table("leads").select("id, lead_score").eq("email", email).single().execute()
        if lead.data:
            novo_score = (lead.data.get("lead_score") or 0) + pontos
            supabase.table("leads").update({
                "lead_score": novo_score,
                "last_contact_at": datetime.utcnow().isoformat()
            }).eq("email", email).execute()

def enviar_email_alerta(to_email, perfume_nome, target_price, current_price, loja, store_url):
    economia = round(target_price - current_price, 2)
    if store_url and not store_url.startswith("http"):
        store_url = f"{SITE_URL}{store_url}"

    payload = {
        "sender": {"name": FROM_NAME, "email": FROM_EMAIL},
        "to": [{"email": to_email}],
        "templateId": BREVO_TEMPLATE_ID,
        "params": {
            "perfume_nome": perfume_nome,
            "target_price": f"{target_price:.2f}".replace(".", ","),
            "current_price": f"{current_price:.2f}".replace(".", ","),
            "economia": f"{economia:.2f}".replace(".", ","),
            "loja": loja,
            "store_url": store_url,
            "site_url": SITE_URL
        }
    }

    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        json=payload,
        headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
        timeout=10
    )

    if resp.status_code in (200, 201):
        log.info(f"  Email enviado para {to_email} ({perfume_nome})")
        return True
    else:
        log.error(f"  Falha ao enviar para {to_email}: {resp.status_code} {resp.text}")
        return False

def run():
    log.info("=== ScentSearch Alert Checker — iniciando ===")
    alertas = buscar_alertas_pendentes()
    log.info(f"Alertas pendentes: {len(alertas)}")

    notificados = sem_preco = preco_alto = erros = 0

    for alerta in alertas:
        perfume_id   = alerta["perfume_id"]
        perfume_nome = alerta["perfume_nome"]
        target_price = float(alerta["target_price"])
        email        = alerta["email"]
        alert_id     = alerta["id"]

        log.info(f"Verificando: {perfume_nome} | alvo R${target_price:.2f} | {email}")

        preco_info = buscar_menor_preco(perfume_id)
        if not preco_info:
            log.warning(f"  Sem preço disponível para {perfume_nome}")
            sem_preco += 1
            continue

        current_price = float(preco_info["preco"])
        loja          = preco_info["loja"]
        store_url     = preco_info["link_afiliado"] or f"{SITE_URL}/perfume/{perfume_id}"

        log.info(f"  Menor preço: R${current_price:.2f} na {loja}")

        if current_price > target_price:
            log.info(f"  Preço acima do alvo (R${current_price:.2f} > R${target_price:.2f})")
            preco_alto += 1
            continue

        sucesso = enviar_email_alerta(email, perfume_nome, target_price, current_price, loja, store_url)

        if sucesso:
            marcar_como_notificado(alert_id)
            atualizar_lead_score(email, pontos=5)
            notificados += 1
        else:
            erros += 1

    log.info(f"=== Resumo: notificados={notificados} sem_preco={sem_preco} alto={preco_alto} erros={erros} ===")

if __name__ == "__main__":
    run()
