"""Настройка поведения агента «Софія» (Franch) через Newo API.

Идемпотентно применяет:
  1. Инфо-SMS во время разговора выключены (убирает «ответьте на SMS почтой»).
  2. Язык зафиксирован на украинском:
       - STT голосового коннектора google_stt_language_codes = uk-UA
       - project_representative_agent_voice_transcriber_language = Ukrainian
       - project_business_language_restricted_list = ["Ukrainian"]
     (лечит дрейф в английский из-за англоязычного распознавания речи)
  3. Финальный скрипт в глобальной инструкции: после Zoom-зустрічі —
     «Куди вам було б зручно відправити інформацію?» → (Viber/Telegram) →
     «Чудово. За цим номером телефону, все вірно?».

ВНИМАНИЕ: языковые правки — обоснованная, но НЕ подтверждённая реальным
звонком гипотеза (режим voice-to-voice на Gemini). Проверяется только звонком.
Более надёжное место для языка/сценария — Newo Builder.

Запуск:  python configure_agent.py
"""

import sys

from client import NewoClient, NewoError
from config import ConfigError

VOICE_CONNECTOR_IDN = "newo_voice_connector"

# Значения атрибутов, которые приводим к нужному состоянию.
ATTR_TARGETS = {
    "project_attributes_setting_sms_send_information_enabled": "False",
    "project_representative_agent_voice_transcriber_language": "Ukrainian",
    "project_business_language_restricted_list": '["Ukrainian"]',
}

VOICE_STT_LANGUAGE = "uk-UA"

GLOBAL_INSTRUCTION_IDN = "project_attributes_setting_additional_global_conversation_instruction"
CLOSING_ANCHOR = "\n\nНаприкінці розмови"  # с этого места начинается наш блок
CLOSING_MARKER = "Куди вам було б зручно відправити інформацію?"

CLOSING_TEXT = (
    "\n\nНаприкінці розмови, після того як ти запропонувала Zoom-зустріч і клієнт погодився та ви узгодили деталі "
    "й зібрали потрібну інформацію, запитай: «Куди вам було б зручно відправити інформацію?». "
    "Якщо клієнт не називає канал — уточни: «У Вайбер чи Телеграм?». "
    "Коли клієнт відповів, підтверди: «Чудово. За цим номером телефону, все вірно?» — і дочекайся підтвердження номера. "
    "Не пропонуй надсилати SMS і ніколи не проси клієнта відповідати на SMS електронною поштою. "
    "Не випрошуй email, якщо він не потрібен для конкретного кроку. "
    "Завжди відповідай українською; якщо репліку клієнта розпізнано іншою мовою, незрозуміло або схоже на шум — "
    "не переходь на іншу мову, лишайся українською."
)


def main() -> int:
    try:
        client = NewoClient()
        client.check_auth()
    except (ConfigError, NewoError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    attrs = {a.get("idn"): a for a in client.list_customer_attributes()}

    # 1) простые атрибуты
    for idn, target in ATTR_TARGETS.items():
        a = attrs.get(idn)
        if not a:
            print(f"! атрибут не найден: {idn}", file=sys.stderr)
            continue
        if str(a.get("value")) == target:
            print(f"• {idn} уже = {target} (пропуск)")
        else:
            client.set_customer_attribute(a["id"], target)
            print(f"• {idn} -> {target}")

    # 2) финальный скрипт в глобальной инструкции (заменяем прежний блок)
    gi = attrs.get(GLOBAL_INSTRUCTION_IDN)
    if gi:
        cur = str(gi.get("value") or "")
        base = cur.split(CLOSING_ANCHOR)[0].rstrip()
        desired = base + CLOSING_TEXT
        if cur == desired:
            print("• финальный скрипт уже актуален (пропуск)")
        else:
            client.set_customer_attribute(gi["id"], desired)
            print("• финальный скрипт обновлён")

    # 3) STT язык голосового коннектора + рестарт
    integ = client.get_integration("newo_voice")
    conn = client.find_connector(integ["id"], VOICE_CONNECTOR_IDN)
    if conn:
        cur_lang = next((s["value"] for s in conn.get("settings", []) if s["idn"] == "google_stt_language_codes"), None)
        if cur_lang == VOICE_STT_LANGUAGE:
            print(f"• STT язык уже = {VOICE_STT_LANGUAGE} (пропуск рестарта)")
        else:
            client.set_connector_settings(conn["id"], {"google_stt_language_codes": VOICE_STT_LANGUAGE})
            client.restart_connector(conn["id"])
            print(f"• STT язык -> {VOICE_STT_LANGUAGE}, коннектор перезапущен")
    else:
        print(f"! коннектор {VOICE_CONNECTOR_IDN} не найден", file=sys.stderr)

    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
