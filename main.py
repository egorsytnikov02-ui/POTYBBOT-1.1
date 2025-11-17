import logging
import os
import re
import datetime
import pytz
import random 

from threading import Thread
from flask import Flask

from upstash_redis import Redis

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters, JobQueue
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

# --- Настройки бота (ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ) ---
TOKEN = os.environ.get('TOKEN')
UPSTASH_URL = os.environ.get('UPSTASH_REDIS_REST_URL')
UPSTASH_TOKEN = os.environ.get('UPSTASH_REDIS_REST_TOKEN')

# ⭐️ НОВОЕ: Подключение к Базе Данных (Redis)
try:
    redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)
    logger = logging.getLogger(__name__) # Определяем logger здесь
    logger.info("Успешное подключение к Upstash (Redis)!")
except Exception as e:
    # Если логгер еще не создан, просто выводим в print
    print(f"Критическая ошибка: Не удалось подключиться к Upstash (Redis)! {e}")
    exit()

# --- Веб-сервер (Для UptimeRobot) ---
app = Flask('')
@app.route('/')
def home():
    return "Бот 'ПОТУЖНИЙ' активний!"

def run_web_server():
    # Render.com сам найдет этот порт
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
# ------------------------------------

# --- Логика самого бота ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ⭐️ ОБНОВЛЕНО: Функции для работы с БД (Redis) ---
SCORES_KEY = "potuzhniy_scores"

# --- ⭐️⭐️⭐️ ТЕКУЩИЕ СПИСКИ ГИФОК ⭐️⭐️⭐️ ---
POSITIVE_GIF_IDS = [
    'CgACAgQAAyEFAATIovxHAAIBMmkbIzBGgizItYUn6o8fZlpqGjtqAAJiAwACTvSFUqxjPD48K-gAATYE',
    'CgACAgQAAyEFAATIovxHAAIBHmkbIaZFLIP_S4833aCn_s-D4BDEAALZCwACRO1JUBpaBRGAwhBvNgQ',
    'CgACAgQAAyEFAATIovxHAAIBIGkbIc3XIkwnqYFgwet3OxYCtTZwAAKBBwAC433cUFBsoYS9IXMkNgQ',
    'CgACAgQAAyEFAATIovxHAAIBImkbIfDxrBTOiprkdrjUjh-UobQiAAIVBwACME5MUZm93-5h-vI6NgQ',
    'CgACAgQAAyEFAATIovxHAAIBJGkbIiIp7dZsQdMlhbrVlXwZY3Y_AAIoBgACFs_0USgd43y068CINgQ',
    'CgACAgQAAyEFAATIovxHAAIBJmkbIkAzqeJQLkUqWugqExioLPycAAI3BwACKbQMULIAAd4-8dO41DYE',
    'CgACAgQAAyEFAATIovxHAAIBKGkbImRTZRMmpgxVOvYu5P5pN1MqAAIRBwACGVY9UqIyuKjywgTFNgQ',
    'CgACAgQAAyEFAATIovxHAAIBKmkbIobxmBVu7jO8b9jB6RHmW73TAAIKBwACGAV1U9NNZdDU0v5yNgQ',
    'CgACAgQAAyEFAATIovxHAAIBLGkbIrJqa2reCTDflu2Ewtx7JkCLAAL9BgAC0HSMU-Tr7ZY7KzoNNgQ',
    'CgACAgQAAyEFAATIovxHAAIBLmkbIuB-FVENCjsqaFIkekzSInH9AAL0BgACG0V1U0ReVATVWXzmNgQ',
    'CgACAgQAAyEFAATIovxHAAIBHGkbIYJHnkyR8eg3wjEVMWLLG1CHAAL6BwACJxdNU6LCCnXidiruNgQ',
    'CgACAgQAAyEFAATIovxHAAIBGmkbIVl25ZMb_AfU7dwGPfOORcfrAAK5BgACwQ01UALpKP9zFPjXNgQ',
    'CgACAgIAAyEFAATIovxHAAIBFGkbIDKVBz0AAcCHPWPiouFBQ-8QUwACZIcAAmI62UjvjUf8zjY5HzYE',
    'CgACAgIAAyEFAATIovxHAAPdaRkVYfGLS8oPv9bQCqI01djvty4AApeHAALH_MhIcSfwdw2VoS82BA',
    'CgACAgIAAyEFAATIovxHAAPbaRkVVbPf905738M4G3LMF2eG5QIAAtWHAALH_MhIO-EsNlzAWLg2BA',
    'CgACAgIAAyEFAATIovxHAAPZaRkVQ0SQ5HVf5JX3ojNQskYlamsAAuGHAALH_MhIYotTm8JAOi02BA',
    'CgACAgIAAyEFAATIovxHAAPXaRkVOZUJov
