"""
ScentSearch — Alert Checker
Verifica diariamente se algum alerta de preço foi atingido
e dispara email via Brevo para o usuário cadastrado.

Agendar no Replit como cron: 0 8 * * *  (todo dia às 8h)
"""

import os
import logging
import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

BASE_URL = os.environ.get("LOVABLE_API_URL", "https://scentsearch.com.br")
API_KEY = os.environ["LOVABLE_API_KEY"]
BREVO_KEY = os.environ["BREVO_API_KEY"]
TEMPLATE_ID = int(os.environ.get("BREVO_TEMPLATE_ID", "1"))
FROM_EMAIL = os.environ.get("FROM_EMAIL", "alertas@scentsearch.com.br")
FROM_NAME = os.environ.get("FROM_NAME", "ScentSearch Alertas")

AUTH = {"Authorization": f"Bearer {API_KEY}"}


def buscar_alertas():
    r = requests.get(f"{BASE_URL}/api/public/price-alerts", headers=AUTH, timeout=30)
    r.raise_for_status()
    return r.json().get("alerts", [])


def marcar_notificado(alert_id, email):
    r = requests.patch(
        f"{BASE_URL}/api/public/price-alerts/{alert_id}/notify",
        headers=AUTH,
        json={"email": email},
        timeout=30,
    )
    r.raise_for_status()


def enviar_email(to_email, perfume_nome, target_price, current_price):
    r = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": BREVO_KEY, "Content-Type": "application/json"},
        json={
            "to": [{"email": to_email}],
            "templateId": TEMPLATE_ID,
            "params": {
                "perfume_nome": perfume_nome,
                "current_price": f"{current_price:.2f}",
                "target_price": f"{target_price:.2f}",
                "loja": BASE_URL,
            },
            "sender": {"email": FROM_EMAIL, "name": FROM_NAME},
        },
        timeout=30,
    )
    r.raise_for_status()


def run():
    log.info("=== ScentSearch Alert Checker — iniciando ===")
    alertas = buscar_alertas()
    log.info(f"Alertas pendentes encontrados: {len(alertas)}")

    notificados = preco_alto = sem_preco = erros = 0

    for a in alertas:
        nome = a["perfume_nome"]
        target = float(a["target_price"])
        current = a.get("current_min_price")

        log.info(
            f"→ {nome} | alvo R${target:.2f} | atual {f'R${float(current):.2f}' if current else 'sem preço'}"
        )

        if current is None:
            sem_preco += 1
            continue

        current = float(current)

        if current > target:
            log.info(f"  ○ Preço ainda acima do alvo")
            preco_alto += 1
            continue

        try:
            enviar_email(a["email"], nome, target, current)
            marcar_notificado(a["id"], a["email"])
            notificados += 1
            log.info(f"  ✉ Email enviado para {a['email']}")
        except Exception as e:
            log.error(f"  ✗ Erro: {e}")
            erros += 1

    log.info("=== Resumo ===")
    log.info(f"  ✉  Notificados:        {notificados}")
    log.info(f"  ○  Preço ainda alto:   {preco_alto}")
    log.info(f"  ⚠  Sem preço no banco: {sem_preco}")
    log.info(f"  ✗  Erros de envio:     {erros}")
    log.info("=== Alert Checker concluído ===")


if __name__ == "__main__":
    run()
