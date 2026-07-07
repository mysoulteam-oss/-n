"""Точка входа: терминальный чат с Newo AI-ассистентом.

Использование:
    python main.py            # интерактивный чат (нужен NEWO_USER_ACTOR_ID)
    python main.py --check    # только проверить авторизацию по ключу
"""

import sys

from client import NewoClient, NewoError
from config import ConfigError


def main() -> int:
    check_only = "--check" in sys.argv[1:]

    try:
        client = NewoClient()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    # Всегда сначала проверяем авторизацию.
    try:
        info = client.check_auth()
    except NewoError as exc:
        print(f"Авторизация не удалась: {exc}", file=sys.stderr)
        return 1
    print(f"✓ Авторизация успешна. base_url={info['base_url']}")

    if check_only:
        return 0

    if not client.user_actor_id:
        print(
            "Для чата нужен NEWO_USER_ACTOR_ID (UUID актёра-пользователя) в .env.\n"
            "Пока задан только ключ — авторизация проверена, чат недоступен.",
            file=sys.stderr,
        )
        return 0

    print("Чат готов. Введите сообщение (пустая строка или Ctrl+D — выход).")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break
        try:
            answers = client.ask(text)
        except NewoError as exc:
            print(f"Ошибка: {exc}", file=sys.stderr)
            continue
        if not answers:
            print("(агент не ответил за отведённое время)")
        for msg in answers:
            print(msg.get("payload", {}).get("text", ""))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
