import telebot
import sqlite3
import time
import random
import threading

TOKEN = '8595324337:AAHQ-tDAN2r3hkshJTH7UYuWMPEsmbfe7qI'
ADMIN_IDS = [6115517123]  # Вставь свои Telegram ID через запятую

bot = telebot.TeleBot(TOKEN)

# ==============================================================
# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
# ==============================================================
def init_db():
    conn = sqlite3.connect('vpi_economy.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 1000,
            level INTEGER DEFAULT 1,
            last_cash REAL DEFAULT 0
        )
    ''')

    # Виды бизнесов (справочник)
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

    # Бизнесы, которыми владеют пользователи
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            business_name TEXT,
            quantity INTEGER DEFAULT 1,
            UNIQUE(user_id, business_name)
        )
    ''')

    # Биржевые активы и их цены
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

    # Портфель пользователей (акции/ресурсы)
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

    # Заполняем справочник бизнесов если пусто
    businesses = [
        ('factory',   '🏭 Завод',          5000,  120, 'Производит товары, приносит стабильный доход'),
        ('farm',      '🌾 Ферма',           2000,   40, 'Небольшой, но надёжный источник дохода'),
        ('mine',      '⛏️ Шахта',           8000,  220, 'Добывает ресурсы, высокая доходность'),
        ('casino',    '🎰 Казино',         15000,  450, 'Огромный доход, но требует больших вложений'),
        ('bank_biz',  '🏦 Частный банк',   30000,  950, 'Элитный бизнес с максимальным пассивным доходом'),
    ]
    cursor.executemany(
        'INSERT OR IGNORE INTO business_types (name, display_name, cost, income_per_hour, description) VALUES (?,?,?,?,?)',
        businesses
    )

    # Заполняем биржу если пусто
    assets = [
        ('oil',    '🛢️ Нефть',    100.0,  100.0, '🛢️'),
        ('gold',   '🥇 Золото',   500.0,  500.0, '🥇'),
        ('steel',  '⚙️ Сталь',    80.0,   80.0,  '⚙️'),
        ('vpi',    '📊 Акции', 300.0, 300.0, '📊'),
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
    conn = sqlite3.connect('vpi_economy.db', check_same_thread=False)
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

# ==============================================================
# --- ФОНОВЫЕ ПОТОКИ ---
# ==============================================================

def market_price_updater():
    """Каждый час случайно изменяет цены на бирже."""
    while True:
        time.sleep(3600)  # раз в час
        assets = db_query("SELECT name, price, base_price FROM market_assets")
        for name, price, base_price in assets:
            # Цена гуляет ±25% от текущей, но не уходит дальше 50% от базовой
            change = random.uniform(-0.25, 0.25)
            new_price = price * (1 + change)
            # Ограничиваем диапазон: от 50% до 200% базовой цены
            new_price = max(base_price * 0.5, min(base_price * 2.0, new_price))
            new_price = round(new_price, 2)
            db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
                     (new_price, time.time(), name))

def passive_income_distributor():
    """Каждые 10 минут начисляет пассивный доход от бизнесов."""
    INTERVAL = 600  # 10 минут
    while True:
        time.sleep(INTERVAL)
        # Получаем всех владельцев бизнесов
        owners = db_query('''
            SELECT ub.user_id, ub.business_name, ub.quantity, bt.income_per_hour
            FROM user_businesses ub
            JOIN business_types bt ON ub.business_name = bt.name
        ''')
        # Группируем по user_id
        income_map = {}
        for user_id, bname, qty, iph in owners:
            income = int(iph * qty * (INTERVAL / 3600))  # доход за прошедший интервал
            income_map[user_id] = income_map.get(user_id, 0) + income

        for user_id, income in income_map.items():
            if income > 0:
                db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (income, user_id))

# Запускаем фоновые потоки
threading.Thread(target=market_price_updater, daemon=True).start()
threading.Thread(target=passive_income_distributor, daemon=True).start()

# ==============================================================
# --- СУЩЕСТВУЮЩИЕ КОМАНДЫ ---
# ==============================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Игрок"
    user = db_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        db_query("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        bot.reply_to(message,
            "🏛 Добро пожаловать в экономику ВПИ!\n\n"
            "💰 Стартовый капитал: 1000\n\n"
            "📋 Основные команды:\n"
            "/profile — профиль\n/cash — сбор налогов\n/upgrade — улучшить экономику\n"
            "/pay — перевести деньги\n\n"
            "🏢 Бизнес:\n/shop — магазин бизнесов\n/mybiz — мои бизнесы\n\n"
            "📈 Биржа:\n/market — текущие цены\n/buy — купить актив\n/sell — продать актив\n/portfolio — мой портфель"
        )
    else:
        bot.reply_to(message, "Вы уже зарегистрированы! Используйте /profile.")

@bot.message_handler(commands=['profile'])
def profile_command(message):
    user = db_query("SELECT balance, level FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Вы не зарегистрированы! Введите /start.")

    # Считаем суммарный пассивный доход в час
    biz_data = db_query('''
        SELECT ub.quantity, bt.income_per_hour FROM user_businesses ub
        JOIN business_types bt ON ub.business_name = bt.name
        WHERE ub.user_id = ?
    ''', (message.from_user.id,))
    passive = sum(q * iph for q, iph in biz_data) if biz_data else 0

    bot.reply_to(message,
        f"👤 **Ваш профиль:**\n\n"
        f"💰 Баланс: {user[0]}\n"
        f"📈 Уровень: {user[1]}\n"
        f"🏭 Пассивный доход: ~{passive} 💰/час\n\n"
        f"Используйте /cash для сбора налогов.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['cash'])
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
        bot.reply_to(message, f"⏳ Следующий сбор налогов через {left_time // 60} мин. {left_time % 60} сек.")
        return

    base_income = 500
    level_multiplier = 1 + (level * 0.2)
    market_luck = random.uniform(0.8, 1.2)
    earned = int(base_income * level_multiplier * market_luck)
    new_balance = balance + earned

    db_query("UPDATE users SET balance = ?, last_cash = ? WHERE user_id = ?", (new_balance, current_time, user_id))

    if market_luck > 1.1:
        event = "📈 В государстве экономический бум!"
    elif market_luck < 0.9:
        event = "📉 На рынках кризис, налоги собраны с трудом."
    else:
        event = "⚖️ Экономика стабильна."

    bot.reply_to(message, f"{event}\n💵 Вы заработали: **{earned}** 💰\nБаланс: {new_balance} 💰", parse_mode="Markdown")

@bot.message_handler(commands=['upgrade'])
def upgrade_command(message):
    user = db_query("SELECT balance, level FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Введите /start")
    balance, level = user
    upgrade_cost = level * 1500
    if balance >= upgrade_cost:
        db_query("UPDATE users SET balance = ?, level = ? WHERE user_id = ?",
                 (balance - upgrade_cost, level + 1, message.from_user.id))
        bot.reply_to(message, f"✅ Экономика улучшена до {level + 1} уровня за {upgrade_cost} 💰!")
    else:
        bot.reply_to(message, f"❌ Нужно {upgrade_cost} 💰, у вас {balance} 💰.")

@bot.message_handler(commands=['pay'])
def pay_command(message):
    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Использование: /pay [ID] [сумма]")
    try:
        target_id = int(args[1])
        amount = int(args[2])
    except ValueError:
        return bot.reply_to(message, "ID и сумма должны быть числами.")
    if amount <= 0:
        return bot.reply_to(message, "Сумма должна быть больше нуля.")

    sender = db_query("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    target = db_query("SELECT balance FROM users WHERE user_id = ?", (target_id,), fetchone=True)
    if not sender or not target:
        return bot.reply_to(message, "Один из пользователей не найден.")
    if sender[0] < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, message.from_user.id))
    db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
    bot.reply_to(message, f"💸 Переведено {amount} 💰 игроку с ID {target_id}.")

# ==============================================================
# --- БИЗНЕСЫ ---
# ==============================================================

@bot.message_handler(commands=['shop'])
def shop_command(message):
    businesses = db_query("SELECT name, display_name, cost, income_per_hour, description FROM business_types")
    if not businesses:
        return bot.reply_to(message, "Магазин пуст.")

    text = "🏪 **Магазин бизнесов:**\n\n"
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
def buybiz_command(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Использование: /buybiz [название]\nСписок бизнесов: /shop")

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
        return bot.reply_to(message, f"❌ Недостаточно средств.\nНужно: {total_cost} 💰\nУ вас: {user[0]} 💰")

    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, message.from_user.id))
    db_query('''
        INSERT INTO user_businesses (user_id, business_name, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, business_name) DO UPDATE SET quantity = quantity + ?
    ''', (message.from_user.id, biz_name, qty, qty))

    bot.reply_to(message,
        f"✅ Вы купили **{qty}x {display}** за {total_cost} 💰!\n"
        f"📊 Пассивный доход от этого бизнеса: ~{iph * qty} 💰/час\n"
        f"💡 Доход начисляется автоматически каждые 10 минут.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['mybiz'])
def mybiz_command(message):
    businesses = db_query('''
        SELECT bt.display_name, ub.quantity, bt.income_per_hour
        FROM user_businesses ub
        JOIN business_types bt ON ub.business_name = bt.name
        WHERE ub.user_id = ?
    ''', (message.from_user.id,))

    if not businesses:
        return bot.reply_to(message,
            "У вас нет бизнесов. Купите их в /shop\n"
            "💡 Бизнесы приносят пассивный доход автоматически!"
        )

    text = "🏢 **Ваши бизнесы:**\n\n"
    total_iph = 0
    for display, qty, iph in businesses:
        subtotal = iph * qty
        total_iph += subtotal
        text += f"{display} x{qty} → {subtotal} 💰/час\n"

    text += f"\n📊 **Итого: ~{total_iph} 💰/час**\n"
    text += f"💰 В сутки: ~{total_iph * 24} 💰\n"
    text += "\n💡 Доход начисляется на баланс автоматически каждые 10 минут."

    bot.reply_to(message, text, parse_mode="Markdown")

# ==============================================================
# --- БИРЖА ---
# ==============================================================

def get_price_arrow(price, base_price):
    if price > base_price * 1.1:
        return "📈"
    elif price < base_price * 0.9:
        return "📉"
    return "➡️"

@bot.message_handler(commands=['market'])
def market_command(message):
    assets = db_query("SELECT name, display_name, price, base_price, emoji FROM market_assets")
    text = "📊 **Биржа ВПИ — Текущие цены:**\n\n"
    for name, display, price, base_price, emoji in assets:
        arrow = get_price_arrow(price, base_price)
        change_pct = ((price - base_price) / base_price) * 100
        sign = "+" if change_pct >= 0 else ""
        text += (
            f"{arrow} **{display}**\n"
            f"   💵 Цена: {price:.2f} 💰 ({sign}{change_pct:.1f}% от базовой)\n"
            f"   Купить: `/buy {name} [кол-во]`\n"
            f"   Продать: `/sell {name} [кол-во]`\n\n"
        )
    text += "⏰ Цены обновляются каждый час случайным образом.\n/portfolio — ваш портфель"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['buy'])
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
        return bot.reply_to(message, f"❌ Недостаточно средств.\nНужно: {total_cost} 💰\nУ вас: {user[0]} 💰")

    # Обновляем среднюю цену покупки
    existing = db_query("SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?",
                        (message.from_user.id, asset_name), fetchone=True)
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
        f"📊 Средняя цена покупки: {price:.2f} 💰\n"
        f"💡 Следите за ценами через /market и продавайте по /sell",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['sell'])
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
    holding = db_query("SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?",
                       (message.from_user.id, asset_name), fetchone=True)
    if not holding or holding[0] < qty:
        owned = holding[0] if holding else 0
        return bot.reply_to(message, f"❌ Недостаточно активов. У вас: {owned} {display}")

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
        f"(Средняя цена покупки была: {avg_buy:.2f} 💰)",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['portfolio'])
def portfolio_command(message):
    holdings = db_query('''
        SELECT p.asset_name, p.quantity, p.avg_buy_price, m.price, m.display_name
        FROM user_portfolio p
        JOIN market_assets m ON p.asset_name = m.name
        WHERE p.user_id = ? AND p.quantity > 0
    ''', (message.from_user.id,))

    if not holdings:
        return bot.reply_to(message, "Ваш инвестиционный портфель пуст.\nНачните инвестировать через /market")

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
            f"   Куплено по: {avg_buy:.2f} | Сейчас: {cur_price:.2f}\n"
            f"   Стоимость: {current:.2f} 💰 (P&L: {profit_str} 💰)\n\n"
        )

    total_profit = total_current - total_invested
    total_str = f"+{total_profit:.2f}" if total_profit >= 0 else f"{total_profit:.2f}"
    text += f"📊 **Итого вложено: {total_invested:.2f} 💰**\n"
    text += f"💰 **Текущая стоимость: {total_current:.2f} 💰**\n"
    text += f"{'📈' if total_profit >= 0 else '📉'} **Общий P&L: {total_str} 💰**"

    bot.reply_to(message, text, parse_mode="Markdown")

# ==============================================================
# --- ADMIN-КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ БИРЖЕЙ ---
# ==============================================================

@bot.message_handler(commands=['setprice'])
def setprice_command(message):
    """Админ: /setprice [актив] [цена] — установить цену напрямую"""
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
    bot.reply_to(message, f"✅ [ADMIN] Цена на **{asset[0]}** установлена: {new_price:.2f} 💰", parse_mode="Markdown")

@bot.message_handler(commands=['setbaseprice'])
def setbaseprice_command(message):
    """Админ: /setbaseprice [актив] [цена] — изменить базовую цену (центр колебаний)"""
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
    bot.reply_to(message, f"✅ [ADMIN] Базовая цена **{asset[0]}** → {new_base:.2f} 💰", parse_mode="Markdown")

@bot.message_handler(commands=['marketevent'])
def marketevent_command(message):
    """Админ: /marketevent [актив] [±процент] — рыночное событие, изменяет цену на %"""
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")

    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Использование: /marketevent [актив] [±процент]\nПример: /marketevent oil -30")

    asset_name = args[1].lower()
    try:
        percent = float(args[2])
    except ValueError:
        return bot.reply_to(message, "Процент должен быть числом (например: 25 или -15).")

    asset = db_query("SELECT display_name, price FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"Актив '{asset_name}' не найден.")

    display, old_price = asset
    new_price = round(old_price * (1 + percent / 100), 2)
    new_price = max(0.01, new_price)

    db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
             (new_price, time.time(), asset_name))

    direction = "выросла" if percent >= 0 else "упала"
    arrow = "📈" if percent >= 0 else "📉"

    bot.reply_to(message,
        f"⚡ [ADMIN EVENT] Рыночное событие!\n\n"
        f"{arrow} Цена на **{display}** {direction} на {abs(percent):.1f}%\n"
        f"{old_price:.2f} → **{new_price:.2f}** 💰",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['marketcrash'])
def marketcrash_command(message):
    """Админ: /marketcrash — обвал всего рынка (-20% до -50% по всем активам)"""
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")

    assets = db_query("SELECT name, display_name, price FROM market_assets")
    text = "🔴 **[ADMIN] ОБВАЛ РЫНКА!**\n\n"
    for name, display, price in assets:
        drop = random.uniform(0.20, 0.50)
        new_price = round(price * (1 - drop), 2)
        db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
                 (new_price, time.time(), name))
        text += f"📉 {display}: {price:.2f} → **{new_price:.2f}** (-{drop*100:.1f}%)\n"

    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['marketboom'])
def marketboom_command(message):
    """Админ: /marketboom — рост всего рынка (+20% до +50% по всем активам)"""
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")

    assets = db_query("SELECT name, display_name, price FROM market_assets")
    text = "🟢 **[ADMIN] БУМ НА РЫНКЕ!**\n\n"
    for name, display, price in assets:
        rise = random.uniform(0.20, 0.50)
        new_price = round(price * (1 + rise), 2)
        db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
                 (new_price, time.time(), name))
        text += f"📈 {display}: {price:.2f} → **{new_price:.2f}** (+{rise*100:.1f}%)\n"

    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['resetmarket'])
def resetmarket_command(message):
    """Админ: /resetmarket — сброс всех цен к базовым значениям"""
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")

    db_query("UPDATE market_assets SET price = base_price, last_updated = ?", (time.time(),))
    bot.reply_to(message, "✅ [ADMIN] Все цены сброшены к базовым значениям.")

@bot.message_handler(commands=['adminhelp'])
def adminhelp_command(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "⛔ Нет доступа.")
    bot.reply_to(message,
        "🔧 **Админ-команды биржи:**\n\n"
        "/setprice [актив] [цена] — установить цену\n"
        "/setbaseprice [актив] [цена] — изменить базовую цену\n"
        "/marketevent [актив] [±%] — изменить цену актива на %\n"
        "/marketcrash — обвал всего рынка\n"
        "/marketboom — рост всего рынка\n"
        "/resetmarket — сброс к базовым ценам\n\n"
        "**Названия активов:** oil, gold, crypto, steel, vpi",
        parse_mode="Markdown"
    )

# ==============================================================
bot.polling(none_stop=True)
