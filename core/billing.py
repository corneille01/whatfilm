# core/billing.py
#
# Intégration Stripe pour l'abonnement hebdomadaire (2,25 € HT / semaine).
#
# ⚠️ Prérequis côté dashboard Stripe (à faire manuellement, je ne peux
# pas le faire à ta place) :
#   1. Créer un Produit "Pelify Pro"
#   2. Créer un Prix récurrent : 2.25 EUR, intervalle "week", tax
#      behavior "exclusive" si tu actives Stripe Tax (sinon le prix
#      encaissé sera exactement 2,25€ sans TVA ajoutée automatiquement)
#   3. Copier l'ID du prix (price_...) dans STRIPE_PRICE_ID_WEEKLY
#   4. Créer un webhook pointant vers https://<ton-domaine>/billing/webhook
#      avec les événements : checkout.session.completed,
#      customer.subscription.updated, customer.subscription.deleted
#   5. Copier le "Signing secret" du webhook dans STRIPE_WEBHOOK_SECRET
#
# Variables d'environnement :
#   STRIPE_SECRET_KEY
#   STRIPE_WEBHOOK_SECRET
#   STRIPE_PRICE_ID_WEEKLY
#   APP_BASE_URL

import os
from datetime import datetime, timezone
from typing import Optional

import stripe

from storage.cache_engine import users_db

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_WEEKLY = os.environ.get("STRIPE_PRICE_ID_WEEKLY", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://pelify.app")


def create_checkout_session(user_id: int, email: str) -> Optional[str]:
    """Crée une session Stripe Checkout pour l'abonnement hebdo, retourne l'URL de paiement."""
    if not stripe.api_key or not STRIPE_PRICE_ID_WEEKLY:
        print("⚠️ billing: STRIPE_SECRET_KEY ou STRIPE_PRICE_ID_WEEKLY manquant", flush=True)
        return None
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID_WEEKLY, "quantity": 1}],
            customer_email=email,
            client_reference_id=str(user_id),
            metadata={"pelify_user_id": str(user_id)},
            success_url=f"{APP_BASE_URL}/?billing=success",
            cancel_url=f"{APP_BASE_URL}/?billing=cancel",
            allow_promotion_codes=True,
        )
        return session.url
    except Exception as e:
        print(f"⚠️ billing.create_checkout_session KO ({e})", flush=True)
        return None


def create_portal_session(customer_id: str) -> Optional[str]:
    """Lien vers le portail Stripe (annulation, moyen de paiement, factures)."""
    if not stripe.api_key:
        return None
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_BASE_URL}/",
        )
        return session.url
    except Exception as e:
        print(f"⚠️ billing.create_portal_session KO ({e})", flush=True)
        return None


def _ts_to_dt(ts: Optional[int]) -> Optional[datetime]:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def handle_webhook_event(payload: bytes, sig_header: str) -> dict:
    """Vérifie la signature et applique l'événement. Lève une exception si
    la signature est invalide (l'appelant doit répondre 400)."""
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET manquant")

    event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("pelify_user_id")
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        if user_id and customer_id:
            users_db.set_stripe_customer_id(int(user_id), customer_id)
        if user_id and subscription_id:
            sub = stripe.Subscription.retrieve(subscription_id)
            users_db.upsert_subscription(
                int(user_id), subscription_id, sub["status"],
                _ts_to_dt(sub.get("current_period_end")),
            )

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        customer_id = obj.get("customer")
        user = users_db.get_user_by_stripe_customer(customer_id) if customer_id else None
        if user:
            status = obj.get("status", "canceled") if event_type == "customer.subscription.updated" else "canceled"
            users_db.upsert_subscription(
                user["id"], obj.get("id", ""), status,
                _ts_to_dt(obj.get("current_period_end")),
            )
        else:
            print(f"⚠️ billing: webhook {event_type} pour customer inconnu {customer_id}", flush=True)

    return {"handled": event_type}