"""PayPal REST client (Orders v2, Authorizations, Payouts) with a mock twin.

Live mode (PAYPAL_CLIENT_ID + PAYPAL_CLIENT_SECRET set) talks to the PayPal sandbox.
Mock mode mirrors the same calls locally so the whole product runs with zero setup;
the dashboard shows a "PayPal mock" badge whenever it is active.
"""

from __future__ import annotations

import threading
import time
import uuid

import httpx

from . import config


class PayPalError(Exception):
    pass


def money(micros: int) -> str:
    return f"{micros / 1_000_000:.2f}"


def _parse_money(value: str) -> int:
    return int(round(float(value) * 1_000_000))


class PayPal:
    def __init__(self):
        self._token: str | None = None
        self._token_exp = 0.0
        self._lock = threading.Lock()

    @property
    def live(self) -> bool:
        return config.get().paypal_live

    @property
    def mode(self) -> str:
        return "sandbox" if self.live else "mock"

    # ---------- plumbing ----------

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_exp - 60:
                return self._token
            s = config.get()
            r = httpx.post(
                f"{s.paypal_api_base}/v1/oauth2/token",
                auth=(s.paypal_client_id, s.paypal_secret),
                data={"grant_type": "client_credentials"},
                timeout=30,
            )
            if r.status_code != 200:
                raise PayPalError(f"PayPal auth failed ({r.status_code}): {r.text[:300]}")
            body = r.json()
            self._token = body["access_token"]
            self._token_exp = time.time() + int(body.get("expires_in", 3000))
            return self._token

    def _req(self, method: str, path: str, json: dict | None = None, request_id: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json",
                   "Prefer": "return=representation"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        r = httpx.request(method, config.get().paypal_api_base + path, json=json, headers=headers, timeout=60)
        if r.status_code >= 400:
            raise PayPalError(f"PayPal {method} {path} failed ({r.status_code}): {r.text[:500]}")
        return r.json() if r.content else {}

    @staticmethod
    def _mock_id(prefix: str) -> str:
        return f"MOCK-{prefix}-{uuid.uuid4().hex[:12].upper()}"

    # ---------- Orders v2 ----------

    def create_order(self, amount: int, intent: str, return_url: str, cancel_url: str,
                     custom_id: str, description: str) -> dict:
        """intent is CAPTURE (wallet/bond top-up) or AUTHORIZE (bounty escrow)."""
        if not self.live:
            oid = self._mock_id("ORDER")
            base = config.get().base_url
            return {"id": oid, "status": "CREATED", "approve_url": f"{base}/paypal/mock/approve?token={oid}"}
        body = {
            "intent": intent,
            "purchase_units": [{
                "amount": {"currency_code": "USD", "value": money(amount)},
                "custom_id": custom_id,
                "description": description[:127],
            }],
            "payment_source": {"paypal": {"experience_context": {
                "brand_name": "Errand",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url,
            }}},
        }
        res = self._req("POST", "/v2/checkout/orders", body, request_id=custom_id)
        approve = next((l["href"] for l in res.get("links", []) if l.get("rel") in ("payer-action", "approve")), None)
        return {"id": res["id"], "status": res.get("status"), "approve_url": approve}

    def capture_order(self, order_id: str) -> dict:
        if not self.live:
            return {"status": "COMPLETED", "capture_id": self._mock_id("CAPTURE")}
        res = self._req("POST", f"/v2/checkout/orders/{order_id}/capture", {}, request_id=f"cap-{order_id}")
        cap = res["purchase_units"][0]["payments"]["captures"][0]
        return {"status": cap["status"], "capture_id": cap["id"], "amount": _parse_money(cap["amount"]["value"])}

    def authorize_order(self, order_id: str) -> dict:
        if not self.live:
            return {"status": "CREATED", "authorization_id": self._mock_id("AUTH")}
        res = self._req("POST", f"/v2/checkout/orders/{order_id}/authorize", {}, request_id=f"auth-{order_id}")
        auth = res["purchase_units"][0]["payments"]["authorizations"][0]
        return {"status": auth["status"], "authorization_id": auth["id"]}

    def capture_authorization(self, authorization_id: str, amount: int) -> dict:
        if not self.live:
            return {"status": "COMPLETED", "capture_id": self._mock_id("CAPTURE")}
        res = self._req(
            "POST", f"/v2/payments/authorizations/{authorization_id}/capture",
            {"amount": {"currency_code": "USD", "value": money(amount)}, "final_capture": True},
            request_id=f"acap-{authorization_id}",
        )
        return {"status": res.get("status"), "capture_id": res.get("id")}

    def void_authorization(self, authorization_id: str) -> dict:
        if not self.live:
            return {"status": "VOIDED"}
        self._req("POST", f"/v2/payments/authorizations/{authorization_id}/void", None,
                  request_id=f"void-{authorization_id}")
        return {"status": "VOIDED"}

    # ---------- Payouts ----------

    def create_payout(self, email: str, amount: int, note: str, batch_id: str) -> dict:
        if not self.live:
            return {"payout_batch_id": self._mock_id("PAYOUT"), "status": "SUCCESS"}
        res = self._req("POST", "/v1/payments/payouts", {
            "sender_batch_header": {"sender_batch_id": batch_id, "email_subject": "You have an Errand payout",
                                    "email_message": note},
            "items": [{"recipient_type": "EMAIL", "receiver": email, "note": note, "sender_item_id": batch_id,
                       "amount": {"value": money(amount), "currency": "USD"}}],
        })
        hdr = res.get("batch_header", {})
        return {"payout_batch_id": hdr.get("payout_batch_id"), "status": hdr.get("batch_status", "PENDING")}


client = PayPal()
