import telebot
import sqlite3
import time
import random
import threading

TOKEN = '8595324337:AAHQ-tDAN2r3hkshJTH7UYuWMPEsmbfe7qI'
ADMIN_IDS = [6115517123, 2046462689, 7787565361]       # Telegram ID админов
ALLOWED_GROUP_ID = -1003880025896  # ID вашей группы (отрицательное число)

bot = telebot.TeleBot(TOKEN)

# ==============================================================
# --- ФИЛЬТР ГРУППЫ ---
# ==============================================================
def group_only(func):
    """Декоратор: команда работает только в разрешённой группе."""
    def wrapper(message):
        if message.chat.id != ALLOWED_GROUP_ID:
            return  # Просто игнорируем
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
            last_cash REAL DEFAULT 0,
            troops INTEGER DEFAULT 0,
            last_draft REAL DEFAULT 0
        )
    ''')

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN troops INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN last_draft REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Колонки уже существуют

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS military_types (
            name TEXT PRIMARY KEY,
            display_name TEXT,
            steel_cost INTEGER,
            money_cost INTEGER,
            description TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_military (
            user_id INTEGER,
            unit_name TEXT,
            quantity INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, unit_name)
        )
    ''')

    conn.commit()

    businesses = [
        ('farm',      '🌾 Ферма',           2000,   40,  'Небольшой, но надёжный источник дохода'),
        ('factory',   '🏭 Завод',            5000,  120,  'Производит товары, стабильный доход'),
        ('mine',      '⛏️ Шахта',            8000,  220,  'Добывает ресурсы, высокая доходность'),
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

    military = [
        ('rifle',     '🔫 Винтовки',     2,    100,    'Базовое вооружение пехоты'),
        ('tank',      '🛡️ Танки',        50,   5000,   'Тяжелая бронетехника для прорыва'),
        ('plane',     '✈️ Авиация',      120,  15000,  'Господство в воздухе'),
        ('ship',      '🚢 Эсминцы',      200,  25000,  'Основа военно-морского флота'),
        ('submarine', '🛥️ Подлодки',     150,  20000,  'Скрытые морские удары'),
        ('carrier',   '⛴️ Авианосцы',    1000, 150000, 'Полное господство в океане'),
    ]
    cursor.executemany(
        'INSERT OR IGNORE INTO military_types (name, display_name, steel_cost, money_cost, description) VALUES (?,?,?,?,?)',
        military
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
            "🌍 Добро пожаловать в мир Аурелии!\n\n"
            "💰 Стартовый капитал: 1000\n\n"
            "📋 Основные команды:\n"
            "/profile - профиль\n"
            "/cash - сбор налогов\n"
            "/upgrade - улучшить экономику\n"
            "/pay @юзернейм сумма - перевод денег\n"
            "/senditem @юзернейм актив сумма - передача ресурсов\n\n"
            "🏢 Бизнес и Биржа:\n"
            "/shop | /mybiz | /market | /portfolio | /buy | /sell\n\n"
            "⚔️ Военное дело и Флот:\n"
            "/draft - призыв войск (раз в 2 часа)\n"
            "/craft - производство техники и кораблей\n"
            "/army - ваша армия и флот\n\n"
            "🏆 Рейтинги мира:\n"
            "/top - топ по ресурсам и валюте\n"
            "/worldstats - мировая статистика"
        )
    else:
        db_query("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        bot.reply_to(message, "Вы уже зарегистрированы в Аурелии! Используйте /profile.")

@bot.message_handler(commands=['profile'])
@group_only
def profile_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"player_{user_id}"
    db_query("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))

    user = db_query("SELECT balance, level, troops FROM users WHERE user_id = ?", (user_id,), fetchone=True)
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
        f"📈 Уровень экономики: {user[1]}\n"
        f"🪖 Войск в резерве: {user[2]}\n"
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

    bot.reply_to(message, f"💵 Вы собрали налоги с ваших территорий: **{earned}** 💰\nБаланс: {new_balance} 💰", parse_mode="Markdown")

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
        bot.reply_to(message, f"✅ Экономика улучшена до {level + 1} уровня за {upgrade_cost} 💰!")
    else:
        bot.reply_to(message, f"❌ Недостаточно средств.\nНужно: {upgrade_cost} 💰\nБаланс: {balance} 💰")

# ==============================================================
# --- ВОЕННОЕ ДЕЛО И ПРОИЗВОДСТВО ---
# ==============================================================

@bot.message_handler(commands=['draft'])
@group_only
def draft_command(message):
    user_id = message.from_user.id
    user = db_query("SELECT troops, last_draft FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Сначала введите /start")

    troops, last_draft = user
    current_time = time.time()
    cooldown = 7200 # 2 часа

    if current_time - last_draft < cooldown:
        left_time = int(cooldown - (current_time - last_draft))
        bot.reply_to(message, f"⏳ Резервы истощены. Следующий призыв через {left_time // 3600} ч. {(left_time % 3600) // 60} мин.")
        return

    new_recruits = random.randint(1000, 2000)
    db_query("UPDATE users SET troops = troops + ?, last_draft = ? WHERE user_id = ?", (new_recruits, current_time, user_id))

    bot.reply_to(message, f"🪖 **Призыв завершен!**\nВ ряды вашей армии вступило **{new_recruits}** новобранцев.\nВсего войск: {troops + new_recruits}", parse_mode="Markdown")

@bot.message_handler(commands=['craft'])
@group_only
def craft_command(message):
    args = message.text.split()
    if len(args) < 3:
        types = db_query("SELECT name, display_name, steel_cost, money_cost FROM military_types")
        text = "⚙️ **Военное и морское производство:**\nИспользование: `/craft [тип] [количество]`\n\n"
        for name, display, steel, money in types:
            text += f"{display} (`{name}`) — {steel} ⚙️ Стали, {money} 💰\n"
        return bot.reply_to(message, text, parse_mode="Markdown")

    unit_name = args[1].lower()
    try:
        qty = int(args[2])
    except ValueError:
        return bot.reply_to(message, "Количество должно быть числом.")
    if qty <= 0:
        return bot.reply_to(message, "Количество должно быть больше нуля.")

    unit = db_query("SELECT display_name, steel_cost, money_cost FROM military_types WHERE name = ?", (unit_name,), fetchone=True)
    if not unit:
        return bot.reply_to(message, f"❌ Чертеж '{unit_name}' не найден.")

    display, steel_cost, money_cost = unit
    total_steel = steel_cost * qty
    total_money = money_cost * qty

    user = db_query("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    user_steel = db_query("SELECT quantity FROM user_portfolio WHERE user_id = ? AND asset_name = 'steel'", (message.from_user.id,), fetchone=True)
    
    current_steel = user_steel[0] if user_steel else 0
    current_money = user[0] if user else 0

    if current_money < total_money or current_steel < total_steel:
        return bot.reply_to(message, f"❌ Недостаточно ресурсов!\nТребуется: {total_steel} ⚙️ Стали и {total_money} 💰\nВ наличии: {current_steel} ⚙️ Стали и {current_money} 💰")

    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_money, message.from_user.id))
    db_query("UPDATE user_portfolio SET quantity = quantity - ? WHERE user_id = ? AND asset_name = 'steel'", (total_steel, message.from_user.id))
    
    db_query('''
        INSERT INTO user_military (user_id, unit_name, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, unit_name) DO UPDATE SET quantity = quantity + ?
    ''', (message.from_user.id, unit_name, qty, qty))

    bot.reply_to(message, f"🏭 Произведено: **{qty}x {display}**\nПотрачено: {total_steel} ⚙️ Стали, {total_money} 💰", parse_mode="Markdown")

@bot.message_handler(commands=['army'])
@group_only
def army_command(message):
    user = db_query("SELECT troops FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    units = db_query('''
        SELECT m.display_name, u.quantity 
        FROM user_military u 
        JOIN military_types m ON u.unit_name = m.name 
        WHERE u.user_id = ? AND u.quantity > 0
    ''', (message.from_user.id,))

    if not user:
        return bot.reply_to(message, "Сначала введите /start")

    text = f"⚔️ **Ваши Вооруженные силы и Флот:**\n\n🪖 Пехота: {user[0]}\n"
    if units:
        text += "\n**Техника и Корабли:**\n"
        for display, qty in units:
            text += f"{display}: {qty} шт.\n"
    else:
        text += "\nТехника и флот отсутствуют. Постройте их через /craft"

    bot.reply_to(message, text, parse_mode="Markdown")


# ==============================================================
# --- РЕЙТИНГИ И СТАТИСТИКА (Новое) ---
# ==============================================================

@bot.message_handler(commands=['top'])
@group_only
def top_command(message):
    args = message.text.split()
    if len(args) < 2:
        assets = db_query("SELECT name, display_name FROM market_assets")
        text = "🏆 **Рейтинги мира Аурелия:**\n\nИспользование: `/top [категория]`\n\n**Доступные категории:**\n`/top money` — Топ по валюте 💰\n"
        for name, display in assets:
            text += f"`/top {name}` — Топ по {display}\n"
        return bot.reply_to(message, text, parse_mode="Markdown")

    category = args[1].lower()
    
    if category == 'money':
        top_users = db_query("SELECT username, balance FROM users WHERE balance > 0 ORDER BY balance DESC LIMIT 10")
        if not top_users:
            return bot.reply_to(message, "Рейтинг пуст.")
        text = "🏆 **Топ богатейших правителей (Баланс):**\n\n"
        for i, (uname, val) in enumerate(top_users, start=1):
            text += f"{i}. @{uname} — {val} 💰\n"
        return bot.reply_to(message, text, parse_mode="Markdown")
    
    asset = db_query("SELECT display_name FROM market_assets WHERE name = ?", (category,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"❌ Категория '{category}' не найдена. Напишите `/top` для списка.")
        
    display = asset[0]
    top_users = db_query('''
        SELECT u.username, p.quantity 
        FROM user_portfolio p 
        JOIN users u ON p.user_id = u.user_id 
        WHERE p.asset_name = ? AND p.quantity > 0 
        ORDER BY p.quantity DESC LIMIT 10
    ''', (category,))
    
    if not top_users:
        return bot.reply_to(message, f"Рейтинг по активу {display} пока пуст.")
        
    text = f"🏆 **Топ магнатов Аурелии ({display}):**\n\n"
    for i, (uname, val) in enumerate(top_users, start=1):
        text += f"{i}. @{uname} — {val} шт.\n"
    return bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['worldstats'])
@group_only
def worldstats_command(message):
    total_money = db_query("SELECT SUM(balance) FROM users", fetchone=True)[0] or 0
    total_troops = db_query("SELECT SUM(troops) FROM users", fetchone=True)[0] or 0
    total_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0] or 0
    
    bot.reply_to(message, 
        f"🌍 **Глобальная статистика мира Аурелия:**\n\n"
        f"👥 Зарегистрировано правителей: {total_users}\n"
        f"💰 Валюты в обороте: {total_money} 💰\n"
        f"🪖 Общая численность мировых войск: {total_troops}",
        parse_mode="Markdown"
    )

# ==============================================================
# --- ТОРГОВЛЯ И ПЕРЕВОДЫ ---
# ==============================================================

@bot.message_handler(commands=['pay'])
@group_only
def pay_command(message):
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

    if not target:
        return bot.reply_to(message, f"❌ Игрок @{target_username} не найден.")
    if not sender or sender[0] < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
    db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target[0]))

    bot.reply_to(message, f"💸 Переведено **{amount}** 💰 игроку @{target_username}.", parse_mode="Markdown")

@bot.message_handler(commands=['senditem'])
@group_only
def senditem_command(message):
    args = message.text.split()
    if len(args) != 4:
        return bot.reply_to(message, "Использование: `/senditem @юзернейм [актив] [количество]`", parse_mode="Markdown")

    target_username = args[1].lstrip('@').lower()
    asset_name = args[2].lower()
    try:
        amount = int(args[3])
    except ValueError:
        return bot.reply_to(message, "Количество должно быть числом.")
    
    if amount <= 0:
        return bot.reply_to(message, "Количество должно быть больше нуля.")

    sender_id = message.from_user.id
    if target_username == (message.from_user.username or "").lower():
        return bot.reply_to(message, "Нельзя отправить ресурсы самому себе.")

    target = db_query("SELECT user_id FROM users WHERE LOWER(username) = ?", (target_username,), fetchone=True)
    if not target:
        return bot.reply_to(message, f"❌ Игрок @{target_username} не найден.")
    target_id = target[0]

    asset_check = db_query("SELECT display_name FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset_check:
        return bot.reply_to(message, f"❌ Актив '{asset_name}' не существует.")
    display = asset_check[0]

    sender_portfolio = db_query("SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?", (sender_id, asset_name), fetchone=True)
    
    if not sender_portfolio or sender_portfolio[0] < amount:
        return bot.reply_to(message, f"❌ У вас недостаточно актива **{display}**.", parse_mode="Markdown")

    new_sender_qty = sender_portfolio[0] - amount
    if new_sender_qty == 0:
        db_query("DELETE FROM user_portfolio WHERE user_id = ? AND asset_name = ?", (sender_id, asset_name))
    else:
        db_query("UPDATE user_portfolio SET quantity = ? WHERE user_id = ? AND asset_name = ?", (new_sender_qty, sender_id, asset_name))

    target_portfolio = db_query("SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?", (target_id, asset_name), fetchone=True)
    if target_portfolio:
        new_avg = ((target_portfolio[0] * target_portfolio[1]) + (amount * sender_portfolio[1])) / (target_portfolio[0] + amount)
        db_query("UPDATE user_portfolio SET quantity = quantity + ?, avg_buy_price = ? WHERE user_id = ? AND asset_name = ?", (amount, new_avg, target_id, asset_name))
    else:
        db_query("INSERT INTO user_portfolio (user_id, asset_name, quantity, avg_buy_price) VALUES (?,?,?,?)", (target_id, asset_name, amount, sender_portfolio[1]))

    bot.reply_to(message, f"📦 Вы успешно передали **{amount}x {display}** игроку @{target_username}.", parse_mode="Markdown")

# ==============================================================
# --- МАГАЗИН И БИЗНЕСЫ ---
# ==============================================================

@bot.message_handler(commands=['shop'])
@group_only
def shop_command(message):
    businesses = db_query("SELECT name, display_name, cost, income_per_hour, description FROM business_types")
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
    if not is_admin(message.from_user.id): return
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

@bot.message_handler(commands=['givemoney'])
@group_only
def givemoney_command(message):
    """Выдает деньги игроку (для админов)"""
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) != 3:
        return bot.reply_to(message, "Использование: /givemoney @юзернейм [сумма]")
    target_username = args[1].lstrip('@').lower()
    try:
        amount = int(args[2])
    except ValueError:
        return bot.reply_to(message, "Сумма должна быть числом.")
    
    target = db_query("SELECT user_id FROM users WHERE LOWER(username) = ?", (target_username,), fetchone=True)
    if not target:
        return bot.reply_to(message, f"❌ Игрок @{target_username} не найден.")
        
    db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target[0]))
    bot.reply_to(message, f"✅ [ADMIN] Игроку @{target_username} выдано {amount} 💰")

@bot.message_handler(commands=['giveitem'])
@group_only
def giveitem_command(message):
    """Выдает ресурс игроку (для админов)"""
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) != 4:
        return bot.reply_to(message, "Использование: /giveitem @юзернейм [актив] [количество]")
    target_username = args[1].lstrip('@').lower()
    asset_name = args[2].lower()
    try:
        amount = int(args[3])
    except ValueError:
        return bot.reply_to(message, "Количество должно быть числом.")
        
    target = db_query("SELECT user_id FROM users WHERE LOWER(username) = ?", (target_username,), fetchone=True)
    if not target:
        return bot.reply_to(message, f"❌ Игрок @{target_username} не найден.")
        
    asset = db_query("SELECT price FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset:
        return bot.reply_to(message, f"❌ Актив '{asset_name}' не найден.")
        
    target_id = target[0]
    target_portfolio = db_query("SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?", (target_id, asset_name), fetchone=True)
    if target_portfolio:
        # При бесплатной выдаче админом, не меняем среднюю цену покупки, чтобы не портить статистику
        db_query("UPDATE user_portfolio SET quantity = quantity + ? WHERE user_id = ? AND asset_name = ?", (amount, target_id, asset_name))
    else:
        db_query("INSERT INTO user_portfolio (user_id, asset_name, quantity, avg_buy_price) VALUES (?,?,?,?)", (target_id, asset_name, amount, 0))
        
    bot.reply_to(message, f"✅ [ADMIN] Игроку @{target_username} выдано {amount}x {asset_name}")

@bot.message_handler(commands=['marketcrash'])
@group_only
def marketcrash_command(message):
    if not is_admin(message.from_user.id): return
    assets = db_query("SELECT name, display_name, price FROM market_assets")
    text = "🔴 **ОБВАЛ РЫНКА АУРЕЛИИ!**\n\nЭкономика переживает тяжелые времена:\n"
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
    if not is_admin(message.from_user.id): return
    assets = db_query("SELECT name, display_name, price FROM market_assets")
    text = "🟢 **БУМ НА РЫНКЕ АУРЕЛИИ!**\n\nИнвесторы ликуют:\n"
    for name, display, price in assets:
        rise = random.uniform(0.20, 0.50)
        new_price = round(price * (1 + rise), 2)
        db_query("UPDATE market_assets SET price = ?, last_updated = ? WHERE name = ?",
                 (new_price, time.time(), name))
        text += f"📈 {display}: {price:.2f} - **{new_price:.2f}** (+{rise*100:.1f}%)\n"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['adminhelp'])
@group_only
def adminhelp_command(message):
    if not is_admin(message.from_user.id): return
    bot.reply_to(message,
        "🔧 **Админ-команды:**\n\n"
        "/setprice [актив] [цена] - установить цену\n"
        "/givemoney @юзер [сумма] - выдать деньги\n"
        "/giveitem @юзер [актив] [кол-во] - выдать ресурс\n"
        "/marketcrash - обвал рынка\n"
        "/marketboom - рост рынка\n",
        parse_mode="Markdown"
    )

# ==============================================================
bot.polling(none_stop=True)
            PRIMARY KEY (user_id, unit_name)
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

    military = [
        ('rifle',     '🔫 Винтовки',     2,    100,    'Базовое вооружение пехоты'),
        ('tank',      '🛡️ Танки',        50,   5000,   'Тяжелая бронетехника для прорыва'),
        ('plane',     '✈️ Авиация',      120,  15000,  'Господство в воздухе'),
        ('ship',      '🚢 Эсминцы',      200,  25000,  'Основа военно-морского флота'),
        ('submarine', '🛥️ Подлодки',     150,  20000,  'Скрытые морские удары'),
        ('carrier',   '⛴️ Авианосцы',    1000, 150000, 'Полное господство в океане'),
    ]
    cursor.executemany(
        'INSERT OR IGNORE INTO military_types (name, display_name, steel_cost, money_cost, description) VALUES (?,?,?,?,?)',
        military
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
            "/pay @юзернейм сумма - перевод денег\n"
            "/senditem @юзернейм актив сумма - передача ресурсов\n\n"
            "🏢 Бизнес и Биржа:\n"
            "/shop | /mybiz | /market | /portfolio | /buy | /sell\n\n"
            "⚔️ Военное дело и Флот:\n"
            "/draft - призыв войск (раз в 2 часа)\n"
            "/craft - производство техники и кораблей\n"
            "/army - ваша армия и флот"
        )
    else:
        db_query("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        bot.reply_to(message, "Вы уже зарегистрированы! Используйте /profile.")

@bot.message_handler(commands=['profile'])
@group_only
def profile_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"player_{user_id}"
    db_query("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))

    user = db_query("SELECT balance, level, troops FROM users WHERE user_id = ?", (user_id,), fetchone=True)
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
        f"📈 Уровень экономики: {user[1]}\n"
        f"🪖 Войск в резерве: {user[2]}\n"
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

    bot.reply_to(message, f"💵 Вы собрали налоги: **{earned}** 💰\nБаланс: {new_balance} 💰", parse_mode="Markdown")

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
        bot.reply_to(message, f"✅ Экономика улучшена до {level + 1} уровня за {upgrade_cost} 💰!")
    else:
        bot.reply_to(message, f"❌ Недостаточно средств.\nНужно: {upgrade_cost} 💰\nБаланс: {balance} 💰")

# ==============================================================
# --- ВОЕННОЕ ДЕЛО И ПРОИЗВОДСТВО ---
# ==============================================================

@bot.message_handler(commands=['draft'])
@group_only
def draft_command(message):
    user_id = message.from_user.id
    user = db_query("SELECT troops, last_draft FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        return bot.reply_to(message, "Сначала введите /start")

    troops, last_draft = user
    current_time = time.time()
    cooldown = 7200 # 2 часа

    if current_time - last_draft < cooldown:
        left_time = int(cooldown - (current_time - last_draft))
        bot.reply_to(message, f"⏳ Резервы истощены. Следующий призыв через {left_time // 3600} ч. {(left_time % 3600) // 60} мин.")
        return

    new_recruits = random.randint(1000, 2000)
    db_query("UPDATE users SET troops = troops + ?, last_draft = ? WHERE user_id = ?", (new_recruits, current_time, user_id))

    bot.reply_to(message, f"🪖 **Призыв завершен!**\nВ ряды армии Аурелии вступило **{new_recruits}** новобранцев.\nВсего войск: {troops + new_recruits}", parse_mode="Markdown")

@bot.message_handler(commands=['craft'])
@group_only
def craft_command(message):
    args = message.text.split()
    if len(args) < 3:
        types = db_query("SELECT name, display_name, steel_cost, money_cost FROM military_types")
        text = "⚙️ **Военное и морское производство:**\nИспользование: `/craft [тип] [количество]`\n\n"
        for name, display, steel, money in types:
            text += f"{display} (`{name}`) — {steel} ⚙️ Стали, {money} 💰\n"
        return bot.reply_to(message, text, parse_mode="Markdown")

    unit_name = args[1].lower()
    try:
        qty = int(args[2])
    except ValueError:
        return bot.reply_to(message, "Количество должно быть числом.")
    if qty <= 0:
        return bot.reply_to(message, "Количество должно быть больше нуля.")

    unit = db_query("SELECT display_name, steel_cost, money_cost FROM military_types WHERE name = ?", (unit_name,), fetchone=True)
    if not unit:
        return bot.reply_to(message, f"❌ Чертеж '{unit_name}' не найден.")

    display, steel_cost, money_cost = unit
    total_steel = steel_cost * qty
    total_money = money_cost * qty

    user = db_query("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    user_steel = db_query("SELECT quantity FROM user_portfolio WHERE user_id = ? AND asset_name = 'steel'", (message.from_user.id,), fetchone=True)
    
    current_steel = user_steel[0] if user_steel else 0
    current_money = user[0] if user else 0

    if current_money < total_money or current_steel < total_steel:
        return bot.reply_to(message, f"❌ Недостаточно ресурсов!\nТребуется: {total_steel} ⚙️ Стали и {total_money} 💰\nВ наличии: {current_steel} ⚙️ Стали и {current_money} 💰")

    # Списываем ресурсы
    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_money, message.from_user.id))
    db_query("UPDATE user_portfolio SET quantity = quantity - ? WHERE user_id = ? AND asset_name = 'steel'", (total_steel, message.from_user.id))
    
    # Добавляем технику
    db_query('''
        INSERT INTO user_military (user_id, unit_name, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, unit_name) DO UPDATE SET quantity = quantity + ?
    ''', (message.from_user.id, unit_name, qty, qty))

    bot.reply_to(message, f"🏭 Произведено: **{qty}x {display}**\nПотрачено: {total_steel} ⚙️ Стали, {total_money} 💰", parse_mode="Markdown")

@bot.message_handler(commands=['army'])
@group_only
def army_command(message):
    user = db_query("SELECT troops FROM users WHERE user_id = ?", (message.from_user.id,), fetchone=True)
    units = db_query('''
        SELECT m.display_name, u.quantity 
        FROM user_military u 
        JOIN military_types m ON u.unit_name = m.name 
        WHERE u.user_id = ? AND u.quantity > 0
    ''', (message.from_user.id,))

    if not user:
        return bot.reply_to(message, "Сначала введите /start")

    text = f"⚔️ **Вооруженные силы и Флот:**\n\n🪖 Пехота: {user[0]}\n"
    if units:
        text += "\n**Техника и Корабли:**\n"
        for display, qty in units:
            text += f"{display}: {qty} шт.\n"
    else:
        text += "\nТехника и флот отсутствуют. Постройте их через /craft"

    bot.reply_to(message, text, parse_mode="Markdown")

# ==============================================================
# --- ТОРГОВЛЯ И ПЕРЕВОДЫ ---
# ==============================================================

@bot.message_handler(commands=['pay'])
@group_only
def pay_command(message):
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

    if not target:
        return bot.reply_to(message, f"❌ Игрок @{target_username} не найден.")
    if not sender or sender[0] < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    db_query("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
    db_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target[0]))

    bot.reply_to(message, f"💸 Переведено **{amount}** 💰 игроку @{target_username}.", parse_mode="Markdown")

@bot.message_handler(commands=['senditem'])
@group_only
def senditem_command(message):
    """Команда для прямой торговли ресурсами (сталь, нефть, золото и т.д.)"""
    args = message.text.split()
    if len(args) != 4:
        return bot.reply_to(message, "Использование: `/senditem @юзернейм [актив] [количество]`\nНапример: `/senditem @ivan steel 10`", parse_mode="Markdown")

    target_username = args[1].lstrip('@').lower()
    asset_name = args[2].lower()
    try:
        amount = int(args[3])
    except ValueError:
        return bot.reply_to(message, "Количество должно быть числом.")
    
    if amount <= 0:
        return bot.reply_to(message, "Количество должно быть больше нуля.")

    sender_id = message.from_user.id
    if target_username == (message.from_user.username or "").lower():
        return bot.reply_to(message, "Нельзя отправить ресурсы самому себе.")

    target = db_query("SELECT user_id FROM users WHERE LOWER(username) = ?", (target_username,), fetchone=True)
    if not target:
        return bot.reply_to(message, f"❌ Игрок @{target_username} не найден.")
    target_id = target[0]

    # Проверяем наличие актива у отправителя (на бирже портфеля)
    asset_check = db_query("SELECT display_name FROM market_assets WHERE name = ?", (asset_name,), fetchone=True)
    if not asset_check:
        return bot.reply_to(message, f"❌ Актив '{asset_name}' не существует.")
    display = asset_check[0]

    sender_portfolio = db_query("SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?", (sender_id, asset_name), fetchone=True)
    
    # ИСПРАВЛЕНА ОШИБКА: Python использует оператор 'or' вместо '||'
    if not sender_portfolio or sender_portfolio[0] < amount:
        return bot.reply_to(message, f"❌ У вас недостаточно актива **{display}**.", parse_mode="Markdown")

    # Списываем у отправителя
    new_sender_qty = sender_portfolio[0] - amount
    if new_sender_qty == 0:
        db_query("DELETE FROM user_portfolio WHERE user_id = ? AND asset_name = ?", (sender_id, asset_name))
    else:
        db_query("UPDATE user_portfolio SET quantity = ? WHERE user_id = ? AND asset_name = ?", (new_sender_qty, sender_id, asset_name))

    # Начисляем получателю
    target_portfolio = db_query("SELECT quantity, avg_buy_price FROM user_portfolio WHERE user_id = ? AND asset_name = ?", (target_id, asset_name), fetchone=True)
    if target_portfolio:
        new_avg = ((target_portfolio[0] * target_portfolio[1]) + (amount * sender_portfolio[1])) / (target_portfolio[0] + amount)
        db_query("UPDATE user_portfolio SET quantity = quantity + ?, avg_buy_price = ? WHERE user_id = ? AND asset_name = ?", (amount, new_avg, target_id, asset_name))
    else:
        db_query("INSERT INTO user_portfolio (user_id, asset_name, quantity, avg_buy_price) VALUES (?,?,?,?)", (target_id, asset_name, amount, sender_portfolio[1]))

    bot.reply_to(message, f"📦 Вы успешно передали **{amount}x {display}** игроку @{target_username}.\n💡 *Используйте эту команду вместе с /pay для безопасной торговли.*", parse_mode="Markdown")


# ==============================================================
# --- МАГАЗИН И БИЗНЕСЫ ---
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
