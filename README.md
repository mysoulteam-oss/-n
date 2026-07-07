# -n

Python-клиент для подключения к API платформы [Newo.ai](https://newo.ai) —
голосовые/чат AI-ассистенты («цифровые сотрудники»).

## Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Настроить ключ
cp .env.example .env
# затем открой .env и впиши NEWO_API_KEY

# 3. Проверить авторизацию
python main.py --check

# 4. Запустить чат (нужен NEWO_USER_ACTOR_ID)
python main.py
```

## Как это работает

Newo использует двухшаговую авторизацию и асинхронный обмен сообщениями:

1. **Токен**: `POST /api/v1/auth/api-key/token` с заголовком `x-api-key` →
   выдаёт `access_token` (JWT, ~15 мин) и `refresh_token`.
2. **Запросы**: заголовок `Authorization: Bearer <access_token>`.
   Клиент сам перевыпускает токен по истечении.
3. **Отправка**: `POST /api/v1/chat/user/{user_actor_id}` — асинхронно (200).
4. **Ответ**: `GET /api/v1/chat/user/{user_actor_id}` — поллинг сообщений агента.

> ⚠️ Рабочий хост API — `app.newo.ai`, хотя в документации указан `api.newo.ai`.
> При необходимости меняется через `NEWO_BASE_URL` в `.env`.

## Структура

| Файл           | Назначение                                             |
| -------------- | ------------------------------------------------------ |
| `config.py`    | Загрузка настроек из `.env`                             |
| `client.py`    | `NewoClient`: авторизация, отправка, поллинг ответов    |
| `main.py`      | Точка входа — проверка авторизации и чат в терминале    |
| `.env.example` | Шаблон настроек                                         |

## Пример кода

```python
from client import NewoClient

client = NewoClient()
answers = client.ask("Привет!", user_actor_id="<uuid>")
for m in answers:
    print(m["payload"]["text"])
```

## Безопасность

- `.env` с ключом **в git не попадает** (см. `.gitignore`).
- Ключ читается только из переменной окружения `NEWO_API_KEY`.

## Документация Newo

- REST API: <https://docs.newo.ai/reference/>
- Индекс для LLM: <https://docs.newo.ai/llms.txt>
