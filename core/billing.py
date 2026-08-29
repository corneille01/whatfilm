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
#      (et faire pareil pour un 2e tarif mensuel si besoin -> STRIPE_PRICE_ID_MONTHLY,
#      en ajoutant un second "Add another price" sur le MÊME produit Stripe)
#   4. Créer un webhook pointant vers https://<ton-domaine>/billing/webhook
#      avec les événements : checkout.session.completed,
#      customer.subscription.updated, customer.subscription.deleted
#   5. Copier le "Signing secret" du webhook dans STRIPE_WEBHOOK_SECRET
#
# Variables d'environnement :
#   STRIPE_SECRET_KEY
#   STRIPE_WEBHOOK_SECRET
#   STRIPE_PRICE_ID_WEEKLY
#   STRIPE_PRICE_ID_MONTHLY (optionnel, pour le second tarif)
#   APP_BASE_URL

import os
from datetime import datetime, timezone
from typing import Optional

import stripe

from storage.cache_engine import users_db

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_WEEKLY = os.environ.get("STRIPE_PRICE_ID_WEEKLY", "")
STRIPE_PRICE_ID_MONTHLY = os.environ.get("STRIPE_PRICE_ID_MONTHLY", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://pelify.app")

PLAN_PRICE_IDS = {
    "weekly": STRIPE_PRICE_ID_WEEKLY,
    "monthly": STRIPE_PRICE_ID_MONTHLY,
}


def create_checkout_session(user_id: int, email: str, plan: str = "weekly") -> Optional[str]:
    """Crée une session Stripe Checkout pour l'abonnement (hebdo ou mensuel), retourne l'URL de paiement."""
    price_id = PLAN_PRICE_IDS.get(plan)
    if not stripe.api_key or not price_id:
        print(f"⚠️ billing: STRIPE_SECRET_KEY ou price manquant pour le plan '{plan}'", flush=True)
        return None
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=email,
            client_reference_id=str(user_id),
            metadata={"pelify_user_id": str(user_id), "plan": plan},
            success_url=f"{APP_BASE_URL}/?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
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


def recover_customer_id(user_id: int, stripe_subscription_id: str) -> Optional[str]:
    """
    Auto-réparation : si l'abonnement d'un compte est actif mais que
    stripe_customer_id n'a jamais été enregistré (raté du webhook ou
    de la confirmation initiale), on va le rechercher directement
    auprès de Stripe via l'abonnement connu, et on le sauvegarde.
    """
    if not stripe.api_key or not stripe_subscription_id:
        return None
    try:
        sub = stripe.Subscription.retrieve(stripe_subscription_id)
        customer_id = sub.get("customer") if hasattr(sub, "get") else getattr(sub, "customer", None)
        if customer_id:
            users_db.set_stripe_customer_id(user_id, customer_id)
            print(f"🔧 billing.recover_customer_id: réparé pour user_id={user_id} (customer_id={customer_id})", flush=True)
            return customer_id
    except Exception as e:
        print(f"⚠️ billing.recover_customer_id KO ({e})", flush=True)
    return None


def _ts_to_dt(ts: Optional[int]) -> Optional[datetime]:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


def confirm_checkout_session(session_id: str, user_id: int) -> bool:
    """
    Vérifie activement l'état d'une session Checkout auprès de Stripe et
    synchronise l'abonnement en base — sans attendre le webhook.

    Sert de filet de sécurité contre l'effet de course : l'utilisateur est
    redirigé vers pelify.app dès le paiement validé, mais le webhook peut
    arriver quelques secondes plus tard. Sans ça, une analyse lancée dans
    cette fenêtre peut se voir refuser l'accès alors que le paiement est
    déjà passé. Idempotent : sans danger même si le webhook a déjà tout
    synchronisé.
    """
    if not stripe.api_key or not session_id:
        return False
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    except Exception as e:
        print(f"⚠️ billing.confirm_checkout_session (retrieve) KO ({e})", flush=True)
        return False

    # Sécurité : on ne confirme que la session de CE user, pas n'importe
    # laquelle qu'un id devinerait dans l'URL.
    if session.get("client_reference_id") != str(user_id):
        print(f"⚠️ billing.confirm_checkout_session: session {session_id} n'appartient pas à user {user_id}", flush=True)
        return False

    if session.get("payment_status") != "paid" and session.get("status") != "complete":
        return False

    customer_id = session.get("customer")
    subscription = session.get("subscription")
    if customer_id:
        users_db.set_stripe_customer_id(user_id, customer_id)
    if subscription:
        users_db.upsert_subscription(
            user_id, subscription["id"], subscription["status"],
            _ts_to_dt(subscription.get("current_period_end")),
        )
        return True
    return False


def handle_webhook_event(payload: bytes, sig_header: str) -> dict:
    """
    Traite les événements Stripe reçus par le webhook.

    Important :
    Stripe renvoie des StripeObject (Session, Subscription, etc.)
    et pas forcément des dictionnaires Python.
    On les convertit donc explicitement avec to_dict()
    avant d'utiliser .get().
    """

    event = stripe.Webhook.construct_event(
        payload,
        sig_header,
        STRIPE_WEBHOOK_SECRET,
    )

    event_type = event["type"]
    obj = event["data"]["object"]

    # StripeObject -> dict
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()

    # ---------------------------------------------------------
    # CHECKOUT TERMINÉ
    # ---------------------------------------------------------
    if event_type == "checkout.session.completed":

        user_id = obj.get("client_reference_id")

        if not user_id:
            metadata = obj.get("metadata") or {}
            user_id = metadata.get("pelify_user_id")

        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")

        # Enregistrer le customer Stripe
        if user_id and customer_id:
            users_db.set_stripe_customer_id(
                int(user_id),
                customer_id,
            )

        # Activer / enregistrer l'abonnement
        if user_id and subscription_id:

            sub = stripe.Subscription.retrieve(
                subscription_id
            )

            # Stripe Subscription -> dict
            if hasattr(sub, "to_dict"):
                sub = sub.to_dict()

            users_db.upsert_subscription(
                int(user_id),
                subscription_id,
                sub["status"],
                _ts_to_dt(
                    sub.get("current_period_end")
                ),
            )

            print(
                f"abonnement activé : "
                f"user_id={user_id}, "
                f"subscription_id={subscription_id}, "
                f"status={sub['status']}"
            )

        return {
            "ok": True,
            "event": event_type,
            "user_id": user_id,
            "customer_id": customer_id,
            "subscription_id": subscription_id,
        }

    # ---------------------------------------------------------
    # ABONNEMENT MIS À JOUR
    # ---------------------------------------------------------
    if event_type == "customer.subscription.updated":

        subscription_id = obj.get("id")
        customer_id = obj.get("customer")
        status = obj.get("status")

        current_period_end = obj.get(
            "current_period_end"
        )

        user_id = None

        if customer_id:
            user_id = users_db.get_user_id_by_stripe_customer(
                customer_id
            )

        if user_id and subscription_id:

            users_db.upsert_subscription(
                int(user_id),
                subscription_id,
                status,
                _ts_to_dt(current_period_end),
            )

            print(
                f"abonnement mis à jour : "
                f"user_id={user_id}, "
                f"subscription_id={subscription_id}, "
                f"status={status}"
            )

        return {
            "ok": True,
            "event": event_type,
            "user_id": user_id,
            "subscription_id": subscription_id,
            "status": status,
        }

    # ---------------------------------------------------------
    # ABONNEMENT ANNULÉ / SUPPRIMÉ
    # ---------------------------------------------------------
    if event_type == "customer.subscription.deleted":

        subscription_id = obj.get("id")
        customer_id = obj.get("customer")

        user_id = None

        if customer_id:
            user_id = users_db.get_user_id_by_stripe_customer(
                customer_id
            )

        if user_id and subscription_id:

            users_db.upsert_subscription(
                int(user_id),
                subscription_id,
                "canceled",
                None,
            )

            print(
                f"abonnement annulé : "
                f"user_id={user_id}, "
                f"subscription_id={subscription_id}"
            )

        return {
            "ok": True,
            "event": event_type,
            "user_id": user_id,
            "subscription_id": subscription_id,
            "status": "canceled",
        }

    # ---------------------------------------------------------
    # AUTRES ÉVÉNEMENTS
    # ---------------------------------------------------------
    print(
        f"Stripe webhook reçu : {event_type}"
    )

    return {
        "ok": True,
        "event": event_type,
    }