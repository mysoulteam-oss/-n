"""Точка входа: простой чат-бот в терминале, подключённый к API."""

import sys

from client import ApiClient
from config import ConfigError


def main() -> int:
    try:
        client = ApiClient()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    print("Подключено. Введите сообщение (пустая строка или Ctrl+D — выход).")
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            break
        try:
            answer = client.chat(message)
        except Exception as exc:  # noqa: BLE001 — показываем пользователю любую ошибку
            print(f"Ошибка запроса: {exc}", file=sys.stderr)
            continue
        print(answer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
