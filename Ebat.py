import functools
import telebot
import sqlite3
import time
import random
import threading

TOKEN = 'ТВОЙ_ТОКЕН'
ADMIN_IDS = [6115517123, 2046462689, 7787565361]       # Telegram ID админов
ALLOWED_GROUP_ID = -1003880025896  # ID вашей группы (отрицательное число)

bot = telebot.TeleBot(TOKEN)

# ==============================================================
# --- ФИЛЬТР ГРУППЫ ---
# ==============================================================
def group_only(func):
    @functools.wraps(func)  # сохраняет оригинальное имя функции
    def wrapper(message):
        if message.chat.id != ALLOWED_GROUP_ID:
            return
        func(message)
    return wrapper

# ==============================================================
# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
# ==============================================================
def init_db():
    conn = sqlite3.connect('aurelia_economy.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            balance INTEGER DEFAULT 1000,
            level INTEGER DEFAULT 1,
            last_cash REAL DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS business_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            display_name TEXT,
            cost INTEGER,
            income_per_hour INTEGER,
            description TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            business_name TEXT,
            quantity INTEGER DEFAULT 1,
            UNIQUE(user_id, business_name)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_assets (
            name TEXT PRIMARY KEY,
            display_name TEXT,
            price REAL,
            base_price REAL,
            last_updated REAL DEFAULT 0,
            emoji TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_portfolio (
            user_id INTEGER,
            asset_name TEXT,
            quantity INTEGER DEFAULT 0,
            avg_buy_price REAL DEFAULT 0,
            PRIMARY KEY (user_id, asset_name)
        )
    ''')

    conn.commit()

    businesses = [
        ('farm',      '🌾 Ферма',           2000,   40,  'Небольшой, но надёжный источник дохода'),
        ('factory',   '🏭 Завод',            5000,  120,  'Производит товары, стабильный доход'),
        ('mine',      '⛏️ Шахта',            8000,  220,  'Добывает ресурсы Аурелии, высокая доходность'),
        ('casino',    '🎰 Казино',          15000,  450,  'Огромный доход, требует больших вложений'),
        ('bank_biz',  '🏦 Частный банк',    30000,  950,  'Элитный бизнес с максимальным пассивным доходом'),
    ]
    cursor.executemany(
        'INSERT OR IGNORE INTO business_types (name, display_name, cost, income_per_hour, description) VALUES (?,?,?,?,?)',
        businesses
    )

    assets = [
        ('oil',    '🛢️ Нефть',   100.0, 100.0, '🛢️'),
        ('gold',   '🥇 Золото',  500.0, 500.0, '🥇'),
        ('steel',  '⚙️ Сталь',   80.0,  80.0,  '⚙️'),
        ('aur',    '💎 Аурит',   300.0, 300.0, '💎'),
    ]
    cursor.executemany(
        'INSERT OR IGNORE INTO market_assets (name, display_name, price, base_price, emoji) VALUES (?,?,?,?,?)',
        assets
    )

    conn.commit()
    conn.close()

init_db()

# ==============================================================
# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
# ==============================================================
def db_query(query, args=(), fetchone=False):
    conn = sqlite3.connect('aurelia_economy.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, args)
    if query.strip().upper().startswith("SELECT"):
        result = cursor.fetchone() if fetchone else cursor.fetchall()
    else:
        conn.commit()
        result = None
    conn.close()
    return result

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_price_arrow(price, base_price):
    if price > base_price * 1.1:
        return "📈"
    elif price < base_price * 0.9:
        return "📉"
    return "➡️"

# ==============================================================
# --- ФОНОВЫЕ ПОТОКИ ---
# ==============================================================
def market_price_updater():
    """Каждый час случайно изменяет цены на бирже."""
    while True:
        time.sleep(3600)
        assets = db_query("SELECT name, price, base_price FROM market_assets")
        for name, price, base_price in assets:
            change = random.uniform(-0.25, 0.25)
            new_price = price * (1 + change)
            new_price = max(base_price * 0.5, min(base_price * 2.0, new_price))
            new_price = round(new_price, 2)
            db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
                     (new_price, time.time(), name))

def passive_income_distributor():
    """Каждые 10 минут начисляет пассивный доход от бизнесов."""
    INTERVAL = 600
    while True:
        time.sleep(INTERVAL)
        owners = db_query('''
            SELECT ub.user_id, ub.quantity, bt.income_per_hour
            FROM user_businesses ub
            JOIN business_types bt ON ub.business_name = bt.name
        ''')
        income_map = {}
        for user_id, qty, iph in owners:
            income = int(iph * qty * (INTERVAL / 3600))
            income_map[user_id] = income_map.get(user_id, 0) + income
        for user_id, income in income_map.items():
            if income > 0:
                db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (income, user_id))

threading.Thread(target=market_price_updater, daemon=True).start()
threading.Thread(target=passive_income_distributor, daemon=True).start()

# ==============================================================
# --- ОСНОВНЫЕ КОМАНДЫ ---
# ==============================================================

@bot.message_handler(commands=['start'])
@group_only
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"player_{user_id}"

    user = db_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        db_query("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        bot.reply_to(message,
            "🌍 Добро пожаловать в экономику мира Aurelia!\n\n"
            "💰 Стартовый капитал: 1000\n\n"
            "📋 Основные команды:\n"
            "/profile - профиль\n"
            "/cash - сбор налогов\n"
            "/upgrade - улучшить экономику\n"
            "/pay @юзернейм сумма - перевод\n\n"
            "🏢 Бизнес:\n"
            "/shop - магазин бизнесов\n"
            "/mybiz - мои бизнесы\n\n"
            "📈 Биржа Аурелии:\n"
            "/market - текущие цены\n"
            "/buy - купить актив\n"
            "/sell - продать актив\n"
            "/portfolio - мой портфель"
        )
    else:
        # Обновляем username если изменился
        db_query("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        bot.reply_to(message, "Вы уже зарегистрированы! Используйте /profile.")

@bot.message_handler(commands=['profile'])
@group_only
def profile_command(message):
    user_id = message.from_user.id
    # Обновляем username при каждом обращении
    username = message.from_user.username or f"player_{user_id}"
    db_query("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))

    user = db_query("SELECT balance, level FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Вы не зарегистрированы! Введите /start.")

    biz_data = db_query('''
        SELECT ub.quantity, bt.income_per_hour FROM user_businesses ub
        JOIN business_types bt ON ub.business_name = bt.name
        WHERE ub.user_id = ?
    ''', (user_id,))
    passive = sum(q * iph for q, iph in biz_data) if biz_data else 0

    bot.reply_to(message,
        f"👤 **Профиль @{username}:**\n\n"
        f"💰 Баланс: {user[0]}\n"
        f"📈 Уровень: {user[1]}\n"
        f"🏭 Пассивный доход: ~{passive} 💰/час\n\n"
        f"Используйте /cash для сбора налогов.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['cash'])
@group_only
def cash_command(message):
    user_id = message.from_user.id
    user = db_query("SELECT balance, level, last_cash FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Сначала введите /start")

    balance, level, last_cash = user
    current_time = time.time()
    cooldown = 1800

    if current_time - last_cash < cooldown:
        left_time = int(cooldown - (current_time - last_cash))
        bot.reply_to(message, f"⏳ Казна пуста. Следующий сбор через {left_time // 60} мин. {left_time % 60} сек.")
        return

    base_income = 500
    level_multiplier = 1 + (level * 0.2)
    market_luck = random.uniform(0.8, 1.2)
    earned = int(base_income * level_multiplier * market_luck)
    new_balance = balance + earned

    db_query("UPDATE users SET balance = ?, last_cash = ? WHERE user_id = ?", (new_balance, current_time, user_id))

    if market_luck > 1.1:
        event = "📈 В Аурелии экономический бум!"
    elif market_luck < 0.9:
        event = "📉 На рынках Аурелии кризис, налоги собраны с трудом."
    else:
        event = "⚖️ Экономика Аурелии стабильна."

    bot.reply_to(message,
        f"{event}\n"
        f"💵 Вы собрали налоги: **{earned}** 💰\n"
        f"Баланс: {new_balance} 💰",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['upgrade'])
@group_only
def upgrade_command(message):
    user = db_query("SELECT balance, level FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Введите /start")
    balance, level = user
    upgrade_cost = level * 1500
    if balance >= upgrade_cost:
        db_query("UPDATE users SET balance = ?, level = ? WHERE user_id = ?",
                 (balance - upgrade_cost, level + 1, message.from_user.id))
        bot.reply_to(message,
            f"✅ Экономика улучшена до {level + 1} уровня за {upgrade_cost} 💰!\n"
            f"/cash теперь приносит больше."
        )
    else:
        bot.reply_to(message,
            f"❌ Недостаточно средств.\n"
            f"Нужно: {upgrade_cost} 💰\n"
            f"Баланс: {balance} 💰"
        )

@bot.message_handler(commands=['pay'])
@group_only
def pay_command(message):
    # Использование: /pay @username 500
    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Использование: /pay @юзернейм [сумма]")

    target_username = args[1].lstrip('@').lower()
    try:
        amount = int(args[2])
    except ValueError:
        return bot.reply_to(message, "Сумма должна быть числом.")
    if amount <= 0:
        return bot.reply_to(message, "Сумма должна быть больше нуля.")

    sender_id = message.from_user.id
    sender_username = (message.from_user.username or "").lower()

    if target_username == sender_username:
        return bot.reply_to(message, "Нельзя переводить самому себе.")

    sender = db_query("SELECT balance FROM users WHERE user_id = ?", (sender_id,), fetchone=True)
    target = db_query("SELECT user_id, username FROM users WHERE LOWER(username) = ?", (target_username,), fetchone=True)

    if not sender:
        return bot.reply_to(message, "Вы не зарегистрированы. Введите /start")
    if not target:
        return bot.reply_to(message, f"❌ Игрок @{target_username} не найден в базе Аурелии.")
    if sender[0] < amount:
        return bot.reply_to(message, f"❌ Недостаточно средств.\nВаш баланс: {sender[0]} 💰")

    target_id = target[0]
    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
    db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))

    bot.reply_to(message, f"💸 Переведено **{amount}** 💰 игроку @{target_username}.", parse_mode="Markdown")

# ==============================================================
# --- БИЗНЕСЫ ---
# ==============================================================

@bot.message_handler(commands=['shop'])
@group_only
def shop_command(message):
    businesses = db_query("SELECT name, display_name, cost, income_per_hour, description FROM business_types")
    text = "🏪 **Магазин бизнесов Аурелии:**\n\n"
    for name, display, cost, iph, desc in businesses:
        text += (
            f"{display}\n"
            f"   💵 Цена: {cost} 💰\n"
            f"   📊 Доход: ~{iph} 💰/час\n"
            f"   📝 {desc}\n"
            f"   Купить: `/buybiz {name}`\n\n"
        )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['buybiz'])
@group_only
def buybiz_command(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Использование: /buybiz [название] [кол-во]\nСписок: /shop")

    biz_name = args[1].lower()
    qty = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 1
    if qty < 1:
        return bot.reply_to(message, "Количество должно быть >= 1.")

    biz = db_query("SELECT display_name, cost, income_per_hour FROM business_types WHERE name = ?",
                   (biz_name,), fetchone=True)
    if not biz:
        return bot.reply_to(message, f"❌ Бизнес '{biz_name}' не найден. Смотри /shop")

    display, cost, iph = biz
    total_cost = cost * qty
    user = db_query("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Введите /start")
    if user[0] < total_cost:
        return bot.reply_to(message, f"❌ Недостаточно средств.\nНужно: {total_cost} 💰\nБаланс: {user[0]} 💰")

    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, message.from_user.id))
    db_query('''
        INSERT INTO user_businesses (user_id, business_name, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, business_name) DO UPDATE SET quantity = quantity + ?
    ''', (message.from_user.id, biz_name, qty, qty))

    bot.reply_to(message,
        f"✅ Куплено **{qty}x {display}** за {total_cost} 💰!\n"
        f"📊 Пассивный доход: ~{iph * qty} 💰/час\n"
        f"💡 Доход начисляется автоматически каждые 10 минут.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['mybiz'])
@group_only
def mybiz_command(message):
    businesses = db_query('''
        SELECT bt.display_name, ub.quantity, bt.income_per_hour
        FROM user_businesses ub
        JOIN business_types bt ON ub.business_name = bt.name
        WHERE ub.user_id = ?
    ''', (message.from_user.id,))

    if not businesses:
        return bot.reply_to(message, "У вас нет бизнесов. Купите их в /shop")

    text = "🏢 **Ваши бизнесы:**\n\n"
    total_iph = 0
    for display, qty, iph in businesses:
        subtotal = iph * qty
        total_iph += subtotal
        text += f"{display} x{qty} - {subtotal} 💰/час\n"

    text += (
        f"\n📊 **Итого: ~{total_iph} 💰/час**\n"
        f"💰 В сутки: ~{total_iph * 24} 💰\n"
        f"\n💡 Доход начисляется каждые 10 минут автоматически."
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ==============================================================
# --- БИРЖА ---
# ==============================================================

@bot.message_handler(commands=['market'])
@group_only
def market_command(message):
    assets = db_query("SELECT name, display_name, price, base_price FROM market_assets")
    text = "📊 **Биржа Аурелии - Текущие цены:**\n\n"
    for name, display, price, base_price in assets:
        arrow = get_price_arrow(price, base_price)
        change_pct = ((price - base_price) / base_price) * 100
        sign = "+" if change_pct >= 0 else ""
        text += (
            f"{arrow} **{display}**\n"
            f"   💵 Цена: {price:.2f} 💰 ({sign}{change_pct:.1f}% от базовой)\n"
            f"   Купить: `/buy {name} [кол-во]`  Продать: `/sell {name} [кол-во]`\n\n"
        )
    text += "⏰ Цены обновляются каждый час.\n/portfolio - ваш портфель"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['buy'])
@group_only
def buy_asset_command(message):
    args = message.text.split()
    if len(args) < 3:
        return bot.reply_to(message, "Использование: /buy [актив] [количество]\nСписок активов: /market")

    asset_name = args[1].lower()
    try:
        qty = int(args[2])
    except ValueError:
        return bot.reply_to(message, "Количество должно быть числом.")
    if qty <= 0:
        return bot.reply_to(message, "Количество должно быть > 0.")

    asset = db_query("SELECT display_name, price FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"❌ Актив '{asset_name}' не найден. Смотри /market")

    display, price = asset
    total_cost = round(price * qty, 2)

    user = db_query("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Введите /start")
    if user[0] < total_cost:
        return bot.reply_to(message, f"❌ Недостаточно средств.\nНужно: {total_cost} 💰\nБаланс: {user[0]} 💰")

    existing = db_query(
        "SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?",
        (message.from_user.id, asset_name), fetchone=True
    )
    if existing:
        old_qty, old_avg = existing
        new_qty = old_qty + qty
        new_avg = ((old_avg * old_qty) + (price * qty)) / new_qty
        db_query("UPDATE user_portfolio SET quantity = ?, avg_buy_price = ? WHERE user_id = ? AND asset_name = ?",
                 (new_qty, new_avg, message.from_user.id, asset_name))
    else:
        db_query("INSERT INTO user_portfolio (user_id, asset_name, quantity, avg_buy_price) VALUES (?,?,?,?)",
                 (message.from_user.id, asset_name, qty, price))

    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, message.from_user.id))

    bot.reply_to(message,
        f"✅ Куплено: **{qty}x {display}** за {total_cost:.2f} 💰\n"
        f"📊 Цена покупки: {price:.2f} 💰\n"
        f"💡 Следите за ценами через /market",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['sell'])
@group_only
def sell_asset_command(message):
    args = message.text.split()
    if len(args) < 3:
        return bot.reply_to(message, "Использование: /sell [актив] [количество]\nВаш портфель: /portfolio")

    asset_name = args[1].lower()
    try:
        qty = int(args[2])
    except ValueError:
        return bot.reply_to(message, "Количество должно быть числом.")
    if qty <= 0:
        return bot.reply_to(message, "Количество должно быть > 0.")

    asset = db_query("SELECT display_name, price FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"❌ Актив '{asset_name}' не найден.")

    display, price = asset
    holding = db_query(
        "SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?",
        (message.from_user.id, asset_name), fetchone=True
    )
    if not holding or holding[0] < qty:
        owned = holding[0] if holding else 0
        return bot.reply_to(message, f"❌ Недостаточно активов.\nУ вас: {owned} {display}")

    old_qty, avg_buy = holding
    total_revenue = round(price * qty, 2)
    profit = round((price - avg_buy) * qty, 2)
    profit_str = f"+{profit:.2f}" if profit >= 0 else f"{profit:.2f}"
    profit_emoji = "📈" if profit >= 0 else "📉"

    new_qty = old_qty - qty
    if new_qty == 0:
        db_query("DELETE FROM user_portfolio WHERE user_id = ? AND asset_name = ?",
                 (message.from_user.id, asset_name))
    else:
        db_query("UPDATE user_portfolio SET quantity = ? WHERE user_id = ? AND asset_name = ?",
                 (new_qty, message.from_user.id, asset_name))

    db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_revenue, message.from_user.id))

    bot.reply_to(message,
        f"💰 Продано: **{qty}x {display}** за {total_revenue:.2f} 💰\n"
        f"{profit_emoji} Прибыль/убыток: **{profit_str} 💰**\n"
        f"(Средняя цена покупки: {avg_buy:.2f} 💰)",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['portfolio'])
@group_only
def portfolio_command(message):
    holdings = db_query('''
        SELECT p.asset_name, p.quantity, p.avg_buy_price, m.price, m.display_name
        FROM user_portfolio p
        JOIN market_assets m ON p.asset_name = m.name
        WHERE p.user_id = ? AND p.quantity > 0
    ''', (message.from_user.id,))

    if not holdings:
        return bot.reply_to(message, "Ваш портфель пуст.\nНачните инвестировать через /market")

    text = "💼 **Ваш инвестиционный портфель:**\n\n"
    total_invested = 0
    total_current = 0

    for asset_name, qty, avg_buy, cur_price, display in holdings:
        invested = avg_buy * qty
        current = cur_price * qty
        profit = current - invested
        profit_str = f"+{profit:.2f}" if profit >= 0 else f"{profit:.2f}"
        arrow = "📈" if profit >= 0 else "📉"
        total_invested += invested
        total_current += current
        text += (
            f"{arrow} **{display}** x{qty}\n"
            f"   Куплено по: {avg_buy:.2f} - Сейчас: {cur_price:.2f}\n"
            f"   Стоимость: {current:.2f} 💰 (P&L: {profit_str} 💰)\n\n"
        )

    total_profit = total_current - total_invested
    total_str = f"+{total_profit:.2f}" if total_profit >= 0 else f"{total_profit:.2f}"
    text += (
        f"📊 **Вложено: {total_invested:.2f} 💰**\n"
        f"💰 **Текущая стоимость: {total_current:.2f} 💰**\n"
        f"{'📈' if total_profit >= 0 else '📉'} **Общий P&L: {total_str} 💰**"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ==============================================================
# --- ADMIN-КОМАНДЫ ---
# ==============================================================

@bot.message_handler(commands=['setprice'])
@group_only
def setprice_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Использование: /setprice [актив] [цена]")
    asset_name = args[1].lower()
    try:
        new_price = float(args[2])
    except ValueError:
        return bot.reply_to(message, "Цена должна быть числом.")
    if new_price <= 0:
        return bot.reply_to(message, "Цена должна быть > 0.")
    asset = db_query("SELECT display_name FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"Актив '{asset_name}' не найден.")
    db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
             (new_price, time.time(), asset_name))
    bot.reply_to(message, f"✅ [ADMIN] Цена на **{asset[0]}** - {new_price:.2f} 💰", parse_mode="Markdown")

@bot.message_handler(commands=['setbaseprice'])
@group_only
def setbaseprice_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Использование: /setbaseprice [актив] [цена]")
    asset_name = args[1].lower()
    try:
        new_base = float(args[2])
    except ValueError:
        return bot.reply_to(message, "Цена должна быть числом.")
    asset = db_query("SELECT display_name FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"Актив '{asset_name}' не найден.")
    db_query("UPDATE market_assets SET base_price = ? WHERE name = ?", (new_base, asset_name))
    bot.reply_to(message, f"✅ [ADMIN] Базовая цена **{asset[0]}** - {new_base:.2f} 💰", parse_mode="Markdown")

@bot.message_handler(commands=['marketevent'])
@group_only
def marketevent_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Использование: /marketevent [актив] [+-процент]\nПример: /marketevent oil -30")
    asset_name = args[1].lower()
    try:
        percent = float(args[2])
    except ValueError:
        return bot.reply_to(message, "Процент должен быть числом.")
    asset = db_query("SELECT display_name, price FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"Актив '{asset_name}' не найден.")
    display, old_price = asset
    new_price = round(max(0.01, old_price * (1 + percent / 100)), 2)
    db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
             (new_price, time.time(), asset_name))
    direction = "выросла" if percent >= 0 else "упала"
    arrow = "📈" if percent >= 0 else "📉"
    bot.reply_to(message,
        f"⚡ [ADMIN] Рыночное событие в Аурелии!\n\n"
        f"{arrow} Цена на **{display}** {direction} на {abs(percent):.1f}%\n"
        f"{old_price:.2f} - **{new_price:.2f}** 💰",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['marketcrash'])
@group_only
def marketcrash_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    assets = db_query("SELECT name, display_name, price FROM market_assets")
    text = "🔴 **[ADMIN] ОБВАЛ РЫНКА АУРЕЛИИ!**\n\n"
    for name, display, price in assets:
        drop = random.uniform(0.20, 0.50)
        new_price = round(price * (1 - drop), 2)
        db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
                 (new_price, time.time(), name))
        text += f"📉 {display}: {price:.2f} - **{new_price:.2f}** (-{drop*100:.1f}%)\n"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['marketboom'])
@group_only
def marketboom_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    assets = db_query("SELECT name, display_name, price FROM market_assets")
    text = "🟢 **[ADMIN] БУМ НА РЫНКЕ АУРЕЛИИ!**\n\n"
    for name, display, price in assets:
        rise = random.uniform(0.20, 0.50)
        new_price = round(price * (1 + rise), 2)
        db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
                 (new_price, time.time(), name))
        text += f"📈 {display}: {price:.2f} - **{new_price:.2f}** (+{rise*100:.1f}%)\n"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['resetmarket'])
@group_only
def resetmarket_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    db_query("UPDATE market_assets SET price = base_price, last_updated = ?", (time.time(),))
    bot.reply_to(message, "✅ [ADMIN] Все цены сброшены к базовым значениям.")

@bot.message_handler(commands=['adminhelp'])
@group_only
def adminhelp_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    bot.reply_to(message,
        "🔧 **Админ-команды биржи Аурелии:**\n\n"
        "/setprice [актив] [цена] - установить цену\n"
        "/setbaseprice [актив] [цена] - изменить базовую цену\n"
        "/marketevent [актив] [+-%] - изменить цену актива на %\n"
        "/marketcrash - обвал всего рынка\n"
        "/marketboom - рост всего рынка\n"
        "/resetmarket - сброс к базовым ценам\n\n"
        "**Активы:** oil, gold, steel, aur",
        parse_mode="Markdown"
    )

# ==============================================================
bot.polling(none_stop=True)
