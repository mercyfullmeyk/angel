from logging.handlers import RotatingFileHandler
from telethon import TelegramClient, events, functions
import asyncio
import logging
import os
import re


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

# ====== NOT REPLAYS ======


def normalize(text):
    return re.findall(r'\w+', text.lower())


def chek_match_words(w1, w2):
    '''Сравнивает два слова по трислогам'''
    if (len(w1) <= 3 or len(w2) <= 3) or w1 == w2:
        return w1 == w2 
    
    count_trislogs = 0
    max_trislogs = len(min([w1, w2], key=len)) - 2
    
    for x in range(0, len(min([w1, w2], key=len)) - 2):
        if w1[0 + x: 3 + x] == w2[0 + x: 3 + x]:
            count_trislogs += 1
            
    if count_trislogs/max_trislogs * 100 >= 50:
        return True
    
    return False


def chek_match(t1, t2):
    '''Показывает процент схожести текстов'''
    count_match = 0
    used_words = set()

    for word1 in t1:
        for word2 in t2:
            if word2 not in used_words and chek_match_words(word1, word2):
                count_match += 1
                used_words.add(word2)
                break

    # print(t1, t2)
    print((int(count_match / len(min([t1, t2], key=len)) * 100)))
    return (int(count_match / len(min([t1, t2], key=len)) * 100)) > 50


def check_replay(text1, text2):
    texts = [normalize(x) for x in [text1, text2]]
    return chek_match(*texts)


# ====== MESSAGE HISTORY ======
class MessageHistory:
    def __init__(self, max_size=100):
        self.max_size = max_size
        self.history = []  # список кортежей (chat_id, message_text, timestamp)
        
    def add_message(self, chat_id, message_text):
        """Добавляет сообщение в историю"""
        if len(self.history) >= self.max_size:
            self.history.pop(0)  # удаляем самое старое сообщение
            
        self.history.append((chat_id, message_text))
        
    def is_replay(self, new_chat_id, new_message_text, threshold=50):
        """Проверяет, является ли сообщение повтором"""
        for chat_id, old_message_text in self.history:
            if check_replay(old_message_text, new_message_text):
                return True
        return False
        
    def get_stats(self):
        """Возвращает статистику истории"""
        return f"Сообщений в истории: {len(self.history)}/{self.max_size}"


message_history = MessageHistory(max_size=100)


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

    # --- фразы ---
    has_phrase = any(search_phrase(message_text, phrase) for phrase in PHRASES)

    if not (has_keyword or has_phrase):
        return

    # --- минус-слова ---
    if any(word in BLOCK_WORDS for word in words):
        logging.info("Сообщение отфильтровано минус-словами")
        return

    if message_history.is_replay(chat_id, event.raw_text):
        logging.info(f"Сообщение из чата {chat_id} похоже на предыдущее - игнорируем")
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
