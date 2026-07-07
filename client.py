"""Клиент для подключения к API сервиса «Нево аи».

Реализация специально сделана минимальной и провайдер-независимой:
как только будет известен точный формат API (endpoint, схема запроса/ответа),
поправить нужно будет только этот файл.
"""

from __future__ import annotations

import requests

import config


class ApiClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or config.API_KEY
        self.base_url = (base_url or config.API_BASE_URL).rstrip("/")
        self.model = model or config.MODEL
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def chat(self, message: str) -> str:
        """Отправить сообщение и получить текстовый ответ.

        NB: тело запроса ниже написано в стиле OpenAI-совместимого API.
        Если у «Нево аи» другой формат — правим здесь по документации сервиса.
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message}],
        }
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def ping(self) -> int:
        """Проверить доступность API — вернуть HTTP-статус базового URL."""
        response = self._session.get(self.base_url, timeout=self.timeout)
        return response.status_code
