from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


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

    def is_ready(self) -> bool:
        return bool(self.bot_token)
