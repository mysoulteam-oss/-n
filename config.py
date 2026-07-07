"""Загрузка конфигурации из переменных окружения (.env)."""

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


API_KEY: str = _require("API_KEY")
API_BASE_URL: str = os.getenv("API_BASE_URL", "https://api.example.com/v1")
MODEL: str = os.getenv("MODEL", "default")
