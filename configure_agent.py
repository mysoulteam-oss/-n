"""Настройка поведения агента «Софія» (Franch) через project-атрибуты Newo.

Что делает (идемпотентно — повторный запуск безопасен):
  1. Выключает инфо-SMS во время разговора
     (project_attributes_setting_sms_send_information_enabled = False).
     Это убирает отправку SMS и связанную с ней просьбу «ответьте на SMS почтой».
  2. Дописывает в глобальную инструкцию агента финальный скрипт:
       — «Можу надіслати вам інформацію у Вайбер чи Телеграм?»
       — при согласии: «Чудово. За цим номером телефону, все вірно?» + подтверждение номера
     и запрет выпрашивать email / предлагать SMS.

Запуск:
    python configure_agent.py
"""

import sys

from client import NewoClient, NewoError
from config import ConfigError

SMS_ENABLED_IDN = "project_attributes_setting_sms_send_information_enabled"
GLOBAL_INSTRUCTION_IDN = "project_attributes_setting_additional_global_conversation_instruction"

# Маркер, по которому определяем, что финальный скрипт уже добавлен.
CLOSING_MARKER = "Можу надіслати вам інформацію у Вайбер чи Телеграм?"

CLOSING_TEXT = (
    "\n\nНаприкінці розмови, коли узгоджено наступний крок, обов'язково запитай: "
    "«Можу надіслати вам інформацію у Вайбер чи Телеграм?» "
    "Якщо клієнт погоджується та каже «так», відповідай: «Чудово. За цим номером телефону, все вірно?» — "
    "і дочекайся підтвердження номера. "
    "Не пропонуй надсилати SMS і ніколи не проси клієнта відповідати на SMS електронною поштою. "
    "Не випрошуй email, якщо він не потрібен для конкретного кроку."
)


def main() -> int:
    try:
        client = NewoClient()
        client.check_auth()
    except (ConfigError, NewoError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    # 1) Выключаем инфо-SMS
    sms_attr = client.get_customer_attribute(SMS_ENABLED_IDN)
    if not sms_attr:
        print("Атрибут SMS не найден.", file=sys.stderr)
        return 1
    if str(sms_attr.get("value")) == "False":
        print("• инфо-SMS уже выключены (пропуск)")
    else:
        client.set_customer_attribute(sms_attr["id"], "False")
        print("• инфо-SMS выключены")

    # 2) Дописываем финальный скрипт (если ещё нет)
    gi = client.get_customer_attribute(GLOBAL_INSTRUCTION_IDN)
    if not gi:
        print("Атрибут глобальной инструкции не найден.", file=sys.stderr)
        return 1
    current = str(gi.get("value") or "")
    if CLOSING_MARKER in current:
        print("• финальный скрипт уже добавлен (пропуск)")
    else:
        client.set_customer_attribute(gi["id"], current + CLOSING_TEXT)
        print("• финальный скрипт (Viber/Telegram + подтверждение номера) добавлен")

    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
