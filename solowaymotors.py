from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime
import os
import requests
import re
from bs4 import BeautifulSoup

TOKEN = "8402346986:AAGp4Xgnm8i_VF9AuTLgCflcKOZ1jrfTksE"

# Путь для постоянного хранения
DB_PATH = "/data/motors.db"

# Создаём папку /data если её нет
os.makedirs("/data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            title TEXT,
            price TEXT,
            year TEXT,
            mileage TEXT,
            engine TEXT,
            horsepower TEXT,
            transmission TEXT,
            location TEXT,
            photo_url TEXT,
            folder TEXT,
            date_added TEXT
        )
    """)
    try:
        c.execute("ALTER TABLE cars ADD COLUMN horsepower TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE cars ADD COLUMN photo_url TEXT")
    except:
        pass
    conn.commit()
    conn.close()

init_db()

ALLOWED_USERS = {
    "Соловей": "2011",
}

def try_parse_avito(url):
    """
    Пытается достать данные из Авито
    Возвращает словарь с данными или None
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()
        
        # ===== НАЗВАНИЕ =====
        title = None
        
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            og_content = og_title['content'].strip()
            if 'Авито' not in og_content or 'Объявления' not in og_content:
                title = og_content
        
        if not title:
            parts = url.split('/')
            if len(parts) > 5:
                car_part = parts[-1].split('?')[0]
                car_part = car_part.replace('_', ' ').title()
                car_part = re.sub(r'\s+\d{10,}\s*$', '', car_part)
                title = car_part
        
        if not title:
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text()
                title_text = re.sub(r'\s*купить.*на Avito.*', '', title_text)
                title_text = title_text.strip()
                if title_text and 'Авито' not in title_text:
                    title = title_text
        
        # ===== ЦЕНА =====
        price = None
        price_meta = soup.find('meta', itemprop='price')
        if price_meta and price_meta.get('content'):
            price = f"₽{int(float(price_meta['content'])):,}".replace(',', ' ')
        else:
            price_match = re.search(r'(\d{1,3}(?:\s*\d{3})*)\s*(?:₽|руб)', text)
            if price_match:
                price = f"₽{price_match.group(1)}"
        
        # ===== ГОД =====
        year = None
        year_match = re.search(r'(\d{4})\s*год', text)
        if year_match:
            year = year_match.group(1)
        
        # ===== ПРОБЕГ =====
        mileage = None
        mileage_match = re.search(r'(\d{1,3}(?:\s*\d{3})*)\s*км', text)
        if mileage_match:
            mileage = f"{mileage_match.group(1)} км"
        
        # ===== ДВИГАТЕЛЬ =====
        engine = None
        engine_match = re.search(r'(\d+\.\d+)\s*л', text)
        if engine_match:
            engine = f"{engine_match.group(1)} л"
        
        # ===== ЛОШАДИНЫЕ СИЛЫ =====
        horsepower = None
        hp_match = re.search(r'(\d{2,4})\s*(?:л\.?с\.?|лошадиных сил|лошадок|лошади)', text)
        if hp_match:
            horsepower = f"{hp_match.group(1)} л.с."
        
        # ===== КОРОБКА =====
        transmission = None
        if 'AT' in url or 'автомат' in text.lower():
            transmission = 'AT'
        elif 'MT' in url or 'механика' in text.lower():
            transmission = 'MT'
        elif 'AMT' in url or 'робот' in text.lower():
            transmission = 'AMT'
        
        # ===== ЛОКАЦИЯ =====
        location = None
        location_match = re.search(r'avito\.ru/([^/]+)/', url)
        if location_match:
            cities = {
                'moskva': 'Москва',
                'sankt-peterburg': 'Санкт-Петербург',
                'vladivostok': 'Владивосток',
                'lyubertsy': 'Люберцы',
            }
            loc = location_match.group(1)
            location = cities.get(loc, loc.replace('-', ' ').title())
        
        # ===== ФОТО =====
        photo_url = None
        
        for img in soup.find_all('img'):
            for attr in ['src', 'data-src', 'data-srcset', 'data-url', 'data-image']:
                src = img.get(attr, '')
                if src and 'http' in src and len(src) > 50:
                    if 'logo' not in src.lower() and 'avatar' not in src.lower() and 'favicon' not in src.lower():
                        photo_url = src
                        break
            if photo_url:
                break
        
        if not photo_url:
            for div in soup.find_all('div'):
                style = div.get('style', '')
                bg_match = re.search(r'url\([\'"]?([^\'"]+)[\'"]?\)', style)
                if bg_match:
                    src = bg_match.group(1)
                    if 'http' in src and len(src) > 50:
                        if 'logo' not in src.lower():
                            photo_url = src
                            break
        
        if not photo_url:
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                og_img = og_image['content']
                if 'logo' not in og_img.lower() and 'avatar' not in og_img.lower():
                    photo_url = og_img
        
        if not photo_url:
            for img in soup.find_all('img'):
                src = img.get('src', '') or img.get('data-src', '')
                if src and ('image' in src.lower() or 'photo' in src.lower() or 'upload' in src.lower()):
                    if 'http' in src and len(src) > 50:
                        photo_url = src
                        break
        
        if title:
            return {
                'title': title,
                'price': price or '',
                'year': year or '',
                'mileage': mileage or '',
                'engine': engine or '',
                'horsepower': horsepower or '',
                'transmission': transmission or '',
                'location': location or '',
                'photo_url': photo_url or ''
            }
        
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
    
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "authenticated" not in context.user_data:
        await update.message.reply_text("🔐 Привет! Введи свой ник:")
        context.user_data["awaiting_username"] = True
        return
    
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇩🇪 Немцы", callback_data="folder_Немцы")],
        [InlineKeyboardButton("🇯🇵 Японцы", callback_data="folder_Японцы")],
        [InlineKeyboardButton("🇺🇸 Американцы", callback_data="folder_Американцы")],
        [InlineKeyboardButton("🇬🇧 Англичане", callback_data="folder_Англичане")],
        [InlineKeyboardButton("🇮🇹 Итальянцы", callback_data="folder_Итальянцы")],
        [InlineKeyboardButton("🏎 Спорткары", callback_data="folder_Спорткары")],
        [InlineKeyboardButton("🗑 Сброс базы", callback_data="reset_db")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            "🏎 SOLOWAY MOTORS\n\n👇 Выбери категорию или кинь ссылку на Авито:",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            "🏎 SOLOWAY MOTORS\n\n👇 Выбери категорию или кинь ссылку на Авито:",
            reply_markup=reply_markup
        )

async def show_car(update: Update, context: ContextTypes.DEFAULT_TYPE, folder, index=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, url, title, price, year, mileage, engine, horsepower, transmission, location, photo_url FROM cars WHERE folder = ? ORDER BY id", (folder,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        keyboard = [[InlineKeyboardButton("➕ Добавить", callback_data=f"add_{folder}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            f"📂 {folder}\n\nПока пусто.",
            reply_markup=reply_markup
        )
        return

    if index < 0:
        index = 0
    if index >= len(rows):
        index = len(rows) - 1

    car_id, url, title, price, year, mileage, engine, horsepower, transmission, location, photo_url = rows[index]
    context.user_data[f"car_{folder}"] = index

    caption = f"🚗 <a href='{url}'>{title}</a>\n"
    caption += f"━━━━━━━━━━━━━━━\n"
    if price:
        caption += f"💰 {price}\n"
    if year:
        caption += f"📅 {year} год\n"
    if mileage:
        caption += f"🛣 {mileage}\n"
    if engine:
        caption += f"⚙️ {engine}\n"
    if horsepower:
        caption += f"🐎 {horsepower}\n"
    if transmission:
        caption += f"🕹 {transmission}\n"
    if location:
        caption += f"📍 {location}\n"

    # Индикатор фото
    photo_btn_text = "📸 Фото ✅" if photo_url else "📸 Нет фото ❌"
    photo_btn_callback = f"photo_{car_id}" if photo_url else "noop"

    keyboard = [
        [InlineKeyboardButton("🔗 Открыть на Авито", url=url)],
        [
            InlineKeyboardButton("◀️", callback_data=f"car_{folder}_prev"),
            InlineKeyboardButton(f"{index + 1}/{len(rows)}", callback_data="noop"),
            InlineKeyboardButton("▶️", callback_data=f"car_{folder}_next")
        ],
        [
            InlineKeyboardButton("➕ Добавить", callback_data=f"add_{folder}"),
            InlineKeyboardButton(photo_btn_text, callback_data=photo_btn_callback),
            InlineKeyboardButton("🗑 Переместить", callback_data=f"move_{car_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        caption,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def car_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    parts = data.split("_")
    folder = parts[1]
    direction = parts[2]
    current = context.user_data.get(f"car_{folder}", 0)
    new_index = current + 1 if direction == "next" else current - 1
    await show_car(update, context, folder, new_index)

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    folder = query.data.split("_")[1]
    context.user_data["add_folder"] = folder
    context.user_data["awaiting_url"] = True
    
    await query.message.reply_text(
        "🔗 Отправь ссылку на авто с Авито\n\n"
        "🤖 Я автоматически вытащу все характеристики!",
        parse_mode="Markdown"
    )
    await query.message.delete()

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_username") or context.user_data.get("awaiting_password"):
        await handle_auth(update, context)
        return
    
    if "authenticated" not in context.user_data:
        await update.message.reply_text("🔐 Сначала авторизуйся: /start")
        return
    
    if context.user_data.get("awaiting_url"):
        await handle_url(update, context)

async def handle_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_username"):
        username = update.message.text.strip()
        if username in ALLOWED_USERS:
            context.user_data["temp_username"] = username
            context.user_data["awaiting_username"] = False
            context.user_data["awaiting_password"] = True
            await update.message.reply_text("🔑 Введи пароль:")
        else:
            await update.message.reply_text("❌ Неверный ник. Попробуй ещё раз:")
        return

    if context.user_data.get("awaiting_password"):
        password = update.message.text.strip()
        username = context.user_data.get("temp_username")
        if ALLOWED_USERS.get(username) == password:
            context.user_data["authenticated"] = True
            context.user_data.pop("temp_username", None)
            context.user_data.pop("awaiting_password", None)
            await update.message.reply_text("✅ Доступ разрешён!")
            await show_main_menu(update, context)
        else:
            context.user_data.pop("temp_username", None)
            context.user_data.pop("awaiting_password", None)
            context.user_data.pop("awaiting_username", None)
            await update.message.reply_text("❌ Неверный пароль. Начни заново с /start")
        return

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    folder = context.user_data["add_folder"]
    
    await update.message.reply_text("🔍 Парсю Авито...")
    parsed = try_parse_avito(url)
    
    if parsed:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO cars (url, title, price, year, mileage, engine, horsepower, transmission, location, photo_url, folder, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (url, parsed['title'], parsed['price'], parsed['year'], parsed['mileage'],
              parsed['engine'], parsed['horsepower'], parsed['transmission'], parsed['location'],
              parsed['photo_url'], folder, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        msg = f"✅ Найдено:\n"
        msg += f"🚗 {parsed['title']}\n"
        if parsed['price']:
            msg += f"💰 {parsed['price']}\n"
        if parsed['year']:
            msg += f"📅 {parsed['year']} год\n"
        if parsed['mileage']:
            msg += f"🛣 {parsed['mileage']}\n"
        if parsed['engine']:
            msg += f"⚙️ {parsed['engine']}\n"
        if parsed['horsepower']:
            msg += f"🐎 {parsed['horsepower']}\n"
        if parsed['transmission']:
            msg += f"🕹 {parsed['transmission']}\n"
        if parsed['location']:
            msg += f"📍 {parsed['location']}\n"
        msg += "\n✅ Добавлено в гараж!"
        
        if parsed['photo_url']:
            try:
                img_response = requests.get(parsed['photo_url'], headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://www.avito.ru/'
                }, timeout=10)
                if img_response.status_code == 200:
                    await update.message.reply_photo(photo=img_response.content, caption=msg)
                    context.user_data["awaiting_url"] = False
                    await show_main_menu(update, context)
                    return
            except:
                pass
        
        await update.message.reply_text(msg)
        context.user_data["awaiting_url"] = False
        await show_main_menu(update, context)
    else:
        await update.message.reply_text("❌ Не удалось распарсить. Проверь ссылку.")

async def ask_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    car_id = int(query.data.split("_")[1])
    context.user_data["move_id"] = car_id
    keyboard = [
        [InlineKeyboardButton("🇩🇪 Немцы", callback_data="move_to_Немцы")],
        [InlineKeyboardButton("🇯🇵 Японцы", callback_data="move_to_Японцы")],
        [InlineKeyboardButton("🇺🇸 Американцы", callback_data="move_to_Американцы")],
        [InlineKeyboardButton("🇬🇧 Англичане", callback_data="move_to_Англичане")],
        [InlineKeyboardButton("🇮🇹 Итальянцы", callback_data="move_to_Итальянцы")],
        [InlineKeyboardButton("🏎 Спорткары", callback_data="move_to_Спорткары")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🗂 Выбери категорию:", reply_markup=reply_markup)

async def move_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "move_id" not in context.user_data:
        return
    car_id = context.user_data.pop("move_id")
    new_folder = query.data.split("_")[2]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE cars SET folder = ? WHERE id = ?", (new_folder, car_id))
    conn.commit()
    conn.close()
    await query.edit_message_text(f"✅ Перемещено в «{new_folder}».")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if "authenticated" not in context.user_data:
        await query.edit_message_text("🔐 Сначала авторизуйся: /start")
        return

    if data == "noop":
        return
    elif data == "reset_db":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM cars")
        conn.commit()
        conn.close()
        await query.edit_message_text("🗑 База очищена! Начни заново.")
    elif data.startswith("photo_"):
        car_id = int(data.split("_")[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT photo_url, title FROM cars WHERE id = ?", (car_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            try:
                img_response = requests.get(row[0], headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://www.avito.ru/'
                }, timeout=10)
                if img_response.status_code == 200:
                    await update.effective_chat.send_photo(
                        photo=img_response.content,
                        caption=f"📸 {row[1]}"
                    )
                else:
                    await query.answer("❌ Не удалось загрузить фото", show_alert=True)
            except Exception as e:
                await query.answer("❌ Ошибка загрузки фото", show_alert=True)
        else:
            await query.answer("❌ Фото не найдено", show_alert=True)
    elif data.startswith("folder_"):
        folder = data.split("_", 1)[1]
        await show_car(update, context, folder, 0)
    elif data.startswith("car_"):
        await car_nav(update, context)
    elif data.startswith("add_"):
        await start_add(update, context)
    elif data.startswith("move_"):
        await ask_move(update, context)
    elif data.startswith("move_to_"):
        await move_to(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    print("🏎 Soloway Motors запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()