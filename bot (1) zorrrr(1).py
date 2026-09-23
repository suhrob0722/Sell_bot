#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════╗
║                    🎬 KODLI KINO BOT 🎬                      ║
║                  To'liq O'zbek Tilida                        ║
║                  Barcha funksiyalar bilan                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import logging
import sqlite3
import time
import json
from datetime import datetime, timedelta
from typing import Optional

import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ╔══════════════════════════════════════════════════════════════╗
# ║                    ⚙️ BOT SOZLAMALARI                        ║
# ╚══════════════════════════════════════════════════════════════╝

BOT_TOKEN = "8942959403:AAFZc3rGTkQRaal_KqramOaRWb-fqAhkaR8"
ADMIN_IDS = [8005460586]

# Majburiy obuna kanallar ro'yxati - bazadan o'qiladi
# Adminlar tugma orqali qo'shadi/o'chiradi
REQUIRED_CHANNELS = []

# Bot username (ishga tushganda avtomatik to'ldiriladi)
BOT_USERNAME = "sell_kino_bot"

# ╔══════════════════════════════════════════════════════════════╗
# ║                   📊 LOG SOZLAMALARI                         ║
# ╚══════════════════════════════════════════════════════════════╝

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ╔══════════════════════════════════════════════════════════════╗
# ║                   🤖 BOT YARATISH                            ║
# ╚══════════════════════════════════════════════════════════════╝

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# ╔══════════════════════════════════════════════════════════════╗
# ║               🗄️ MA'LUMOTLAR BAZASI                          ║
# ╚══════════════════════════════════════════════════════════════╝

def create_database():
    """Ma'lumotlar bazasini yaratish va jadvallarni sozlash"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()

    # Foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            status TEXT DEFAULT 'user',
            status_expires_at TEXT,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            bonus_points INTEGER DEFAULT 0,
            last_bonus_date TEXT,
            spam_count INTEGER DEFAULT 0,
            last_spam_time REAL DEFAULT 0,
            registered_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Eski bazaga status_expires_at ustunini qo'shish (agar yo'q bo'lsa)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN status_expires_at TEXT')
    except sqlite3.OperationalError:
        pass

    # Eski 'vip' statusli foydalanuvchilarni 'premium' ga o'tkazish
    cursor.execute("UPDATE users SET status = 'premium' WHERE status = 'vip'")

    # Kinolar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            file_id TEXT NOT NULL,
            file_type TEXT DEFAULT 'video',
            category TEXT DEFAULT 'Umumiy',
            is_vip INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            rating_sum INTEGER DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Reyting jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            movie_code TEXT NOT NULL,
            rating INTEGER NOT NULL,
            rated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, movie_code)
        )
    ''')

    # Statistika jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            movie_code TEXT NOT NULL,
            action TEXT NOT NULL,
            action_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Majburiy obuna kanallar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE NOT NULL,
            channel_name TEXT NOT NULL,
            channel_url TEXT NOT NULL,
            added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# ╔══════════════════════════════════════════════════════════════╗
# ║              📡 KANAL FUNKSIYALARI                            ║
# ╚══════════════════════════════════════════════════════════════╝

def get_channels() -> list:
    """Bazadan barcha majburiy kanallarni olish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id, channel_name, channel_url FROM channels')
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "url": r[2]} for r in rows]

def add_channel(channel_id: str, channel_name: str, channel_url: str, added_by: int) -> bool:
    """Yangi kanal qo'shish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO channels (channel_id, channel_name, channel_url, added_by) VALUES (?, ?, ?, ?)',
            (channel_id, channel_name, channel_url, added_by)
        )
        conn.commit()
        logger.info(f"✅ Yangi kanal qo'shildi: {channel_id}")
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_channel(channel_id: str) -> bool:
    """Kanalni o'chirish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    if affected > 0:
        logger.info(f"🗑️ Kanal o'chirildi: {channel_id}")
    return affected > 0

# ╔══════════════════════════════════════════════════════════════╗
# ║               👤 FOYDALANUVCHI FUNKSIYALARI                  ║
# ╚══════════════════════════════════════════════════════════════╝

def get_user(user_id: int) -> Optional[dict]:
    """Foydalanuvchini bazadan olish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        columns = ['id', 'user_id', 'username', 'full_name', 'status', 'referral_code',
                   'referred_by', 'referral_count', 'bonus_points', 'last_bonus_date',
                   'spam_count', 'last_spam_time', 'registered_at']
        return dict(zip(columns, row))
    return None

def register_user(user_id: int, username: str, full_name: str, referred_by: int = None) -> bool:
    """Yangi foydalanuvchini ro'yxatdan o'tkazish"""
    import random
    import string
    referral_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, referral_code, referred_by)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, full_name, referral_code, referred_by))

        # Referal bonus
        if referred_by:
            cursor.execute('''
                UPDATE users SET referral_count = referral_count + 1,
                bonus_points = bonus_points + 50
                WHERE user_id = ?
            ''', (referred_by,))

        conn.commit()
        logger.info(f"✅ Yangi foydalanuvchi ro'yxatdan o'tdi: {user_id} ({full_name})")
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_user_status(user_id: int, status: str, days: int = 0) -> bool:
    """Foydalanuvchi statusini yangilash. days=0 — cheksiz/standart"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    expires_at = None
    if status in ['premium'] and days > 0:
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    cursor.execute(
        'UPDATE users SET status = ?, status_expires_at = ? WHERE user_id = ?',
        (status, expires_at, user_id)
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def check_and_expire_status(user_id: int) -> str:
    """Foydalanuvchi statusi muddati tugaganmi tekshiradi va kerak bo'lsa standartga tushiradi"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status, status_expires_at FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return 'user'
    status, expires_at = row
    if status == 'premium' and expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now():
                cursor.execute(
                    'UPDATE users SET status = ?, status_expires_at = NULL WHERE user_id = ?',
                    ('user', user_id)
                )
                conn.commit()
                logger.info(f"⏰ Premium muddati tugadi: {user_id}")
                status = 'user'
        except Exception:
            pass
    conn.close()
    return status

def get_all_users() -> list:
    """Barcha foydalanuvchilarni olish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_users_count() -> dict:
    """Foydalanuvchilar sonini olish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status, COUNT(*) FROM users GROUP BY status')
    counts = dict(cursor.fetchall())
    cursor.execute('SELECT COUNT(*) FROM users')
    total = cursor.fetchone()[0]
    conn.close()
    counts['total'] = total
    return counts

def check_spam(user_id: int) -> bool:
    """Spam tekshirish - 1 daqiqada 10 ta xabardan ko'p yuborsa to'xtatish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT spam_count, last_spam_time FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False

    spam_count, last_spam_time = row
    current_time = time.time()

    if current_time - last_spam_time > 60:
        # 1 daqiqa o'tgan, hisoblagichni qayta boshlash
        conn = sqlite3.connect('kino_bot.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET spam_count = 1, last_spam_time = ? WHERE user_id = ?',
                      (current_time, user_id))
        conn.commit()
        conn.close()
        return False

    if spam_count >= 10:
        return True

    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET spam_count = spam_count + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return False

# ╔══════════════════════════════════════════════════════════════╗
# ║                🎬 KINO FUNKSIYALARI                          ║
# ╚══════════════════════════════════════════════════════════════╝

def get_movie(code: str) -> Optional[dict]:
    """Kino kodini qidirish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM movies WHERE code = ?', (code.strip(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        columns = ['id', 'code', 'title', 'description', 'file_id', 'file_type',
                   'category', 'is_vip', 'is_premium', 'views', 'rating_sum',
                   'rating_count', 'added_by', 'added_at']
        return dict(zip(columns, row))
    return None

def add_movie(code: str, title: str, description: str, file_id: str,
              file_type: str, category: str, is_vip: int, is_premium: int,
              added_by: int) -> bool:
    """Yangi kino qo'shish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO movies (code, title, description, file_id, file_type,
                               category, is_vip, is_premium, added_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (code, title, description, file_id, file_type, category,
              is_vip, is_premium, added_by))
        conn.commit()
        logger.info(f"✅ Yangi kino qo'shildi: [{code}] {title}")
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_movie(code: str) -> bool:
    """Kinoni o'chirish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM movies WHERE code = ?', (code,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def increment_views(code: str):
    """Ko'rishlar sonini oshirish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE movies SET views = views + 1 WHERE code = ?', (code,))
    conn.commit()
    conn.close()

def get_popular_movies(limit: int = 10) -> list:
    """Eng mashhur kinolar"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT code, title, views, category FROM movies ORDER BY views DESC LIMIT ?', (limit,))
    movies = cursor.fetchall()
    conn.close()
    return movies

def get_latest_movies(limit: int = 10) -> list:
    """So'nggi qo'shilgan kinolar"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT code, title, added_at, category FROM movies ORDER BY added_at DESC LIMIT ?', (limit,))
    movies = cursor.fetchall()
    conn.close()
    return movies

def get_movies_by_category(category: str) -> list:
    """Kategoriya bo'yicha kinolar"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT code, title, views FROM movies WHERE category = ?', (category,))
    movies = cursor.fetchall()
    conn.close()
    return movies

def search_movies(query: str) -> list:
    """Kino qidirish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT code, title, category FROM movies WHERE title LIKE ? OR description LIKE ?',
                  (f'%{query}%', f'%{query}%'))
    movies = cursor.fetchall()
    conn.close()
    return movies

def get_all_categories() -> list:
    """Barcha kategoriyalar"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT category, COUNT(*) as cnt FROM movies GROUP BY category')
    categories = cursor.fetchall()
    conn.close()
    return categories

def rate_movie(user_id: int, movie_code: str, rating: int) -> str:
    """Kinoni baholash"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO ratings (user_id, movie_code, rating) VALUES (?, ?, ?)',
                      (user_id, movie_code, rating))
        cursor.execute('UPDATE movies SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE code = ?',
                      (rating, movie_code))
        conn.commit()
        return "added"
    except sqlite3.IntegrityError:
        # Avvalgi baholashni yangilash
        cursor.execute('SELECT rating FROM ratings WHERE user_id = ? AND movie_code = ?',
                      (user_id, movie_code))
        old_rating = cursor.fetchone()[0]
        cursor.execute('UPDATE ratings SET rating = ? WHERE user_id = ? AND movie_code = ?',
                      (rating, user_id, movie_code))
        cursor.execute('UPDATE movies SET rating_sum = rating_sum - ? + ? WHERE code = ?',
                      (old_rating, rating, movie_code))
        conn.commit()
        return "updated"
    finally:
        conn.close()

# ╔══════════════════════════════════════════════════════════════╗
# ║              🏆 BONUS FUNKSIYALARI                           ║
# ╚══════════════════════════════════════════════════════════════╝

def claim_daily_bonus(user_id: int) -> tuple:
    """Kunlik bonus olish"""
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT last_bonus_date, bonus_points FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False, 0, "Foydalanuvchi topilmadi"

    last_bonus_date, current_points = row
    today = datetime.now().strftime('%Y-%m-%d')

    if last_bonus_date == today:
        next_bonus = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
        time_left = next_bonus - datetime.now()
        hours = int(time_left.seconds / 3600)
        minutes = int((time_left.seconds % 3600) / 60)
        return False, current_points, f"{hours} soat {minutes} daqiqadan so'ng"

    bonus = 100
    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET bonus_points = bonus_points + ?, last_bonus_date = ? WHERE user_id = ?',
                  (bonus, today, user_id))
    conn.commit()
    conn.close()
    return True, current_points + bonus, str(bonus)

# ╔══════════════════════════════════════════════════════════════╗
# ║              ✅ OBUNA TEKSHIRISH                              ║
# ╚══════════════════════════════════════════════════════════════╝

def check_subscription(user_id: int) -> tuple:
    """Kanalga obunani tekshirish"""
    channels = get_channels()
    if not channels:
        # Hech qanday kanal qo'shilmagan bo'lsa, hammasi obunada deb hisoblanadi
        return True, []
    not_subscribed = []
    for channel in channels:
        try:
            member = bot.get_chat_member(channel['id'], user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Kanal tekshirishda xato ({channel['id']}): {e}")
            not_subscribed.append(channel)
    return len(not_subscribed) == 0, not_subscribed

# ╔══════════════════════════════════════════════════════════════╗
# ║              🎨 KLAVIATURA FUNKSIYALARI                      ║
# ╚══════════════════════════════════════════════════════════════╝

def get_main_keyboard(user_status: str = 'user') -> ReplyKeyboardMarkup:
    """Asosiy reply klaviatura"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    keyboard.add(
        KeyboardButton("🎬 Kino Izlash"),
        KeyboardButton("🔍 Qidiruv")
    )
    keyboard.add(
        KeyboardButton("⭐ Mashhur Kinolar"),
        KeyboardButton("🆕 Yangi Kinolar")
    )
    keyboard.add(
        KeyboardButton("📂 Kategoriyalar"),
        KeyboardButton("👤 Profilim")
    )
    keyboard.add(
        KeyboardButton("🎁 Kunlik Bonus"),
        KeyboardButton("👥 Referal")
    )
    keyboard.add(
        KeyboardButton("❓ Yordam"),
        KeyboardButton("📞 Bog'lanish")
    )

    if user_status in ['admin'] + ADMIN_IDS:
        keyboard.add(KeyboardButton("⚙️ Admin Panel"))

    return keyboard

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Admin panel klaviaturasi"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("➕ Kino Qo'shish"),
        KeyboardButton("🗑️ Kino O'chirish")
    )
    keyboard.add(
        KeyboardButton("📊 Statistika"),
        KeyboardButton("👥 Foydalanuvchilar")
    )
    keyboard.add(
        KeyboardButton("📢 Broadcast"),
        KeyboardButton("💎 Status Berish")
    )
    keyboard.add(
        KeyboardButton("📡 Kanal Sozlash"),
        KeyboardButton("🔙 Orqaga")
    )
    return keyboard

def get_subscription_keyboard(channels: list) -> InlineKeyboardMarkup:
    """Obuna bo'lish tugmalari"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    for channel in channels:
        keyboard.add(InlineKeyboardButton(
            f"📢 {channel['name']}",
            url=channel['url']
        ))
    keyboard.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription"))
    return keyboard

def get_rating_keyboard(movie_code: str) -> InlineKeyboardMarkup:
    """Reyting tugmalari"""
    keyboard = InlineKeyboardMarkup(row_width=5)
    buttons = [
        InlineKeyboardButton(f"{'⭐' * i}", callback_data=f"rate_{movie_code}_{i}")
        for i in range(1, 6)
    ]
    keyboard.add(*buttons)
    return keyboard

def show_channels_menu(user_id: int):
    """Admin uchun kanallar menyusini ko'rsatish"""
    channels = get_channels()
    keyboard = InlineKeyboardMarkup(row_width=1)

    if not channels:
        text = (
            "📡 <b>MAJBURIY KANALLAR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "ℹ️ Hozircha hech qanday kanal qo'shilmagan.\n"
            "Foydalanuvchilar bemalol botdan foydalanishi mumkin.\n\n"
            "➕ <b>Yangi kanal qo'shish</b> tugmasini bosing:"
        )
    else:
        text = "📡 <b>MAJBURIY KANALLAR</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, ch in enumerate(channels, 1):
            text += f"{i}. {ch['name']}\n   🆔 <code>{ch['id']}</code>\n   🔗 {ch['url']}\n\n"
            keyboard.add(InlineKeyboardButton(
                f"🗑️ O'chirish: {ch['name']}",
                callback_data=f"chremove_{ch['id']}"
            ))

    keyboard.add(InlineKeyboardButton("➕ Yangi Kanal Qo'shish", callback_data="chadd_start"))
    bot.send_message(user_id, text, reply_markup=keyboard)


def get_category_keyboard() -> InlineKeyboardMarkup:
    """Kategoriya tugmalari"""
    categories = get_all_categories()
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(f"🎬 {cat[0]} ({cat[1]})", callback_data=f"category_{cat[0]}")
        for cat in categories
    ]
    keyboard.add(*buttons)
    return keyboard

# ╔══════════════════════════════════════════════════════════════╗
# ║              📨 XABAR YUBORISH FUNKSIYALARI                   ║
# ╚══════════════════════════════════════════════════════════════╝

def send_movie(chat_id: int, movie: dict, user_status: str):
    """Kinoni yuborish"""
    # Premium kinolarni tekshirish (is_vip va is_premium ikkalasi ham premium hisoblanadi)
    if (movie['is_vip'] or movie['is_premium']) and user_status not in ['premium', 'admin']:
        bot.send_message(
            chat_id,
            "💎 <b>Bu kino faqat PREMIUM foydalanuvchilar uchun!</b>\n\n"
            "Premium status olish uchun admin bilan bog'laning.",
        )
        return

    # Reklama (standart foydalanuvchilar uchun)
    if user_status == 'user':
        bot.send_message(
            chat_id,
            "📢 <b>Reklama</b>\n"
            "Bu reklama Premium foydalanuvchilar uchun ko'rsatilmaydi!"
        )
        time.sleep(0.5)

    # Kino ma'lumotlari
    rating = 0
    if movie['rating_count'] > 0:
        rating = movie['rating_sum'] / movie['rating_count']

    stars = '⭐' * round(rating) if rating > 0 else '❌ Baholanmagan'

    caption = (
        f"🎬 <b>{movie['title']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Tavsif:</b> {movie['description'] or 'Mavjud emas'}\n"
        f"📂 <b>Kategoriya:</b> {movie['category']}\n"
        f"🔢 <b>Kod:</b> <code>{movie['code']}</code>\n"
        f"👁️ <b>Ko'rishlar:</b> {movie['views']}\n"
        f"⭐ <b>Reyting:</b> {stars} ({rating:.1f}/5.0)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📺 @your_channel_1"
    )

    rating_keyboard = get_rating_keyboard(movie['code'])

    try:
        if movie['file_type'] == 'video':
            bot.send_video(
                chat_id,
                video=movie['file_id'],
                caption=caption,
                reply_markup=rating_keyboard
            )
        elif movie['file_type'] == 'document':
            bot.send_document(
                chat_id,
                document=movie['file_id'],
                caption=caption,
                reply_markup=rating_keyboard
            )
        elif movie['file_type'] == 'photo':
            bot.send_photo(
                chat_id,
                photo=movie['file_id'],
                caption=caption,
                reply_markup=rating_keyboard
            )
        else:
            bot.send_message(chat_id, caption, reply_markup=rating_keyboard)

        # Ko'rishlar sonini oshirish
        increment_views(movie['code'])
        logger.info(f"✅ Kino yuborildi: [{movie['code']}] {movie['title']} -> {chat_id}")

    except Exception as e:
        logger.error(f"❌ Kino yuborishda xato: {e}")
        bot.send_message(chat_id, "❌ Kinoni yuborishda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")

# ╔══════════════════════════════════════════════════════════════╗
# ║              🎮 HOLATLAR BOSHQARISH (STATE)                   ║
# ╚══════════════════════════════════════════════════════════════╝

user_states = {}

def set_state(user_id: int, state: str, data: dict = None):
    """Foydalanuvchi holatini saqlash"""
    user_states[user_id] = {'state': state, 'data': data or {}}

def get_state(user_id: int) -> dict:
    """Foydalanuvchi holatini olish"""
    return user_states.get(user_id, {})

def clear_state(user_id: int):
    """Foydalanuvchi holatini tozalash"""
    user_states.pop(user_id, None)

# ╔══════════════════════════════════════════════════════════════╗
# ║                  📩 KOMANDALAR                               ║
# ╚══════════════════════════════════════════════════════════════╝

@bot.message_handler(commands=['start'])
def start_handler(message):
    """Start komandasi"""
    user_id = message.from_user.id
    username = message.from_user.username or ''
    full_name = message.from_user.full_name or 'Anonim'

    # Referal tekshirish
    referred_by = None
    if len(message.text.split()) > 1:
        ref_part = message.text.split()[1]
        if ref_part.startswith('ref_'):
            try:
                referred_by = int(ref_part.replace('ref_', ''))
                if referred_by == user_id:
                    referred_by = None
            except ValueError:
                pass

    # Ro'yxatdan o'tkazish
    user = get_user(user_id)
    if not user:
        register_user(user_id, username, full_name, referred_by)
        user = get_user(user_id)
        logger.info(f"🆕 Yangi foydalanuvchi: {user_id} ({full_name})")
        if referred_by:
            try:
                bot.send_message(
                    referred_by,
                    f"🎉 <b>Yangi referal!</b>\n"
                    f"👤 {full_name} sizning havolangiz orqali ro'yxatdan o'tdi!\n"
                    f"💰 +50 bonus ball qo'shildi!"
                )
            except Exception:
                pass

    # Obuna tekshirish
    is_subscribed, not_subscribed = check_subscription(user_id)

    if not is_subscribed:
        keyboard = get_subscription_keyboard(not_subscribed)
        bot.send_message(
            user_id,
            f"👋 Salom, <b>{full_name}</b>!\n\n"
            f"🎬 <b>KODLI KINO BOT</b>ga xush kelibsiz!\n\n"
            f"⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz shart:\n\n"
            + "\n".join([f"➡️ {ch['name']}" for ch in not_subscribed]) +
            f"\n\n✅ Obuna bo'lgandan so'ng <b>Tekshirish</b> tugmasini bosing.",
            reply_markup=keyboard
        )
        return

    # Asosiy menyu
    user_status = user.get('status', 'user')
    keyboard = get_main_keyboard(user_status)

    status_emoji = {'user': '👤', 'premium': '💎', 'admin': '👑'}.get(user_status, '👤')
    status_name = {'user': 'Standard', 'premium': 'Premium', 'admin': 'Admin'}.get(user_status, 'Standard')

    welcome_text = (
        f"🎬 <b>KODLI KINO BOT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 Xush kelibsiz, <b>{full_name}</b>!\n\n"
        f"{status_emoji} <b>Sizning statusingiz:</b> {status_name}\n\n"
        f"🎯 <b>Qanday ishlaydi?</b>\n"
        f"Shunchaki kino kodini yuboring (masalan: <code>101</code>)\n"
        f"va siz istagan kinoni olasiz!\n\n"
        f"📌 <b>Asosiy buyruqlar:</b>\n"
        f"/start - Bosh sahifa\n"
        f"/help - Yordam\n"
        f"/profile - Profilim\n"
        f"/bonus - Kunlik bonus\n"
        f"/referral - Referal tizim\n"
        f"/search - Kino qidirish\n\n"
        f"🎬 <b>Kino kodini kiriting!</b>"
    )

    bot.send_message(user_id, welcome_text, reply_markup=keyboard)

@bot.message_handler(commands=['help'])
def help_handler(message):
    """Yordam komandasi"""
    help_text = (
        f"❓ <b>BOT HAQIDA YORDAM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 <b>Kino olish:</b>\n"
        f"Kino kodini yozing (masalan: <code>101</code>)\n\n"
        f"🔍 <b>Qidiruv:</b>\n"
        f"Kino nomini yozing yoki /search buyrug'ini ishlating\n\n"
        f"⭐ <b>Mashhur kinolar:</b>\n"
        f"<code>Mashhur Kinolar</code> tugmasini bosing\n\n"
        f"🆕 <b>Yangi kinolar:</b>\n"
        f"<code>Yangi Kinolar</code> tugmasini bosing\n\n"
        f"📂 <b>Kategoriyalar:</b>\n"
        f"<code>Kategoriyalar</code> tugmasini bosing\n\n"
        f"🎁 <b>Kunlik Bonus:</b>\n"
        f"Har kuni 100 ball olasiz!\n\n"
        f"👥 <b>Referal:</b>\n"
        f"Havolangizni ulashing va har bir do'stingiz uchun 50 ball oling!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>PREMIUM afzalliklari:</b>\n"
        f"✅ Reklamasiz foydalanish\n"
        f"✅ Tezkor kino olish\n"
        f"✅ Maxsus kinolarga kirish\n\n"
        f"📩 Savol va takliflar uchun: /contact"
    )
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['profile'])
def profile_handler(message):
    """Profil komandasi"""
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user:
        bot.send_message(user_id, "❌ Siz hali ro'yxatdan o'tmagansiz. /start bosing.")
        return

    status_emoji = {'user': '👤', 'premium': '💎', 'admin': '👑'}.get(user['status'], '👤')
    status_name = {'user': 'Standard', 'premium': 'Premium', 'admin': 'Admin'}.get(user['status'], 'Standard')

    expiry_text = ""
    if user['status'] == 'premium' and user.get('status_expires_at'):
        try:
            exp = datetime.fromisoformat(user['status_expires_at'])
            expiry_text = f"⏰ <b>Premium tugaydi:</b> {exp.strftime('%Y-%m-%d %H:%M')}\n"
        except Exception:
            pass

    profile_text = (
        f"👤 <b>PROFILIM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"👤 <b>Ism:</b> {user['full_name']}\n"
        f"📱 <b>Username:</b> @{user['username'] or 'Mavjud emas'}\n"
        f"{status_emoji} <b>Status:</b> {status_name}\n"
        f"{expiry_text}"
        f"💰 <b>Bonus ball:</b> {user['bonus_points']}\n"
        f"👥 <b>Referallar:</b> {user['referral_count']} kishi\n"
        f"🔗 <b>Referal kod:</b> <code>{user['referral_code']}</code>\n"
        f"📅 <b>Ro'yxatdan:</b> {user['registered_at'][:10]}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Referal havola:</b>\n"
        f"<code>https://t.me/{BOT_USERNAME}?start=ref_{user['user_id']}</code>"
    )

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🎁 Kunlik Bonus", callback_data="daily_bonus"))
    keyboard.add(InlineKeyboardButton("👥 Referal Tizim", callback_data="referral_info"))

    bot.send_message(user_id, profile_text, reply_markup=keyboard)

@bot.message_handler(commands=['bonus'])
def bonus_command(message):
    """Bonus komandasi"""
    user_id = message.from_user.id
    success, points, info = claim_daily_bonus(user_id)

    if success:
        bot.send_message(
            user_id,
            f"🎁 <b>Kunlik Bonus!</b>\n\n"
            f"✅ Siz {info} ball oldingiz!\n"
            f"💰 Jami ballingiz: <b>{points}</b>\n\n"
            f"⏰ Ertaga yana qaytib keling!"
        )
    else:
        bot.send_message(
            user_id,
            f"⏰ <b>Kunlik Bonus</b>\n\n"
            f"❌ Siz bugun allaqachon bonus oldingiz!\n"
            f"⏳ Keyingi bonus: <b>{info}</b>\n"
            f"💰 Hozirgi ballingiz: <b>{points}</b>"
        )

@bot.message_handler(commands=['referral'])
def referral_command(message):
    """Referal komandasi"""
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user:
        bot.send_message(user_id, "❌ /start bosing.")
        return

    referral_text = (
        f"👥 <b>REFERAL TIZIM</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Qanday ishlaydi?</b>\n"
        f"Do'stlaringizga referal havolangizni yuboring.\n"
        f"Har bir ro'yxatdan o'tgan do'stingiz uchun <b>50 ball</b> olasiz!\n\n"
        f"📊 <b>Sizning statistikangiz:</b>\n"
        f"👤 Jami referallar: <b>{user['referral_count']}</b> kishi\n"
        f"💰 Referal bonus: <b>{user['referral_count'] * 50}</b> ball\n\n"
        f"🔗 <b>Sizning havolangiz:</b>\n"
        f"<code>https://t.me/{BOT_USERNAME}?start=ref_{user['user_id']}</code>\n\n"
        f"📋 <b>Sizning kodingiz:</b> <code>{user['referral_code']}</code>"
    )

    bot.send_message(user_id, referral_text)

@bot.message_handler(commands=['search'])
def search_command(message):
    """Qidiruv komandasi"""
    user_id = message.from_user.id
    if len(message.text.split()) > 1:
        query = ' '.join(message.text.split()[1:])
        do_search(user_id, query)
    else:
        set_state(user_id, 'searching')
        bot.send_message(
            user_id,
            "🔍 <b>Kino Qidirish</b>\n\n"
            "Qidirmoqchi bo'lgan kino nomini yozing:",
            reply_markup=types.ForceReply()
        )

def do_search(user_id: int, query: str):
    """Qidiruv natijalarini yuborish"""
    results = search_movies(query)

    if not results:
        bot.send_message(
            user_id,
            f"🔍 '<b>{query}</b>' bo'yicha hech narsa topilmadi.\n\n"
            f"💡 Boshqa kalit so'z bilan urinib ko'ring."
        )
        return

    text = f"🔍 '<b>{query}</b>' bo'yicha natijalar:\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = InlineKeyboardMarkup(row_width=2)

    for i, movie in enumerate(results[:10], 1):
        code, title, category = movie
        text += f"{i}. 🎬 <b>{title}</b>\n   📂 {category} | 🔢 Kod: <code>{code}</code>\n\n"
        keyboard.add(InlineKeyboardButton(
            f"🎬 {title[:25]}...",
            callback_data=f"get_movie_{code}"
        ) if len(title) > 25 else InlineKeyboardButton(
            f"🎬 {title}",
            callback_data=f"get_movie_{code}"
        ))

    bot.send_message(user_id, text, reply_markup=keyboard)

# ╔══════════════════════════════════════════════════════════════╗
# ║               👑 ADMIN KOMANDALAR                            ║
# ╚══════════════════════════════════════════════════════════════╝

def is_admin(user_id: int) -> bool:
    """Admin tekshirish"""
    return user_id in ADMIN_IDS

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """Admin paneli"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Sizda admin huquqlari yo'q!")
        return

    counts = get_users_count()
    admin_text = (
        f"👑 <b>ADMIN PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Statistika:</b>\n"
        f"👤 Jami foydalanuvchilar: <b>{counts.get('total', 0)}</b>\n"
        f"👤 Oddiy: <b>{counts.get('user', 0)}</b>\n"
        f"💎 Premium: <b>{counts.get('premium', 0)}</b>\n\n"
        f"🎬 <b>Kino boshqarish:</b>\n"
        f"➕ Kino qo'shish: /addmovie\n"
        f"🗑️ Kino o'chirish: /deletemovie\n"
        f"📢 Xabar yuborish: /broadcast\n"
        f"💎 Status berish: /setstatus\n"
    )

    bot.send_message(user_id, admin_text, reply_markup=get_admin_keyboard())

@bot.message_handler(commands=['addmovie'])
def add_movie_command(message):
    """Kino qo'shish"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Sizda admin huquqlari yo'q!")
        return

    set_state(user_id, 'add_movie_code')
    bot.send_message(
        user_id,
        "➕ <b>Yangi Kino Qo'shish</b>\n\n"
        "1️⃣ Avvalo kino kodini kiriting (masalan: <code>101</code>):",
        reply_markup=types.ForceReply()
    )

@bot.message_handler(commands=['deletemovie'])
def delete_movie_command(message):
    """Kino o'chirish"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Sizda admin huquqlari yo'q!")
        return

    set_state(user_id, 'delete_movie')
    bot.send_message(
        user_id,
        "🗑️ <b>Kino O'chirish</b>\n\n"
        "O'chirmoqchi bo'lgan kino kodini kiriting:",
        reply_markup=types.ForceReply()
    )

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    """Broadcast komandasi"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Sizda admin huquqlari yo'q!")
        return

    set_state(user_id, 'broadcast')
    bot.send_message(
        user_id,
        "📢 <b>Broadcast</b>\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing:\n\n"
        "⚠️ Eslatma: Bu xabar <b>barcha foydalanuvchilarga</b> yuboriladi!",
        reply_markup=types.ForceReply()
    )

@bot.message_handler(commands=['setstatus'])
def set_status_command(message):
    """Status berish komandasi"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Sizda admin huquqlari yo'q!")
        return

    # Format: /setstatus USER_ID STATUS
    parts = message.text.split()
    is_command = message.text.startswith('/setstatus')
    if is_command and len(parts) == 3:
        try:
            target_id = int(parts[1])
            new_status = parts[2].lower()
            if new_status not in ['user', 'premium', 'admin']:
                bot.send_message(user_id, "❌ Noto'g'ri status! (user/premium/admin)")
                return

            if update_user_status(target_id, new_status):
                status_names = {'user': 'Standard', 'premium': 'Premium', 'admin': 'Admin'}
                bot.send_message(
                    user_id,
                    f"✅ Foydalanuvchi {target_id} statusiga <b>{status_names[new_status]}</b> berildi!"
                )
                try:
                    bot.send_message(
                        target_id,
                        f"🎉 <b>Tabriklaymiz!</b>\n\n"
                        f"Sizga <b>{status_names[new_status]}</b> statusli berildi!\n"
                        f"Yangi imkoniyatlardan bahramand bo'ling! 🚀"
                    )
                except Exception:
                    pass
            else:
                bot.send_message(user_id, "❌ Foydalanuvchi topilmadi!")
        except ValueError:
            bot.send_message(user_id, "❌ Noto'g'ri format! /setstatus USER_ID STATUS")
    else:
        set_state(user_id, 'set_status_id')
        bot.send_message(
            user_id,
            "💎 <b>Status Berish</b>\n\n"
            "Format: /setstatus USER_ID STATUS\n"
            "Masalan: /setstatus 123456789 premium\n\n"
            "Yoki foydalanuvchi ID sini kiriting:",
            reply_markup=types.ForceReply()
        )

@bot.message_handler(commands=['stats'])
def stats_command(message):
    """Statistika komandasi"""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Sizda admin huquqlari yo'q!")
        return

    conn = sqlite3.connect('kino_bot.db')
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM movies')
    total_movies = cursor.fetchone()[0]

    cursor.execute('SELECT SUM(views) FROM movies')
    total_views = cursor.fetchone()[0] or 0

    cursor.execute('SELECT code, title, views FROM movies ORDER BY views DESC LIMIT 3')
    top_movies = cursor.fetchall()

    cursor.execute('SELECT status, COUNT(*) FROM users GROUP BY status')
    status_counts = dict(cursor.fetchall())

    conn.close()

    top_text = "\n".join([f"  {i+1}. {m[1]} - {m[2]} marta" for i, m in enumerate(top_movies)])

    stats_text = (
        f"📊 <b>BOT STATISTIKASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Foydalanuvchilar:</b>\n"
        f"  👤 Jami: <b>{total_users}</b>\n"
        f"  👤 Oddiy: <b>{status_counts.get('user', 0)}</b>\n"
        f"  💎 Premium: <b>{status_counts.get('premium', 0)}</b>\n"
        f"  👑 Admin: <b>{status_counts.get('admin', 0)}</b>\n\n"
        f"🎬 <b>Kinolar:</b>\n"
        f"  Jami kinolar: <b>{total_movies}</b>\n"
        f"  Jami ko'rishlar: <b>{total_views}</b>\n\n"
        f"🏆 <b>Top 3 Kino:</b>\n"
        f"{top_text or '  Hali korish yoq'}"
    )

    bot.send_message(user_id, stats_text)

# ╔══════════════════════════════════════════════════════════════╗
# ║            📨 XABAR HANDLERLARI (HOLATLAR)                   ║
# ╚══════════════════════════════════════════════════════════════╝

@bot.message_handler(content_types=['text'])
def text_handler(message):
    """Matn xabarlarini boshqarish"""
    user_id = message.from_user.id
    text = message.text.strip()

    # Spam tekshirish
    if check_spam(user_id):
        bot.send_message(
            user_id,
            "⚠️ <b>Spam aniqlandi!</b>\n\n"
            "Siz juda ko'p xabar yubordingiz. Iltimos, 1 daqiqa kuting."
        )
        return

    # Obuna tekshirish
    is_subscribed, not_subscribed = check_subscription(user_id)
    if not is_subscribed:
        keyboard = get_subscription_keyboard(not_subscribed)
        bot.send_message(
            user_id,
            "⚠️ <b>Avval kanallarga obuna bo'ling!</b>",
            reply_markup=keyboard
        )
        return

    user = get_user(user_id)
    if not user:
        register_user(user_id, message.from_user.username or '', message.from_user.full_name or '')
        user = get_user(user_id)

    user_status = user.get('status', 'user')
    state = get_state(user_id)

    # Holat bo'yicha xabarlarni boshqarish
    if state.get('state') == 'searching':
        clear_state(user_id)
        do_search(user_id, text)
        return

    if state.get('state') == 'broadcast' and is_admin(user_id):
        clear_state(user_id)
        do_broadcast(user_id, text)
        return

    if state.get('state') == 'delete_movie' and is_admin(user_id):
        clear_state(user_id)
        if delete_movie(text):
            bot.send_message(user_id, f"✅ Kino <code>{text}</code> o'chirildi!")
        else:
            bot.send_message(user_id, f"❌ <code>{text}</code> kodli kino topilmadi!")
        return

    if state.get('state') == 'add_movie_code' and is_admin(user_id):
        if get_movie(text):
            bot.send_message(user_id, f"❌ <code>{text}</code> kodli kino allaqachon mavjud!")
            clear_state(user_id)
            return
        set_state(user_id, 'add_movie_title', {'code': text})
        bot.send_message(
            user_id,
            f"✅ Kod: <code>{text}</code>\n\n"
            f"2️⃣ Kino nomini kiriting:"
        )
        return

    if state.get('state') == 'add_movie_title' and is_admin(user_id):
        data = state.get('data', {})
        data['title'] = text
        set_state(user_id, 'add_movie_description', data)
        bot.send_message(
            user_id,
            f"✅ Nom: <b>{text}</b>\n\n"
            f"3️⃣ Kino tavsifini kiriting (yoki 'skip' yozing):"
        )
        return

    if state.get('state') == 'add_movie_description' and is_admin(user_id):
        data = state.get('data', {})
        data['description'] = '' if text.lower() == 'skip' else text
        set_state(user_id, 'add_movie_category', data)
        keyboard = InlineKeyboardMarkup(row_width=2)
        categories_list = ['Uzbek Kino', 'Xorij Kino', 'Multfilm', 'Serial', 'Hujjatli', 'Boshqa']
        for cat in categories_list:
            keyboard.add(InlineKeyboardButton(cat, callback_data=f"admin_cat_{cat}"))
        bot.send_message(
            user_id,
            f"4️⃣ Kategoriyani tanlang:",
            reply_markup=keyboard
        )
        return

    if state.get('state') == 'add_movie_vip' and is_admin(user_id):
        # VIP bosqichi olib tashlandi - to'g'ridan-to'g'ri premium so'raymiz
        data = state.get('data', {})
        data['is_vip'] = 0
        data['is_premium'] = 1 if text.lower() in ['ha', 'yes', '1'] else 0
        set_state(user_id, 'add_movie_file', data)
        bot.send_message(user_id, "6️⃣ Video yoki faylni yuboring:")
        return

    if state.get('state') == 'add_movie_premium' and is_admin(user_id):
        data = state.get('data', {})
        data['is_premium'] = 1 if text.lower() in ['ha', 'yes', '1'] else 0
        set_state(user_id, 'add_movie_file', data)
        bot.send_message(user_id, "7️⃣ Video yoki faylni yuboring:")
        return

    if state.get('state') == 'add_channel_id' and is_admin(user_id):
        ch_id = text.strip()
        if not ch_id.startswith('@') and not ch_id.startswith('-'):
            ch_id = '@' + ch_id
        set_state(user_id, 'add_channel_name', {'channel_id': ch_id})
        bot.send_message(
            user_id,
            f"✅ Kanal ID: <code>{ch_id}</code>\n\n"
            f"2️⃣ Endi kanal nomini kiriting (masalan: <b>📢 Asosiy Kanal</b>):"
        )
        return

    if state.get('state') == 'add_channel_name' and is_admin(user_id):
        data = state.get('data', {})
        data['channel_name'] = text.strip()
        set_state(user_id, 'add_channel_url', data)
        bot.send_message(
            user_id,
            f"✅ Nomi: <b>{text}</b>\n\n"
            f"3️⃣ Endi kanal havolasini kiriting (masalan: <code>https://t.me/kanal_username</code>):"
        )
        return

    if state.get('state') == 'add_channel_url' and is_admin(user_id):
        data = state.get('data', {})
        ch_url = text.strip()
        if not ch_url.startswith('http'):
            ch_url = 'https://t.me/' + ch_url.lstrip('@')

        success = add_channel(
            channel_id=data['channel_id'],
            channel_name=data['channel_name'],
            channel_url=ch_url,
            added_by=user_id
        )
        clear_state(user_id)

        if success:
            bot.send_message(
                user_id,
                f"✅ <b>Kanal muvaffaqiyatli qo'shildi!</b>\n\n"
                f"🆔 ID: <code>{data['channel_id']}</code>\n"
                f"📢 Nomi: <b>{data['channel_name']}</b>\n"
                f"🔗 Havola: {ch_url}\n\n"
                f"⚠️ <b>Eslatma:</b> Botni shu kanalga admin qilib qo'shing!"
            )
            show_channels_menu(user_id)
        else:
            bot.send_message(user_id, f"❌ Bu kanal allaqachon qo'shilgan: <code>{data['channel_id']}</code>")
        return

    if state.get('state') == 'set_status_id' and is_admin(user_id):
        try:
            target_id = int(text)
            set_state(user_id, 'set_status_value', {'target_id': target_id})
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("👤 Standard", callback_data=f"setstatus_{target_id}_user"),
                InlineKeyboardButton("💎 Premium", callback_data=f"setstatus_{target_id}_premium"),
                InlineKeyboardButton("👑 Admin", callback_data=f"setstatus_{target_id}_admin")
            )
            bot.send_message(
                user_id,
                f"👤 Foydalanuvchi: <code>{target_id}</code>\n\nStatusni tanlang:",
                reply_markup=keyboard
            )
        except ValueError:
            bot.send_message(user_id, "❌ Noto'g'ri ID! Faqat raqam kiriting.")
            clear_state(user_id)
        return

    # Tugmalar
    if text == "🎬 Kino Izlash":
        bot.send_message(
            user_id,
            "🎬 <b>Kino Kodini Kiriting</b>\n\n"
            "Kino kodini yozing (masalan: <code>101</code>):\n\n"
            "💡 Kod odatda 3 xonali raqam bo'ladi."
        )
        return

    if text == "🔍 Qidiruv":
        set_state(user_id, 'searching')
        bot.send_message(
            user_id,
            "🔍 <b>Kino Qidirish</b>\n\n"
            "Qidirmoqchi bo'lgan kino nomini yozing:"
        )
        return

    if text == "⭐ Mashhur Kinolar":
        movies = get_popular_movies(10)
        if not movies:
            bot.send_message(user_id, "📭 Hali kinolar yo'q.")
            return
        text_msg = "⭐ <b>ENG MASHHUR KINOLAR</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        keyboard = InlineKeyboardMarkup(row_width=1)
        for i, (code, title, views, category) in enumerate(movies, 1):
            text_msg += f"{i}. 🎬 <b>{title}</b>\n   👁️ {views} | 📂 {category} | 🔢 <code>{code}</code>\n\n"
            keyboard.add(InlineKeyboardButton(f"▶️ {title[:30]}", callback_data=f"get_movie_{code}"))
        bot.send_message(user_id, text_msg, reply_markup=keyboard)
        return

    if text == "🆕 Yangi Kinolar":
        movies = get_latest_movies(10)
        if not movies:
            bot.send_message(user_id, "📭 Hali kinolar yo'q.")
            return
        text_msg = "🆕 <b>YANGI KINOLAR</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        keyboard = InlineKeyboardMarkup(row_width=1)
        for i, (code, title, added_at, category) in enumerate(movies, 1):
            date_str = added_at[:10] if added_at else 'N/A'
            text_msg += f"{i}. 🎬 <b>{title}</b>\n   📅 {date_str} | 📂 {category} | 🔢 <code>{code}</code>\n\n"
            keyboard.add(InlineKeyboardButton(f"▶️ {title[:30]}", callback_data=f"get_movie_{code}"))
        bot.send_message(user_id, text_msg, reply_markup=keyboard)
        return

    if text == "📂 Kategoriyalar":
        categories = get_all_categories()
        if not categories:
            bot.send_message(user_id, "📭 Hali kategoriyalar yo'q.")
            return
        keyboard = get_category_keyboard()
        bot.send_message(user_id, "📂 <b>KATEGORIYALAR</b>\n\nQuyidagi kategoriyalardan birini tanlang:", reply_markup=keyboard)
        return

    if text == "👤 Profilim":
        profile_handler(message)
        return

    if text == "🎁 Kunlik Bonus":
        bonus_command(message)
        return

    if text == "👥 Referal":
        referral_command(message)
        return

    if text == "❓ Yordam":
        help_handler(message)
        return

    if text == "📞 Bog'lanish":
        bot.send_message(
            user_id,
            "📞 <b>BOG'LANISH</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💬 Savol va takliflaringiz bo'lsa,\n"
            "admin bilan bog'laning:\n\n"
            "👤 Admin: @your_admin_username\n"
            "📢 Kanal: @kinovibe_uzzz\n\n"
            "🕐 24/7 javob beramiz!"
        )
        return

    if text == "⚙️ Admin Panel" and is_admin(user_id):
        admin_panel(message)
        return

    if text == "🔙 Orqaga":
        keyboard = get_main_keyboard(user_status)
        bot.send_message(user_id, "🏠 Bosh sahifa", reply_markup=keyboard)
        return

    # Admin tugmalari
    if is_admin(user_id):
        if text == "➕ Kino Qo'shish":
            add_movie_command(message)
            return
        if text == "🗑️ Kino O'chirish":
            delete_movie_command(message)
            return
        if text == "📊 Statistika":
            stats_command(message)
            return
        if text == "👥 Foydalanuvchilar":
            counts = get_users_count()
            bot.send_message(
                user_id,
                f"👥 <b>FOYDALANUVCHILAR</b>\n\n"
                f"Jami: <b>{counts.get('total', 0)}</b>\n"
                f"Oddiy: <b>{counts.get('user', 0)}</b>\n"
                f"Premium: <b>{counts.get('premium', 0)}</b>"
            )
            return
        if text == "📢 Broadcast":
            broadcast_command(message)
            return
        if text == "💎 Status Berish":
            set_status_command(message)
            return
        if text == "📡 Kanal Sozlash":
            show_channels_menu(user_id)
            return

    # Kino kodi qidirish (raqam bo'lsa)
    if text.isdigit() or text.replace(' ', '').isdigit():
        movie = get_movie(text.strip())
        if movie:
            send_movie(user_id, movie, user_status)
        else:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("🔍 Qidirish", callback_data="start_search"))
            bot.send_message(
                user_id,
                f"❌ <b>{text}</b> kodli kino topilmadi!\n\n"
                f"💡 <b>Maslahat:</b>\n"
                f"• Kodni to'g'ri kiritganingizni tekshiring\n"
                f"• Kino hali qo'shilmagan bo'lishi mumkin\n"
                f"• Nomini yozib qidiring",
                reply_markup=keyboard
            )
        return

    # Matn bo'lsa qidirish
    results = search_movies(text)
    if results and len(text) > 2:
        do_search(user_id, text)
    else:
        bot.send_message(
            user_id,
            f"❓ <b>Kino kodi kiriting!</b>\n\n"
            f"Kino kodini yozing (masalan: <code>101</code>)\n"
            f"Yoki kino nomini yozib qidiring."
        )

# ╔══════════════════════════════════════════════════════════════╗
# ║              📁 FAYL HANDLERLARI (VIDEO, HUJJAT)             ║
# ╚══════════════════════════════════════════════════════════════╝

@bot.message_handler(content_types=['video', 'document', 'photo'])
def file_handler(message):
    """Video va fayllarni qabul qilish (admin uchun)"""
    user_id = message.from_user.id

    if not is_admin(user_id):
        bot.send_message(user_id, "❌ Faqat adminlar fayl yuborishi mumkin.")
        return

    state = get_state(user_id)
    if state.get('state') == 'add_movie_file':
        data = state.get('data', {})

        if message.content_type == 'video':
            file_id = message.video.file_id
            file_type = 'video'
        elif message.content_type == 'document':
            file_id = message.document.file_id
            file_type = 'document'
        elif message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        else:
            bot.send_message(user_id, "❌ Noto'g'ri fayl turi!")
            return

        success = add_movie(
            code=data['code'],
            title=data['title'],
            description=data.get('description', ''),
            file_id=file_id,
            file_type=file_type,
            category=data.get('category', 'Umumiy'),
            is_vip=data.get('is_vip', 0),
            is_premium=data.get('is_premium', 0),
            added_by=user_id
        )

        clear_state(user_id)

        if success:
            bot.send_message(
                user_id,
                f"✅ <b>Kino muvaffaqiyatli qo'shildi!</b>\n\n"
                f"🔢 Kod: <code>{data['code']}</code>\n"
                f"🎬 Nom: <b>{data['title']}</b>\n"
                f"📂 Kategoriya: {data.get('category', 'Umumiy')}\n"
                f"💎 Premium: {'Ha' if data.get('is_premium') else 'Yoq'}"
            )
        else:
            bot.send_message(user_id, f"❌ Xatolik! <code>{data['code']}</code> kodli kino allaqachon mavjud.")

# ╔══════════════════════════════════════════════════════════════╗
# ║              📲 CALLBACK QUERY HANDLERLARI                   ║
# ╚══════════════════════════════════════════════════════════════╝

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Inline tugmalar callback"""
    user_id = call.from_user.id
    data = call.data

    try:
        # Obuna tekshirish
        if data == "check_subscription":
            is_subscribed, not_subscribed = check_subscription(user_id)
            if is_subscribed:
                bot.answer_callback_query(call.id, "✅ Ajoyib! Siz barcha kanallarga obuna bo'lgansiz!")
                bot.delete_message(call.message.chat.id, call.message.message_id)
                # Start xabarini yuborish
                fake_message = call.message
                fake_message.from_user = call.from_user
                fake_message.text = '/start'
                start_handler(fake_message)
            else:
                bot.answer_callback_query(call.id, "❌ Siz hali barcha kanallarga obuna bo'lmagansiz!")
                keyboard = get_subscription_keyboard(not_subscribed)
                bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=keyboard
                )
            return

        # Kino olish (inline)
        if data.startswith("get_movie_"):
            code = data.replace("get_movie_", "")
            movie = get_movie(code)
            user = get_user(user_id)
            user_status = user.get('status', 'user') if user else 'user'
            if movie:
                send_movie(user_id, movie, user_status)
                bot.answer_callback_query(call.id)
            else:
                bot.answer_callback_query(call.id, "❌ Kino topilmadi!")
            return

        # Kategoriya kinolar
        if data.startswith("category_"):
            category = data.replace("category_", "")
            movies = get_movies_by_category(category)
            if not movies:
                bot.answer_callback_query(call.id, f"❌ '{category}' kategoriyasida kino yo'q!")
                return

            text_msg = f"📂 <b>{category}</b> kategoriyasi\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            keyboard = InlineKeyboardMarkup(row_width=1)
            for code, title, views in movies:
                text_msg += f"🎬 <b>{title}</b>\n   👁️ {views} | 🔢 <code>{code}</code>\n\n"
                keyboard.add(InlineKeyboardButton(f"▶️ {title[:30]}", callback_data=f"get_movie_{code}"))

            bot.answer_callback_query(call.id)
            bot.send_message(user_id, text_msg, reply_markup=keyboard)
            return

        # Admin kategoriya tanlash
        if data.startswith("admin_cat_") and is_admin(user_id):
            category = data.replace("admin_cat_", "")
            state = get_state(user_id)
            if state.get('state') == 'add_movie_category':
                movie_data = state.get('data', {})
                movie_data['category'] = category
                set_state(user_id, 'add_movie_vip', movie_data)
                bot.answer_callback_query(call.id, f"✅ Kategoriya: {category}")
                bot.send_message(user_id, f"✅ Kategoriya: <b>{category}</b>\n\n5️⃣ Premium kinomi? (ha/yo'q):")
            return

        # Reyting berish
        if data.startswith("rate_"):
            parts = data.split("_")
            movie_code = parts[1]
            rating = int(parts[2])

            result = rate_movie(user_id, movie_code, rating)
            stars = "⭐" * rating

            if result == "added":
                bot.answer_callback_query(call.id, f"✅ Baholadingiz: {stars}")
            else:
                bot.answer_callback_query(call.id, f"✅ Bahoyingiz yangilandi: {stars}")
            return

        # Admin status berish - status tanlash bosqichi
        if data.startswith("setstatus_") and is_admin(user_id):
            parts = data.split("_")
            target_id = int(parts[1])
            new_status = parts[2]
            status_names = {'user': 'Standard', 'premium': 'Premium', 'admin': 'Admin'}

            # Premium tanlangan bo'lsa - muddatni so'raymiz
            if new_status == 'premium':
                kb = InlineKeyboardMarkup(row_width=3)
                kb.add(
                    InlineKeyboardButton("7 kun", callback_data=f"setdays_{target_id}_7"),
                    InlineKeyboardButton("14 kun", callback_data=f"setdays_{target_id}_14"),
                    InlineKeyboardButton("30 kun", callback_data=f"setdays_{target_id}_30"),
                )
                kb.add(
                    InlineKeyboardButton("60 kun", callback_data=f"setdays_{target_id}_60"),
                    InlineKeyboardButton("90 kun", callback_data=f"setdays_{target_id}_90"),
                    InlineKeyboardButton("180 kun", callback_data=f"setdays_{target_id}_180"),
                )
                kb.add(
                    InlineKeyboardButton("365 kun", callback_data=f"setdays_{target_id}_365"),
                    InlineKeyboardButton("♾️ Cheksiz", callback_data=f"setdays_{target_id}_0"),
                )
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"💎 <b>Premium muddati</b>\n\n"
                    f"👤 Foydalanuvchi: <code>{target_id}</code>\n\n"
                    f"Necha kunga Premium berilsin?",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=kb
                )
                return

            # Standard yoki Admin - to'g'ridan-to'g'ri o'rnatish
            if update_user_status(target_id, new_status, days=0):
                bot.answer_callback_query(call.id, f"✅ Status berildi: {status_names[new_status]}")
                bot.edit_message_text(
                    f"✅ Foydalanuvchi <code>{target_id}</code> ga <b>{status_names[new_status]}</b> statusi berildi!",
                    call.message.chat.id,
                    call.message.message_id
                )
                clear_state(user_id)
                try:
                    bot.send_message(
                        target_id,
                        f"🎉 <b>Tabriklaymiz!</b>\n\n"
                        f"Sizga <b>{status_names[new_status]}</b> statusi berildi!"
                    )
                except Exception:
                    pass
            else:
                bot.answer_callback_query(call.id, "❌ Foydalanuvchi topilmadi!")
            return

        # Premium muddatini tanlash
        if data.startswith("setdays_") and is_admin(user_id):
            parts = data.split("_")
            target_id = int(parts[1])
            days = int(parts[2])

            if update_user_status(target_id, 'premium', days=days):
                if days > 0:
                    expires = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
                    duration_text = f"{days} kun (tugaydi: {expires})"
                else:
                    duration_text = "Cheksiz ♾️"

                bot.answer_callback_query(call.id, "✅ Premium berildi!")
                bot.edit_message_text(
                    f"✅ <b>Premium status berildi!</b>\n\n"
                    f"👤 Foydalanuvchi: <code>{target_id}</code>\n"
                    f"💎 Status: <b>Premium</b>\n"
                    f"⏰ Muddati: <b>{duration_text}</b>",
                    call.message.chat.id,
                    call.message.message_id
                )
                clear_state(user_id)
                try:
                    bot.send_message(
                        target_id,
                        f"🎉 <b>Tabriklaymiz!</b>\n\n"
                        f"Sizga <b>💎 Premium</b> status berildi!\n"
                        f"⏰ Muddati: <b>{duration_text}</b>\n\n"
                        f"Endi barcha Premium kinolardan bemalol foydalanishingiz mumkin! 🚀"
                    )
                except Exception:
                    pass
            else:
                bot.answer_callback_query(call.id, "❌ Foydalanuvchi topilmadi!")
            return

        # Kunlik bonus
        if data == "daily_bonus":
            success, points, info = claim_daily_bonus(user_id)
            if success:
                bot.answer_callback_query(call.id, f"🎁 +{info} ball!")
                bot.send_message(
                    user_id,
                    f"🎁 <b>Kunlik Bonus!</b>\n\n✅ +{info} ball oldingiz!\n💰 Jami: <b>{points}</b>"
                )
            else:
                bot.answer_callback_query(call.id, f"⏰ {info}dan so'ng qaytib keling!")
            return

        # Referal ma'lumot
        if data == "referral_info":
            referral_command(call.message)
            bot.answer_callback_query(call.id)
            return

        # Yangi kanal qo'shish boshlash
        if data == "chadd_start" and is_admin(user_id):
            set_state(user_id, 'add_channel_id')
            bot.answer_callback_query(call.id)
            bot.send_message(
                user_id,
                "➕ <b>Yangi Majburiy Kanal Qo'shish</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1️⃣ Avvalo kanal ID sini kiriting:\n\n"
                "📌 Misollar:\n"
                "  • <code>@kanal_username</code>\n"
                "  • <code>-1001234567890</code> (yopiq kanal uchun)\n\n"
                "⚠️ Botni avval shu kanalga <b>admin</b> qilib qo'shing!"
            )
            return

        # Kanalni o'chirish
        if data.startswith("chremove_") and is_admin(user_id):
            ch_id = data.replace("chremove_", "", 1)
            if remove_channel(ch_id):
                bot.answer_callback_query(call.id, f"✅ Kanal o'chirildi: {ch_id}")
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    pass
                show_channels_menu(user_id)
            else:
                bot.answer_callback_query(call.id, "❌ Kanal topilmadi!")
            return

        # Qidiruv boshlash
        if data == "start_search":
            set_state(user_id, 'searching')
            bot.answer_callback_query(call.id)
            bot.send_message(user_id, "🔍 Qidirmoqchi bo'lgan kino nomini yozing:")
            return

    except Exception as e:
        logger.error(f"❌ Callback xatosi: {e}")
        bot.answer_callback_query(call.id, "❌ Xatolik yuz berdi!")

# ╔══════════════════════════════════════════════════════════════╗
# ║              📢 BROADCAST FUNKSIYASI                         ║
# ╚══════════════════════════════════════════════════════════════╝

def do_broadcast(admin_id: int, message_text: str):
    """Barcha foydalanuvchilarga xabar yuborish"""
    users = get_all_users()
    total = len(users)
    success = 0
    failed = 0

    bot.send_message(
        admin_id,
        f"📢 <b>Broadcast boshlandi...</b>\n"
        f"👥 Jami foydalanuvchilar: <b>{total}</b>"
    )

    for user_id in users:
        try:
            bot.send_message(user_id, f"📢 <b>E'lon</b>\n\n{message_text}")
            success += 1
            time.sleep(0.05)  # Telegram limit
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast xatosi {user_id}: {e}")

    bot.send_message(
        admin_id,
        f"✅ <b>Broadcast yakunlandi!</b>\n\n"
        f"✅ Muvaffaqiyatli: <b>{success}</b>\n"
        f"❌ Xatolik: <b>{failed}</b>\n"
        f"📊 Jami: <b>{total}</b>"
    )
    logger.info(f"📢 Broadcast: {success}/{total} muvaffaqiyatli")

# ╔══════════════════════════════════════════════════════════════╗
# ║                    🚀 ASOSIY FUNKSIYA                        ║
# ╚══════════════════════════════════════════════════════════════╝

def main():
    """Botni ishga tushirish"""
    global BOT_USERNAME
    logger.info("🚀 KODLI KINO BOT ishga tushmoqda...")

    # Bot tokenini tekshirish
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.critical("❌ BOT_TOKEN o'rnatilmagan! bot.py faylida BOT_TOKEN o'zgartiring.")
        return

    if not ADMIN_IDS or ADMIN_IDS == [0]:
        logger.warning("⚠️ ADMIN_IDS o'rnatilmagan! bot.py faylida ADMIN_IDS ga o'z ID ingizni qo'shing.")

    # Ma'lumotlar bazasini yaratish
    create_database()

    # Bot username ni avtomatik olish
    try:
        me = bot.get_me()
        BOT_USERNAME = me.username or BOT_USERNAME
        logger.info(f"🤖 Bot ulandi: @{BOT_USERNAME} ({me.first_name})")
    except Exception as e:
        logger.error(f"❌ Bot ma'lumotlarini olishda xato: {e}")
        logger.critical("❌ BOT_TOKEN noto'g'ri yoki internet aloqasi yo'q. Tekshiring va qayta urinib ko'ring.")
        return

    logger.info("✅ Bot muvaffaqiyatli ishga tushdi!")
    logger.info(f"👑 Admin ID lari: {ADMIN_IDS}")
    channels = get_channels()
    if channels:
        logger.info(f"📢 Majburiy kanallar: {[ch['id'] for ch in channels]}")
    else:
        logger.info("📢 Majburiy kanallar: hech qanday kanal yo'q (admin qo'shishi kerak)")

    # Botni cheksiz ishlashga ishga tushirish
    while True:
        try:
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=30,
                logger_level=logging.INFO,
                allowed_updates=None,
                restart_on_change=False,
                skip_pending=True
            )
        except KeyboardInterrupt:
            logger.info("👋 Bot to'xtatildi (Ctrl+C)")
            break
        except Exception as e:
            logger.error(f"⚠️ Bot xatosi: {e}. 5 soniyadan keyin qayta urinib ko'rilmoqda...")
            time.sleep(5)

if __name__ == '__main__':
    main()
