from logging.handlers import RotatingFileHandler
from telethon import TelegramClient, events, functions
import asyncio
import logging
import os
import re
from rapidfuzz import fuzz
from collections import defaultdict
import time


# ====== CONFIG ======
api_id = 25987610
api_hash = '78e9317b91a3b210351c634d11b5ed6f'

SESSION_NAME = "userbot_session"

KEYWORDS_FILE = "keywords.txt"
PHRASES_FILE = "phrases.txt"
BLOCKWORDS_FILE = "blockwords.txt"
LOG_FILE = "bot.log"

# ====== LOGGING ======
logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=0,               # НИКАКИХ бэкапов
    encoding="utf-8"
)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)
handler.setFormatter(formatter)

logger.handlers.clear()
logger.addHandler(handler)

logging.info("===== Бот запускается =====")

# ====== UTILS ======
def load_words(filename):
    if not os.path.exists(filename):
        return set()
    with open(filename, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_words(filename, words):
    with open(filename, "w", encoding="utf-8") as f:
        for word in sorted(words):
            f.write(word + "\n")


# ====== CLIENT ======
client = TelegramClient(SESSION_NAME, api_id, api_hash)

KEYWORDS = set(load_words(KEYWORDS_FILE))
PHRASES = load_words(PHRASES_FILE)
BLOCK_WORDS = set(load_words(BLOCKWORDS_FILE))
KNOWN_CHATS = {}

logging.info(f"Загружено ключевых слов: {len(KEYWORDS)}")
logging.info(f"Загружено ключевых фраз: {len(PHRASES)}")
logging.info(f"Загружено минус-слов: {len(BLOCK_WORDS)}")


def search_phrase(text, phrase):
    return re.search(re.escape(phrase), text, re.IGNORECASE)


def fuzzy_match(word, keywords):
    for kw in keywords:
        if abs(len(word) - len(kw)) > 2:
            continue
        if fuzz.ratio(word, kw) > 85:
            return True
    return False
# ====== NOT REPLAYS ======


def normalize(text):
    return re.findall(r'\w+', text.lower())


class MessageHistory:
    def __init__(self, max_per_chat=100, ttl=3600):
        """
        max_per_chat — сколько сообщений хранить на чат
        ttl — время жизни сообщения (в секундах)
        """
        self.storage = defaultdict(list)
        self.max_per_chat = max_per_chat
        self.ttl = ttl

    def _clean_old(self, chat_id):
        """Удаляем старые сообщения по TTL"""
        now = time.time()
        self.storage[chat_id] = [
            item for item in self.storage[chat_id]
            if now - item["time"] < self.ttl
        ]

    def _similarity(self, words1, words2, important_words):
        """Jaccard + важные слова"""

        set1 = set(words1)
        set2 = set(words2)

        if not set1 or not set2:
            return 0

        intersection = set1 & set2
        union = set1 | set2

        jaccard = len(intersection) / len(union)

        # важные слова
        imp1 = set1 & important_words
        imp2 = set2 & important_words

        if imp1 and imp2:
            important_score = len(imp1 & imp2) / len(imp1 | imp2)
        else:
            important_score = 0

        return jaccard, important_score

    def is_duplicate(self, chat_id, text, important_words):
        """
        Проверяет, является ли сообщение дубликатом
        """

        self._clean_old(chat_id)

        words = normalize(text)

        for item in self.storage[chat_id]:
            jaccard, important_score = self._similarity(
                words,
                item["words"],
                important_words
            )

            # 🔥 ГЛАВНАЯ ЛОГИКА
            if jaccard > 0.55 or important_score > 0.8:
                return True

        return False

    def add_message(self, chat_id, text):
        """Добавляем сообщение в историю"""

        words = normalize(text)

        self.storage[chat_id].append({
            "text": text,
            "words": words,
            "time": time.time()
        })

        # ограничение размера
        if len(self.storage[chat_id]) > self.max_per_chat:
            self.storage[chat_id].pop(0)


message_history = MessageHistory(max_per_chat=100)

# ====== MESSAGE HANDLER ======
# @client.on(events.NewMessage)
# async def handle_message(event):
#     sender = await event.get_sender()
#     chat = await event.get_chat()
#     chat_id = event.chat_id
#     message_text = event.raw_text

#     me = await client.get_me()

#     try:
#         if chat_id == me.id and message_text.startswith('/'):
#             await handle_command(event)
#             return
        
#     except AttributeError:
#         logging.error("Ошибка получения me.id")

#     if chat_id not in KNOWN_CHATS:
#         title = getattr(chat, 'title', f'ID {chat_id}')
#         username = getattr(chat, 'username', None)
#         KNOWN_CHATS[chat_id] = f"@{username}" if username else title

#     logging.info(f"Сообщение из чата {chat_id}: {event.raw_text[:100]}")

#     # Проверяем, не повтор ли это
    
#     IMPORTANT_WORDS = set(KEYWORDS)


#     # проверка ключевых слов

#     words = normalize(message_text)
#     # has_keyword = any(word in words for word in KEYWORDS)
#     # Проверка наличия слов включая опечатки
#     # быстрый точный матч
#     has_keyword = any(word in KEYWORDS for word in words)
#     # если не нашли — используем fuzzy
#     if not has_keyword:
#         has_keyword = any(fuzzy_match(word, KEYWORDS) for word in words)

#     # проверка фраз (оставляем как есть, но исправим ниже)
#     has_phrase = any(search_phrase(message_text, phrase) for phrase in PHRASES)

    

#     if has_keyword or has_phrase:
#         # проверка минус-слов
#         has_block = any(bad in words for bad in BLOCK_WORDS)

#         if has_block:
#             logging.info("Сообщение отфильтровано минус-словами")
#             return
        
#         if message_history.is_duplicate(chat_id, message_text, IMPORTANT_WORDS):
#             logging.info(f"Сообщение из чата {chat_id} похоже на предыдущее - игнорируем")
#             return

#         # Добавляем сообщение в историю
#         message_history.add_message(chat_id, event.raw_text)

#         chat_title = KNOWN_CHATS[chat_id]

#         if getattr(chat, 'username', None):
#             link = f"https://t.me/{chat.username}/{event.id}"
#         elif str(chat_id).startswith('-100'):
#             link = f"https://t.me/c/{str(chat_id)[4:]}/{event.id}"
#         else:
#             link = "🔒 приватный чат"

#         result = (
#             f"📌 *Сообщение в {chat_title}:*\n\n"
#             f"{event.raw_text}\n\n"
#             f"🔗 {link}"
#         )

#         await client.send_message("me", result, parse_mode="markdown")
#         logging.info(f"Сработало ключевое слово в чате {chat_id}")


@client.on(events.NewMessage)
async def handle_message(event):
    chat = await event.get_chat()
    chat_id = event.chat_id
    message_text = event.raw_text

    me = await client.get_me()

    # --- обработка команд ---
    try:
        if chat_id == me.id and message_text.startswith('/'):
            await handle_command(event)
            return
    except AttributeError:
        logging.error("Ошибка получения me.id")

    # --- регистрация чата ---
    if chat_id not in KNOWN_CHATS:
        title = getattr(chat, 'title', f'ID {chat_id}')
        username = getattr(chat, 'username', None)
        KNOWN_CHATS[chat_id] = f"@{username}" if username else title

    logging.info(f"Сообщение из чата {chat_id}: {message_text[:100]}")

    # --- нормализация ---
    words = normalize(message_text)

    # --- ключевые слова ---
    has_keyword = any(word in KEYWORDS for word in words)
    if not has_keyword:
        has_keyword = any(fuzzy_match(word, KEYWORDS) for word in words)

    # --- фразы ---
    has_phrase = any(search_phrase(message_text, phrase) for phrase in PHRASES)

    if not (has_keyword or has_phrase):
        return

    # --- минус-слова ---
    if any(word in BLOCK_WORDS for word in words):
        logging.info("Сообщение отфильтровано минус-словами")
        return

    # --- анти-дубликат ---
    if message_history.is_duplicate(chat_id, message_text, KEYWORDS):
        logging.info(f"Дубликат в чате {chat_id}")
        return

    # --- добавляем в историю ---
    message_history.add_message(chat_id, message_text)

    # --- формируем ссылку ---
    if getattr(chat, 'username', None):
        link = f"https://t.me/{chat.username}/{event.id}"
    elif str(chat_id).startswith('-100'):
        link = f"https://t.me/c/{str(chat_id)[4:]}/{event.id}"
    else:
        link = "🔒 приватный чат"

    chat_title = KNOWN_CHATS[chat_id]

    result = (
        f"📌 *Сообщение в {chat_title}:*\n\n"
        f"{message_text}\n\n"
        f"🔗 {link}"
    )

    await client.send_message("me", result, parse_mode="markdown")
    logging.info(f"Сработало ключевое слово в чате {chat_id}")


# ====== COMMAND HANDLER ======
async def handle_command(event):
    cmd, *args = event.raw_text.strip().split(maxsplit=1)
    args = args[0] if args else ""

    if cmd == "/addword":
        words = {w.strip().lower() for w in args.split(',') if w.strip()}
        added = words - KEYWORDS
        KEYWORDS.update(added)
        save_words(KEYWORDS_FILE, KEYWORDS)
        logging.info(f"Добавлены ключевые слова: {added}")
        await event.reply(f"✅ Добавлено: {', '.join(added)}")

    elif cmd == "/addphrase":
        phrase = {w.strip().lower() for w in args.split(',') if w.strip()}
        added = phrase - PHRASES
        PHRASES.update(added)
        save_words(PHRASES_FILE, PHRASES)
        logging.info(f"Добавлены ключевые фразы: {added}")
        await event.reply(f"✅ Добавлено: {', '.join(added)}")

    elif cmd == "/delphrase":
        phrase = {w.strip().lower() for w in args.split(',') if w.strip()}
        removed = phrase & PHRASES
        PHRASES.difference_update(removed)
        save_words(PHRASES_FILE, PHRASES)
        logging.info(f"Удалены ключевые фразы: {removed}")
        await event.reply(f"🗑 Удалено: {', '.join(removed)}")

    elif cmd == "/delword":
        words = {w.strip().lower() for w in args.split(',') if w.strip()}
        removed = words & KEYWORDS
        KEYWORDS.difference_update(removed)
        save_words(KEYWORDS_FILE, KEYWORDS)
        logging.info(f"Удалены ключевые слова: {removed}")
        await event.reply(f"🗑 Удалено: {', '.join(removed)}")

    elif cmd == "/phrases":
        if KEYWORDS:
            await event.reply("📃 Ключевые фразы:\n" + "\n".join(f"• {w}" for w in sorted(PHRASES)))
        else:
            await event.reply("❗ Список ключевых фраз пуст.")

    elif cmd == "/keywords":
        if KEYWORDS:
            await event.reply("📃 Ключевые слова:\n" + "\n".join(f"• {w}" for w in sorted(KEYWORDS)))
        else:
            await event.reply("❗ Список ключевых слов пуст.")

    elif cmd == "/listchats":
        if KNOWN_CHATS:
            text = "📂 Известные чаты:\n\n"
            for cid, name in KNOWN_CHATS.items():
                text += f"• {name} — `{cid}`\n"
            await event.reply(text, parse_mode="markdown")
        else:
            await event.reply("❗ Бот пока не видел ни одного чата.")

    elif cmd == "/leavechat":
        try:
            cid = int(args.strip())
            await client(functions.messages.LeaveChatRequest(cid))
            KNOWN_CHATS.pop(cid, None)
            logging.info(f"Вышел из чата {cid}")
            await event.reply(f"👋 Вышел из чата `{cid}`", parse_mode="markdown")
        except Exception as e:
            logging.error(f"Ошибка выхода из чата: {e}")
            await event.reply(f"❌ Ошибка: {e}")

    elif cmd == "/addblack":
        words = {w.strip().lower() for w in args.split(',') if w.strip()}
        added = words - BLOCK_WORDS
        BLOCK_WORDS.update(added)
        save_words(BLOCKWORDS_FILE, BLOCK_WORDS)
        logging.info(f"Добавлены минус-слова: {added}")
        await event.reply(f"🚫 Добавлено в минус-слова: {', '.join(added)}")

    elif cmd == "/delblock":
        words = {w.strip().lower() for w in args.split(',') if w.strip()}
        removed = words & BLOCK_WORDS
        BLOCK_WORDS.difference_update(removed)
        save_words(BLOCKWORDS_FILE, BLOCK_WORDS)
        logging.info(f"Удалены минус-слова: {removed}")
        await event.reply(f"✅ Удалено из минус-слов: {', '.join(removed)}")

    elif cmd == "/blockwords":
        if BLOCK_WORDS:
            await event.reply("🚫 Минус-слова:\n" + "\n".join(f"• {w}" for w in sorted(BLOCK_WORDS)))
        else:
            await event.reply("📭 Минус-слов пока нет.")

    elif cmd == "/help":
        await event.reply(
            "📖 Команды:\n\n"
            "/addword слова через запятую (добавляет ключевые слова)\n"
            "/delword слова через запятую (удаляет ключевые слова)\n"
            "/keywords (показывает все ключевые слова)\n"
            "/addphrase (добавляет все ключевые фразы)\n"
            "/delphrase (удаляет все ключевые фразы)\n"
            "/phrases (удаляет все ключевые фразы)\n"
            "/listchats (показывает список чатов)\n"
            "/leavechat ID (покинуть чат)\n"
            "/addblack слова через запятую (добавляет минус слова)\n"
            "/delblock слова через запятую (удаляет минус слова)\n"
            "/blockwords (показывает все минус слова)\n"
        )
        
    else:
        await event.reply("🤖 Неизвестная команда.")

# ====== MAIN ====== 
async def main():
    await client.start()
    logging.info("Бот успешно запущен")
    print("✅ Userbot запущен. Пиши команды в ЛС самому себе.")
    await client.run_until_disconnected()

asyncio.run(main())
