"""Загрузка конфигурации Newo из переменных окружения (.env)."""

import os

from dotenv import load_dotenv

load_dotenv()  # читает .env из корня проекта, если он есть


class ConfigError(RuntimeError):
    """Ошибка конфигурации — не хватает обязательной переменной окружения."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Не задана переменная окружения {name}. "
            f"Скопируй .env.example в .env и заполни значения."
        )
    return value


# Ключ выдаётся в личном кабинете Newo: Account → API Keys
NEWO_API_KEY: str = _require("NEWO_API_KEY")

# Живой хост API — app.newo.ai (в доках указан api.newo.ai, но рабочий — этот).
NEWO_BASE_URL: str = os.getenv("NEWO_BASE_URL", "https://app.newo.ai/api/v1")

# UUID актёра-пользователя (user_actor_id), с которым ведём диалог.
# Необязателен для проверки авторизации; нужен для отправки/чтения сообщений.
NEWO_USER_ACTOR_ID: str = os.getenv("NEWO_USER_ACTOR_ID", "")

# --- Телефония: SIP-транк (интеграция newo_voice) -------------------------
# provider: один из twilio | sip | custom_sip | csc-telecom | telnyx | webrtc.
# Для внешнего SIP-транка (напр. Zadarma) — sip или custom_sip.
NEWO_SIP_PROVIDER: str = os.getenv("NEWO_SIP_PROVIDER", "sip")
NEWO_SIP_HOSTNAME: str = os.getenv("NEWO_SIP_HOSTNAME", "")
NEWO_SIP_USERNAME: str = os.getenv("NEWO_SIP_USERNAME", "")
NEWO_SIP_PASSWORD: str = os.getenv("NEWO_SIP_PASSWORD", "")
# Caller id / номер агента в формате E.164 (напр. +380734496407)
NEWO_SIP_CALLER_ID: str = os.getenv("NEWO_SIP_CALLER_ID", "")
# Коннектор интеграции newo_voice, в котором настраиваем SIP.
# По умолчанию — основной newo_voice_connector (тот, что привязан к агенту).
NEWO_SIP_CONNECTOR_IDN: str = os.getenv("NEWO_SIP_CONNECTOR_IDN", "newo_voice_connector")
