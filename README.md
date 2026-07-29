# AI Consultant Telegram Bot

Бот для первичной консультации по ДТП, страховым выплатам и передаче лида специалисту.

## Возможности

- естественный диалог по теме ДТП / ОСАГО / страховых споров;
- уточняющие вопросы по шагам;
- сбор контактов;
- передача обращения оператору;
- сохранение истории и лидов в SQLite;
- запросы к OpenRouter через `POST /api/v1/chat/completions`.

## Установка

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

## Переменные окружения

- `BOT_TOKEN`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_BASE_URL`
- `HTTP_PROXY`
- `HTTPS_PROXY`
- `DEFAULT_LANGUAGE`
- `DEFAULT_TONE`
- `ADMIN_CHAT_ID`
- `LEAD_CHANNEL_ID`
- `DATABASE_PATH`
- `LOG_LEVEL`

## Команды

- `/start`
- `/consult`
- `/contacts`
- `/status`
- `/history`
- `/operator`
- `/cancel`
- `/help`
