"""Клиент Newo API (голосовые/чат AI-ассистенты, newo.ai).

Флоу авторизации:
  1. POST /auth/api-key/token  (заголовок x-api-key)  -> access_token (JWT, ~15 мин) + refresh_token
  2. Все остальные вызовы: заголовок Authorization: Bearer <access_token>
  3. Токен протух -> перевыпускаем по api-key автоматически.

Обмен сообщениями (асинхронный):
  POST /chat/user/{user_actor_id}  -> 200, сообщение принято в обработку
  GET  /chat/user/{user_actor_id}  -> {"status": ..., "messages": [...]}  (поллинг ответа)

Документация: https://docs.newo.ai/reference/
"""

from __future__ import annotations

import time
from typing import Any

import requests

import config


class NewoError(RuntimeError):
    """Ошибка обращения к Newo API."""


class NewoClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        user_actor_id: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or config.NEWO_API_KEY
        self.base_url = (base_url or config.NEWO_BASE_URL).rstrip("/")
        self.user_actor_id = user_actor_id or config.NEWO_USER_ACTOR_ID
        self.timeout = timeout

        self._session = requests.Session()
        self._access_token: str | None = None
        self._token_expiry: float = 0.0  # unix-время, когда токен считаем протухшим

    # ---------------------------------------------------------------- auth ---
    def authenticate(self) -> None:
        """Обменять API-ключ на access_token."""
        url = f"{self.base_url}/auth/api-key/token"
        resp = self._session.post(
            url,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
            json={},
            timeout=self.timeout,
        )
        if resp.status_code not in (200, 201):
            raise NewoError(f"Авторизация не удалась: HTTP {resp.status_code} — {resp.text[:200]}")
        data = resp.json()
        self._access_token = data["access_token"]
        # обновим за 30 секунд до фактического истечения
        self._token_expiry = time.monotonic() + max(0, int(data.get("expires_in", 900)) - 30)

    def _auth_header(self) -> dict[str, str]:
        if self._access_token is None or time.monotonic() >= self._token_expiry:
            self.authenticate()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """HTTP-запрос с автоматическим перевыпуском токена при 401."""
        url = f"{self.base_url}{path}"
        headers = {**self._auth_header(), **kwargs.pop("headers", {})}
        resp = self._session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        if resp.status_code == 401:  # токен протух раньше времени — перевыпустим и повторим
            self.authenticate()
            headers = {**self._auth_header(), **kwargs.pop("headers", {})}
            resp = self._session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        return resp

    # ---------------------------------------------------------------- chat ---
    def _actor(self, user_actor_id: str | None) -> str:
        actor = user_actor_id or self.user_actor_id
        if not actor:
            raise NewoError(
                "Не задан user_actor_id. Укажи NEWO_USER_ACTOR_ID в .env "
                "или передай user_actor_id явно."
            )
        return actor

    def send(self, text: str, user_actor_id: str | None = None, **extra: Any) -> None:
        """Отправить сообщение агенту (асинхронно). Ответ забирается через poll()."""
        actor = self._actor(user_actor_id)
        resp = self._request(
            "POST",
            f"/chat/user/{actor}",
            json={"text": text, **extra},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            raise NewoError(f"Отправка не удалась: HTTP {resp.status_code} — {resp.text[:200]}")

    def poll(self, user_actor_id: str | None = None, is_streaming: bool = False) -> dict[str, Any]:
        """Один опрос состояния/сообщений агента."""
        actor = self._actor(user_actor_id)
        resp = self._request(
            "GET",
            f"/chat/user/{actor}",
            params={"is_streaming": str(is_streaming).lower()},
        )
        if resp.status_code != 200:
            raise NewoError(f"Опрос не удался: HTTP {resp.status_code} — {resp.text[:200]}")
        return resp.json()

    def ask(
        self,
        text: str,
        user_actor_id: str | None = None,
        poll_interval: float = 1.0,
        max_wait: float = 60.0,
    ) -> list[dict[str, Any]]:
        """Отправить сообщение и дождаться ответных сообщений агента.

        Возвращает список сообщений с is_agent=True, полученных после отправки.
        """
        actor = self._actor(user_actor_id)
        self.send(text, user_actor_id=actor)

        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            state = self.poll(user_actor_id=actor)
            agent_msgs = [m for m in state.get("messages", []) if m.get("is_agent")]
            if agent_msgs and state.get("status") in ("online", "away", "unavailable", None):
                return agent_msgs
            time.sleep(poll_interval)
        return []

    def check_auth(self) -> dict[str, Any]:
        """Проверить, что ключ валиден — вернуть краткую сводку без раскрытия токена."""
        self.authenticate()
        return {
            "ok": True,
            "base_url": self.base_url,
            "token_len": len(self._access_token or ""),
        }

    # ------------------------------------------------ integrations/connectors ---
    def list_integrations(self) -> list[dict[str, Any]]:
        """Список интеграций аккаунта (newo_voice, twilio, telegram, ...)."""
        resp = self._request("GET", "/integrations")
        if resp.status_code != 200:
            raise NewoError(f"Список интеграций не получен: HTTP {resp.status_code} — {resp.text[:200]}")
        return resp.json()

    def get_integration(self, idn: str) -> dict[str, Any]:
        """Найти интеграцию по её idn (напр. 'newo_voice')."""
        for integ in self.list_integrations():
            if integ.get("idn") == idn:
                return integ
        raise NewoError(f"Интеграция '{idn}' не найдена в аккаунте.")

    def list_connectors(self, integration_id: str) -> list[dict[str, Any]]:
        """Список коннекторов интеграции (с их id, статусом и настройками)."""
        resp = self._request("GET", f"/integrations/{integration_id}/connectors")
        if resp.status_code != 200:
            raise NewoError(f"Список коннекторов не получен: HTTP {resp.status_code} — {resp.text[:200]}")
        data = resp.json()
        return data if isinstance(data, list) else data.get("items", [])

    def find_connector(self, integration_id: str, connector_idn: str) -> dict[str, Any] | None:
        """Найти коннектор по connector_idn или вернуть None."""
        for c in self.list_connectors(integration_id):
            if c.get("connector_idn") == connector_idn:
                return c
        return None

    def create_connector(
        self, integration_id: str, connector_idn: str, title: str, settings: dict[str, str]
    ) -> dict[str, Any]:
        """Создать коннектор интеграции. Коннектор создаётся ОСТАНОВЛЕННЫМ.

        Идемпотентно: если коннектор уже существует (409), возвращает его.
        """
        body = {
            "title": title,
            "connector_idn": connector_idn,
            "settings": [{"idn": k, "value": v} for k, v in settings.items()],
        }
        resp = self._request(
            "POST",
            f"/integrations/{integration_id}/connectors",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 409:  # уже существует — вернём существующий
            existing = self.find_connector(integration_id, connector_idn)
            if existing:
                return existing
        if resp.status_code not in (200, 201):
            raise NewoError(f"Создание коннектора не удалось: HTTP {resp.status_code} — {resp.text[:300]}")
        # Успех может прийти с пустым телом — тогда находим коннектор в списке.
        if resp.content:
            try:
                return resp.json()
            except ValueError:
                pass
        found = self.find_connector(integration_id, connector_idn)
        if found:
            return found
        raise NewoError("Коннектор создан, но не найден при повторном запросе.")

    def set_connector_settings(self, connector_id: str, settings: dict[str, str]) -> None:
        """Обновить настройки существующего коннектора.

        Эндпоинт ожидает список пар idn/value непосредственно в теле запроса.
        """
        body = [{"idn": k, "value": v} for k, v in settings.items()]
        resp = self._request(
            "POST",
            f"/integrations/connectors/{connector_id}/settings",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code not in (200, 201, 204):
            raise NewoError(f"Настройки коннектора не применены: HTTP {resp.status_code} — {resp.text[:300]}")

    def run_connector(self, connector_id: str) -> None:
        """Запустить (активировать) коннектор."""
        resp = self._request("POST", f"/integrations/connectors/{connector_id}/run")
        if resp.status_code not in (200, 201, 204):
            raise NewoError(f"Запуск коннектора не удался: HTTP {resp.status_code} — {resp.text[:300]}")

    def stop_connector(self, connector_id: str) -> None:
        """Остановить коннектор."""
        resp = self._request("POST", f"/integrations/connectors/{connector_id}/stop")
        if resp.status_code not in (200, 201, 204):
            raise NewoError(f"Остановка коннектора не удалась: HTTP {resp.status_code} — {resp.text[:300]}")

    # ------------------------------------------------ customer attributes ---
    def list_customer_attributes(self, per: int = 300) -> list[dict[str, Any]]:
        """Список project/customer-атрибутов (настройки поведения агента)."""
        resp = self._request("GET", "/customer/attributes", params={"page": 1, "per": per})
        if resp.status_code != 200:
            raise NewoError(f"Атрибуты не получены: HTTP {resp.status_code} — {resp.text[:200]}")
        data = resp.json()
        return data if isinstance(data, list) else data.get("items", [])

    def get_customer_attribute(self, idn: str) -> dict[str, Any] | None:
        """Найти атрибут по idn."""
        for a in self.list_customer_attributes():
            if a.get("idn") == idn:
                return a
        return None

    def set_customer_attribute(self, attribute_id: str, value: str) -> None:
        """Обновить значение атрибута по его id (PUT /customer/attributes/{id})."""
        resp = self._request(
            "PUT",
            f"/customer/attributes/{attribute_id}",
            json={"value": value},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code not in (200, 201, 204):
            raise NewoError(f"Атрибут не обновлён: HTTP {resp.status_code} — {resp.text[:200]}")

    def set_customer_attribute_by_idn(self, idn: str, value: str) -> None:
        """Обновить атрибут по idn (сначала находит его id)."""
        attr = self.get_customer_attribute(idn)
        if not attr:
            raise NewoError(f"Атрибут '{idn}' не найден.")
        self.set_customer_attribute(attr["id"], value)

    def restart_connector(self, connector_id: str) -> None:
        """Перезапустить коннектор (stop -> run) — нужно для применения credentials."""
        try:
            self.stop_connector(connector_id)
        except NewoError:
            pass  # уже остановлен — не страшно
        self.run_connector(connector_id)

    def setup_sip_connector(
        self,
        provider: str,
        hostname: str,
        username: str,
        password: str,
        caller_id: str,
        connector_idn: str = "newo_voice_connector",
        title: str = "Newo Voice",
        activate: bool = False,
    ) -> dict[str, Any]:
        """Настроить SIP на коннекторе интеграции newo_voice.

        Если коннектор с таким connector_idn уже есть (напр. основной
        newo_voice_connector) — обновляет его настройки; иначе создаёт новый.
        При activate=True перезапускает коннектор, чтобы применить credentials.
        """
        integ = self.get_integration("newo_voice")
        settings = {
            "provider": provider,
            "sip_hostname": hostname,
            "sip_username": username,
            "sip_password": password,
            "sip_caller_id": caller_id,
        }
        existing = self.find_connector(integ["id"], connector_idn)
        if existing:
            connector_id = existing["id"]
            self.set_connector_settings(connector_id, settings)
        else:
            connector = self.create_connector(integ["id"], connector_idn, title, settings)
            connector_id = connector.get("id")
            if not connector_id:
                raise NewoError("Не удалось определить id коннектора.")
            self.set_connector_settings(connector_id, settings)

        activated = False
        if activate:
            self.restart_connector(connector_id)
            activated = True
        return {
            "integration_id": integ["id"],
            "connector_id": connector_id,
            "connector_idn": connector_idn,
            "provider": provider,
            "reused_existing": bool(existing),
            "activated": activated,
        }
