# Idea Dump

Telegram messages → LLM-cleaned English ideas → Markdown knowledge base.

## Input

- Text
- Text + Image
- Text + Video

## Flow

Telegram → OpenRouter → Markdown → Knowledge Base

## Knowledge base

```text
knowledge-base/
├── schema.md
├── index.md
├── log.md
└── ideas/
    └── assets/
```

## Environment

Copy `.env.example` to `.env` and set:

```text
TELEGRAM_BOT_TOKEN
OPENROUTER_API_KEY
OPENROUTER_MODEL
```

`.env` is not committed.

## Local run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```
