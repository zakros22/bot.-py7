# -*- coding: utf-8 -*-
import os

# توكن البوت من متغيرات البيئة
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# رابط Webhook (لـ Heroku)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# منفذ التشغيل
PORT = int(os.environ.get("PORT", 5000))
