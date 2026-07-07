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
