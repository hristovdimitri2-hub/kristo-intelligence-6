from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import requests


log = logging.getLogger("kristo.v5.telegram_flow")


@dataclass
class TelegramOnboarding:
    chat_id: str
    welcome_message: str
    plan: str = "starter"
    follow_up_message: str = ""


class TelegramSalesFlow:
    """Onboarding flow for launch-ready sales conversion."""

    def __init__(self, bot_token: str = ""):
        self.bot_token = bot_token

    def build_welcome_message(self, plan_name: str) -> str:
        return (
            f"🎉 Добре дошъл в Kristo Intelligence!\n\n"
            f"Твоят план: {plan_name}\n"
            f"Получаваш достъп до live crypto intelligence и VIP сигнали.\n"
            f"За да започнеш, провери своята подписка и следващата стъпка."
        )

    def build_follow_up_message(self, plan_name: str) -> str:
        return (
            f"📈 Твоят {plan_name} план е активен.\n"
            f"Следващата стъпка е да получиш първата си дневна сигнална обвързаност."
        )

    def create_onboarding(self, chat_id: str, plan_name: str) -> TelegramOnboarding:
        welcome = self.build_welcome_message(plan_name)
        follow_up = self.build_follow_up_message(plan_name)
        return TelegramOnboarding(
            chat_id=chat_id,
            plan=plan_name,
            welcome_message=welcome,
            follow_up_message=follow_up,
        )

    def create_follow_up_payload(self, chat_id: str, plan_name: str) -> Dict[str, str]:
        onboarding = self.create_onboarding(chat_id, plan_name)
        return {
            "chat_id": chat_id,
            "plan": onboarding.plan,
            "welcome_message": onboarding.welcome_message,
            "follow_up_message": onboarding.follow_up_message,
        }

    def deliver_vip_invite(
        self,
        customer_chat_id: str,
        checkout_id: str,
        plan_name: str,
    ) -> Dict[str, str]:
        """Create a one-use group invite and deliver it to a linked Telegram user.

        Telegram cannot add a purchaser to a group from an email address. A checkout
        must therefore carry the purchaser's Telegram chat ID, and the bot must be
        an administrator in the configured VIP group.
        """
        if not customer_chat_id:
            return {"status": "pending_telegram_link"}

        invitation = self.create_vip_invite(checkout_id)
        invite_link = invitation.get("invite_link", "")
        if not invite_link:
            return invitation
        return self.send_vip_invite(customer_chat_id, plan_name, invite_link)

    def create_vip_invite(self, checkout_id: str) -> Dict[str, str]:
        """Create a one-use VIP invite without delivering it yet."""
        vip_chat_id = (os.getenv("TELEGRAM_VIP_CHAT_ID") or "").strip()
        if not self.bot_token or not vip_chat_id:
            return {"status": "pending_vip_group_configuration"}
        api_base = f"https://api.telegram.org/bot{self.bot_token}"
        invite_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        try:
            invite_response = requests.post(
                f"{api_base}/createChatInviteLink",
                json={
                    "chat_id": vip_chat_id,
                    "name": f"vip-{checkout_id[-24:]}",
                    "member_limit": 1,
                    "expire_date": int(invite_expires_at.timestamp()),
                },
                timeout=15,
            )
            invite_payload = invite_response.json()
            invite_link = (invite_payload.get("result") or {}).get("invite_link")
            if not invite_response.ok or not invite_payload.get("ok") or not invite_link:
                log.warning("Telegram VIP invite creation was rejected.")
                return {"status": "invite_creation_failed"}
            return {
                "status": "invite_created",
                "invite_link": invite_link,
                "invite_expires_at": invite_expires_at.isoformat(),
            }
        except requests.RequestException:
            log.warning("Telegram VIP invite creation failed.")
            return {"status": "invite_creation_failed"}

    def send_vip_invite(
        self,
        customer_chat_id: str,
        plan_name: str,
        invite_link: str,
    ) -> Dict[str, str]:
        """Deliver an already-created one-use invite, so retries reuse it."""
        if not customer_chat_id or not invite_link:
            return {"status": "pending_telegram_link"}
        if not self.bot_token:
            return {"status": "pending_vip_group_configuration"}
        api_base = f"https://api.telegram.org/bot{self.bot_token}"
        try:
            message_response = requests.post(
                f"{api_base}/sendMessage",
                json={
                    "chat_id": customer_chat_id,
                    "text": (
                        f"🎉 Плащането за {plan_name} е потвърдено.\n\n"
                        f"Това е твоята еднократна VIP покана (валидна 24 часа):\n{invite_link}"
                    ),
                },
                timeout=15,
            )
            message_payload = message_response.json()
            if not message_response.ok or not message_payload.get("ok"):
                log.warning("Telegram VIP invite delivery was rejected.")
                return {"status": "invite_delivery_failed"}
            return {"status": "invite_sent"}
        except requests.RequestException:
            log.warning("Telegram VIP invite delivery failed.")
            return {"status": "invite_delivery_failed"}

    def send_message(self, customer_chat_id: str, text: str) -> Dict[str, str]:
        """Send a non-sensitive account-link confirmation to a Telegram user."""
        if not customer_chat_id or not self.bot_token:
            return {"status": "message_delivery_unavailable"}
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": customer_chat_id, "text": text},
                timeout=15,
            )
            payload = response.json()
            if not response.ok or not payload.get("ok"):
                return {"status": "message_delivery_failed"}
            return {"status": "message_sent"}
        except requests.RequestException:
            return {"status": "message_delivery_failed"}

    def is_ready(self) -> bool:
        return bool(self.bot_token)
