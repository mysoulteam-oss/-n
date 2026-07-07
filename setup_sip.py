"""Создать и настроить SIP-коннектор Newo (интеграция newo_voice) из .env.

Использование:
    python setup_sip.py            # создать коннектор с настройками, НЕ запускать
    python setup_sip.py --activate # создать и сразу запустить (боевой режим)

Значения берутся из .env: NEWO_SIP_PROVIDER / NEWO_SIP_HOSTNAME /
NEWO_SIP_USERNAME / NEWO_SIP_PASSWORD / NEWO_SIP_CALLER_ID / NEWO_SIP_CONNECTOR_IDN.
"""

import sys

import config
from client import NewoClient, NewoError
from config import ConfigError


def main() -> int:
    activate = "--activate" in sys.argv[1:]

    if not (config.NEWO_SIP_HOSTNAME and config.NEWO_SIP_USERNAME and config.NEWO_SIP_PASSWORD):
        print("Не заданы SIP-настройки в .env (NEWO_SIP_HOSTNAME/USERNAME/PASSWORD).", file=sys.stderr)
        return 1

    try:
        client = NewoClient()
        client.check_auth()
    except (ConfigError, NewoError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    try:
        result = client.setup_sip_connector(
            provider=config.NEWO_SIP_PROVIDER,
            hostname=config.NEWO_SIP_HOSTNAME,
            username=config.NEWO_SIP_USERNAME,
            password=config.NEWO_SIP_PASSWORD,
            caller_id=config.NEWO_SIP_CALLER_ID,
            connector_idn=config.NEWO_SIP_CONNECTOR_IDN,
            title="Zadarma SIP",
            activate=activate,
        )
    except NewoError as exc:
        print(f"Не удалось настроить SIP-коннектор: {exc}", file=sys.stderr)
        return 1

    print("✓ SIP-коннектор создан:")
    print(f"    connector_idn : {result['connector_idn']}")
    print(f"    connector_id  : {result['connector_id']}")
    print(f"    provider      : {result['provider']}")
    print(f"    hostname      : {config.NEWO_SIP_HOSTNAME}")
    print(f"    caller_id     : {config.NEWO_SIP_CALLER_ID}")
    print(f"    активирован   : {'да' if result['activated'] else 'нет (запусти с --activate)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
