import os
import csv
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
import pandas as pd
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from pdf_reader import extract_price_list_with_ai


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # keeps console logs clean


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN is missing from your .env file!")

bot = telebot.TeleBot(TOKEN)

# --- DATABASE SETUP ---
DB_NAME = "database.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Suppliers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            filename TEXT,
            updated_at TEXT,
            UNIQUE(user_id, name)
        )
    ''')

    # Products catalog table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER,
            product_name TEXT,
            price REAL,
            gst REAL DEFAULT 0,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE CASCADE
        )
    ''')

    # Orders history tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT,
            total_amount REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            product_name TEXT,
            quantity INTEGER,
            supplier_name TEXT,
            unit_price REAL,
            subtotal REAL,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()


init_db()


# --- PERSISTENT REPLY KEYBOARD (BOXY MENU) ---
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("📊 Compare Prices"),
        KeyboardButton("🔍 Search Product"),
        KeyboardButton("🛒 Generate Order"),
        KeyboardButton("📜 Order History"),
        KeyboardButton("📂 View Suppliers"),
        KeyboardButton("📁 Export CSV"),
        KeyboardButton("🗑️ Clear My Data")
    )
    return markup


def get_saved_catalogs(user_id):
    """Fetch catalogs strictly isolated to the specific user_id."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM suppliers WHERE user_id = ?", (user_id,))
    suppliers = cursor.fetchall()

    catalogs = {}
    for sup_id, sup_name in suppliers:
        cursor.execute("SELECT product_name, price FROM products WHERE supplier_id = ?", (sup_id,))
        items = cursor.fetchall()
        catalogs[sup_name] = {prod: price for prod, price in items}

    conn.close()
    return catalogs


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "👋 **Welcome to PriceSync Bot!**\n\n"
        "1. Send your supplier price lists (**PDF, XLSX, or CSV**).\n"
        "2. Your files are private and securely isolated to your account.\n"
        "3. Use the buttons below to compare, search, generate orders, or check history!"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())


# --- PERSISTENT MENU BUTTON ROUTING ---
@bot.message_handler(func=lambda message: message.text in [
    "📊 Compare Prices", "🔍 Search Product", "🛒 Generate Order",
    "📜 Order History", "📂 View Suppliers", "📁 Export CSV", "🗑️ Clear My Data"
])
def handle_persistent_menu(message):
    if message.text == "📊 Compare Prices":
        compare_prices(message)
    elif message.text == "🔍 Search Product":
        sent_msg = bot.reply_to(message, "🔍 Please enter the product name you want to search for:")
        bot.register_next_step_handler(sent_msg, execute_search)
    elif message.text == "🛒 Generate Order":
        sent_msg = bot.reply_to(
            message,
            "🛒 **Order Generator**\n\n"
            "Please send the items and quantities you need in this format:\n"
            "`product name: quantity, product name: quantity`\n\n"
            "*Example:* `ryzen 5: 2, rtx 4060: 4`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(sent_msg, process_order_generation)
    elif message.text == "📜 Order History":
        show_order_history(message)
    elif message.text == "📂 View Suppliers":
        show_suppliers_menu(message)
    elif message.text == "📁 Export CSV":
        export_comparison_csv(message)
    elif message.text == "🗑️ Clear My Data":
        ask_clear_account_data(message)


# --- ACCOUNT DATA DELETION ---
def ask_clear_account_data(message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM suppliers WHERE user_id = ?", (user_id,))
    sup_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
    ord_count = cursor.fetchone()[0]
    conn.close()

    if sup_count == 0 and ord_count == 0:
        bot.reply_to(
            message,
            "ℹ️ Your account already has no saved suppliers, products, or orders.",
            reply_markup=get_main_keyboard()
        )
        return

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚠️ Yes, Delete All My Data", callback_data="confirm_clear_data"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_clear_data")
    )

    warning_text = (
        "⚠️ **Delete Account Data?**\n\n"
        f"This will permanently remove your **{sup_count}** supplier catalog(s) (and their products) "
        f"and **{ord_count}** order record(s) from your account.\n"
        "Other users' data will not be affected."
    )
    bot.reply_to(message, warning_text, parse_mode="Markdown", reply_markup=markup)


def delete_user_account_data(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute(
        "DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id = ?)",
        (user_id,)
    )
    cursor.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))

    cursor.execute(
        "DELETE FROM products WHERE supplier_id IN (SELECT id FROM suppliers WHERE user_id = ?)",
        (user_id,)
    )
    cursor.execute("DELETE FROM suppliers WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()


# --- STEP 3: ORDER GENERATOR ENGINE ---
def process_order_generation(message):
    user_id = message.from_user.id
    raw_input = message.text.strip()

    if raw_input.startswith('/'):
        return

    SAVED_CATALOGS = get_saved_catalogs(user_id)
    if not SAVED_CATALOGS:
        bot.reply_to(message, "⚠️ No supplier catalogs found in your account. Upload some price lists first!", reply_markup=get_main_keyboard())
        return

    items_to_buy = []
    try:
        parts = raw_input.split(',')
        for part in parts:
            if ':' not in part:
                continue
            prod_name_raw, qty_raw = part.split(':')
            prod_name = prod_name_raw.strip().lower()
            qty = int(qty_raw.strip())
            if qty > 0:
                items_to_buy.append((prod_name, qty))
    except Exception:
        bot.reply_to(message, "⚠️ Invalid format. Please use: `item name: quantity, item name: quantity`", parse_mode="Markdown", reply_markup=get_main_keyboard())
        return

    if not items_to_buy:
        bot.reply_to(message, "⚠️ No valid items or quantities detected. Try again using the button menu.", reply_markup=get_main_keyboard())
        return

    supplier_orders = {}
    grand_total = 0.0
    unmatched_items = []

    for prod_query, qty in items_to_buy:
        best_match = None
        best_supplier = None
        lowest_price = float('inf')

        for supplier, catalog in SAVED_CATALOGS.items():
            for prod_name, price in catalog.items():
                if prod_query in prod_name:
                    if price < lowest_price:
                        lowest_price = price
                        best_supplier = supplier
                        best_match = prod_name

        if best_match and best_supplier:
            subtotal = lowest_price * qty
            grand_total += subtotal
            if best_supplier not in supplier_orders:
                supplier_orders[best_supplier] = []
            supplier_orders[best_supplier].append((best_match, qty, lowest_price, subtotal))
        else:
            unmatched_items.append(prod_query)

    if not supplier_orders:
        bot.reply_to(message, "❌ None of the requested items were found in your supplier catalogs.", reply_markup=get_main_keyboard())
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("INSERT INTO orders (user_id, created_at, total_amount) VALUES (?, ?, ?)",
                   (user_id, timestamp, grand_total))
    order_id = cursor.lastrowid

    for supplier, entries in supplier_orders.items():
        for prod_name, qty, unit_price, subtotal in entries:
            cursor.execute('''
                INSERT INTO order_items (order_id, product_name, quantity, supplier_name, unit_price, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (order_id, prod_name, qty, supplier, unit_price, subtotal))

    conn.commit()
    conn.close()

    report = f"🛒 **Generated Purchase Order**\n📅 {timestamp}\n\n"

    for supplier, entries in supplier_orders.items():
        report += f"🏢 **Supplier: {supplier}**\n"
        sup_total = 0
        for prod_name, qty, unit_price, subtotal in entries:
            sup_total += subtotal
            report += f"   • {prod_name.title()} x {qty} @ ₹{unit_price} = ₹{subtotal}\n"
        report += f"   🔹 *Supplier Subtotal: ₹{sup_total:.2f}*\n\n"

    report += f"💰 **Grand Total: ₹{grand_total:.2f}**\n"

    if unmatched_items:
        report += f"\n⚠️ *Unmatched items skipped:* {', '.join(unmatched_items)}"

    if len(report) > 4000:
        report = report[:4000] + "\n\n*(Truncated)*"

    bot.reply_to(message, report, parse_mode="Markdown", reply_markup=get_main_keyboard())


# --- ORDER HISTORY VIEW ---
def show_order_history(message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, created_at, total_amount FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        bot.reply_to(message, "📜 You have no saved order history yet.", reply_markup=get_main_keyboard())
        return

    text = "📜 **Your Recent Purchase Orders:**\n\n"
    for order_id, created_at, total in orders:
        text += f"🆔 **Order #{order_id}** — {created_at}\n   💰 Total: **₹{total:.2f}**\n\n"

    bot.reply_to(message, text, parse_mode="Markdown", reply_markup=get_main_keyboard())


# --- SUPPLIER MANAGEMENT MENU (INLINE) ---
def show_suppliers_menu(message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, filename FROM suppliers WHERE user_id = ?", (user_id,))
    suppliers = cursor.fetchall()
    conn.close()

    markup = InlineKeyboardMarkup()
    markup.row_width = 1

    if suppliers:
        markup.add(InlineKeyboardButton("🔄 Update / Replace Supplier File", callback_data="menu_update"))
        markup.add(InlineKeyboardButton("🗑️ Delete a Supplier", callback_data="menu_delete"))
        markup.add(InlineKeyboardButton("📁 View Loaded Files Details", callback_data="menu_list"))
    else:
        markup.add(InlineKeyboardButton("📥 No Catalogs Loaded (Upload a file)", callback_data="btn_noop"))

    bot.reply_to(message, "🎛️ **Your Supplier Management Options:**", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    user_id = call.from_user.id

    if call.data == "confirm_clear_data":
        delete_user_account_data(user_id)
        bot.answer_callback_query(call.id, "All your account data has been deleted.")
        bot.edit_message_text(
            "🗑️ **All data for your account has been deleted** (suppliers, products, and order history).",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        return

    if call.data == "cancel_clear_data":
        bot.answer_callback_query(call.id, "Deletion cancelled.")
        bot.edit_message_text(
            "✅ Cancelled. Your account data is safe.",
            call.message.chat.id,
            call.message.message_id
        )
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if call.data == "menu_list":
        cursor.execute("SELECT name, filename, updated_at FROM suppliers WHERE user_id = ?", (user_id,))
        suppliers = cursor.fetchall()
        if not suppliers:
            bot.answer_callback_query(call.id, "No suppliers found in your account.")
            conn.close()
            return

        text = "📁 **Your Active Suppliers & Source Files:**\n\n"
        for name, filename, updated in suppliers:
            text += f"🏢 **{name}**\n   • File: `{filename}`\n   • Updated: {updated}\n\n"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    elif call.data == "menu_delete":
        cursor.execute("SELECT id, name, filename FROM suppliers WHERE user_id = ?", (user_id,))
        suppliers = cursor.fetchall()
        if not suppliers:
            bot.answer_callback_query(call.id, "No suppliers to delete.")
            conn.close()
            return

        markup = InlineKeyboardMarkup()
        for sup_id, name, filename in suppliers:
            markup.add(InlineKeyboardButton(f"❌ Delete {name} ({filename})", callback_data=f"del_{sup_id}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="menu_back"))

        bot.edit_message_text("🗑️ Select a supplier to remove from your account:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("del_"):
        sup_id = call.data.split("_")[1]
        cursor.execute("DELETE FROM suppliers WHERE id = ? AND user_id = ?", (sup_id, user_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Supplier deleted successfully!")
        bot.edit_message_text("✅ Supplier catalog deleted from your database.", call.message.chat.id, call.message.message_id)
        return

    elif call.data == "menu_update":
        cursor.execute("SELECT id, name, filename FROM suppliers WHERE user_id = ?", (user_id,))
        suppliers = cursor.fetchall()
        if not suppliers:
            bot.answer_callback_query(call.id, "No suppliers available to update.")
            conn.close()
            return

        markup = InlineKeyboardMarkup()
        for sup_id, name, filename in suppliers:
            markup.add(InlineKeyboardButton(f"🔄 Update {name} (Current: {filename})", callback_data=f"upd_{sup_id}"))
        markup.add(InlineKeyboardButton("🔙 Back", callback_data="menu_back"))

        bot.edit_message_text("🔄 Select which supplier file you want to update/replace:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("upd_"):
        sup_id = call.data.split("_")[1]
        cursor.execute("SELECT name FROM suppliers WHERE id = ? AND user_id = ?", (sup_id, user_id))
        res = cursor.fetchone()
        conn.close()

        if res:
            sup_name = res[0]
            sent_msg = bot.edit_message_text(f"📥 Please upload the **new file (PDF, XLSX, or CSV)** update for **{sup_name}**:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            bot.register_next_step_handler(sent_msg, process_supplier_update, sup_name)
        return

    elif call.data == "menu_back":
        conn.close()
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return

    conn.close()


def process_supplier_update(message, target_supplier_name):
    if not message.document:
        bot.reply_to(message, "⚠️ Please upload a valid document file.")
        return
    handle_uploaded_file(message, override_supplier=target_supplier_name)


# --- MULTI-FORMAT FILE INGESTION (PDF, XLSX, CSV) ---
@bot.message_handler(content_types=['document'])
def handle_document(message):
    handle_uploaded_file(message)


def handle_uploaded_file(message, override_supplier=None):
    try:
        user_id = message.from_user.id
        file_info = bot.get_file(message.document.file_id)
        filename = message.document.file_name.lower()

        bot.reply_to(message, "📥 Downloading and parsing file data for your account...")

        downloaded_file = bot.download_file(file_info.file_path)
        os.makedirs("files/input", exist_ok=True)
        local_path = f"files/input/{message.document.file_name}"

        with open(local_path, "wb") as f:
            f.write(downloaded_file)

        products = {}
        if filename.endswith('.xlsx'):
            df = pd.read_excel(local_path)
            products = parse_dataframe(df)
        elif filename.endswith('.csv'):
            df = pd.read_csv(local_path)
            products = parse_dataframe(df)
        elif filename.endswith('.pdf'):
            products = extract_price_list_with_ai(local_path)
        else:
            bot.reply_to(message, "⚠️ Unsupported file format. Please upload PDF, XLSX, or CSV.")
            return

        if not products:
            bot.reply_to(message, "❌ Couldn't extract any products from this file.")
            return

        company_name = override_supplier if override_supplier else message.document.file_name.split('_')[0].upper()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM suppliers WHERE user_id = ? AND name = ?", (user_id, company_name))
        row = cursor.fetchone()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        if row:
            sup_id = row[0]
            cursor.execute("UPDATE suppliers SET filename = ?, updated_at = ? WHERE id = ?",
                           (message.document.file_name, timestamp, sup_id))
            cursor.execute("DELETE FROM products WHERE supplier_id = ?", (sup_id,))
        else:
            cursor.execute("INSERT INTO suppliers (user_id, name, filename, updated_at) VALUES (?, ?, ?, ?)",
                           (user_id, company_name, message.document.file_name, timestamp))
            sup_id = cursor.lastrowid

        for prod_name, price in products.items():
            cursor.execute("INSERT INTO products (supplier_id, product_name, price) VALUES (?, ?, ?)",
                           (sup_id, prod_name, price))

        conn.commit()
        conn.close()

        response_text = f"✅ **Saved catalog for [{company_name}]** ({len(products)} products loaded).\n\nUse the bottom menu buttons to search or compare!"
        bot.reply_to(message, response_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred: {e}")


def parse_dataframe(df):
    df.columns = [str(col).strip().lower() for col in df.columns]
    prod_col = next((col for col in df.columns if 'product' in col or 'item' in col or 'name' in col), df.columns[0])
    price_col = next((col for col in df.columns if 'price' in col or 'rate' in col or 'cost' in col), df.columns[1])

    products = {}
    for _, row in df.iterrows():
        name = str(row[prod_col]).strip().lower()
        try:
            price = float(row[price_col])
            if name and name != 'nan':
                products[name] = price
        except ValueError:
            continue
    return products


# --- SEARCH, COMPARE & EXPORT ---
@bot.message_handler(commands=['search', 'find'])
def search_prompt(message):
    raw_text = message.text.strip()
    if raw_text.startswith('/'):
        parts = raw_text.split(maxsplit=1)
        query = parts[1].strip().lower() if len(parts) > 1 else ""
    else:
        query = raw_text.lower()

    if not query:
        sent_msg = bot.reply_to(message, "🔍 Please enter the product name you want to search for:")
        bot.register_next_step_handler(sent_msg, execute_search)
        return

    run_search_logic(message, query)


def execute_search(message):
    query = message.text.strip().lower()
    if not query:
        bot.reply_to(message, "⚠️ Search cancelled.")
        return
    run_search_logic(message, query)


def run_search_logic(message, query):
    user_id = message.from_user.id
    SAVED_CATALOGS = get_saved_catalogs(user_id)
    if not SAVED_CATALOGS:
        bot.reply_to(message, "⚠️ No supplier catalogs loaded in your account yet. Upload a file first!", reply_markup=get_main_keyboard())
        return

    all_products = set()
    for catalog in SAVED_CATALOGS.values():
        for prod_name in catalog.keys():
            if query in prod_name:
                all_products.add(prod_name)

    if not all_products:
        bot.reply_to(message, f"❌ No products found matching **'{query}'**.", parse_mode="Markdown", reply_markup=get_main_keyboard())
        return

    response_text = f"🔍 **Search Results for '{query}':**\n\n"

    for product in sorted(all_products):
        prices = {}
        for supplier, catalog in SAVED_CATALOGS.items():
            if product in catalog:
                prices[supplier] = catalog[product]

        if prices:
            cheapest_supplier = min(prices, key=prices.get)
            response_text += f"🔹 **{product.title()}**\n"
            for supplier, price in prices.items():
                if supplier == cheapest_supplier:
                    response_text += f"   • {supplier}: **₹{price}** 🟢 (Lowest)\n"
                else:
                    response_text += f"   • {supplier}: ₹{price}\n"
            response_text += "\n"

    bot.reply_to(message, response_text, parse_mode="Markdown", reply_markup=get_main_keyboard())


@bot.message_handler(commands=['compare'])
def compare_prices(message):
    user_id = message.from_user.id
    SAVED_CATALOGS = get_saved_catalogs(user_id)
    if len(SAVED_CATALOGS) < 2:
        bot.reply_to(message, f"⚠️ You have uploaded {len(SAVED_CATALOGS)} catalog(s). Please upload at least 2 files first to compare prices.", reply_markup=get_main_keyboard())
        return

    bot.reply_to(message, "🔍 Analyzing and comparing prices across your suppliers...")

    supplier_names = list(SAVED_CATALOGS.keys())
    all_products = set()
    for catalog in SAVED_CATALOGS.values():
        all_products.update(catalog.keys())

    comparison_text = f"📊 **Price Comparison Report** ({len(supplier_names)} Suppliers)\n\n"

    matched_count = 0
    for product in sorted(all_products):
        prices = {}
        for supplier in supplier_names:
            if product in SAVED_CATALOGS[supplier]:
                prices[supplier] = SAVED_CATALOGS[supplier][product]

        if len(prices) > 1:
            matched_count += 1
            cheapest_supplier = min(prices, key=prices.get)

            comparison_text += f"🔹 **{product.title()}**\n"
            for supplier, price in prices.items():
                if supplier == cheapest_supplier:
                    comparison_text += f"   • {supplier}: **₹{price}** 🟢 (Lowest)\n"
                else:
                    comparison_text += f"   • {supplier}: ₹{price}\n"
            comparison_text += "\n"

    if matched_count == 0:
        comparison_text += "⚠️ No exact matching product names found across your uploaded suppliers yet."

    if len(comparison_text) > 4000:
        comparison_text = comparison_text[:4000] + "\n\n*(Truncated due to length)*"

    bot.reply_to(message, comparison_text, parse_mode="Markdown", reply_markup=get_main_keyboard())


@bot.message_handler(commands=['export'])
def export_comparison_csv(message):
    user_id = message.from_user.id
    SAVED_CATALOGS = get_saved_catalogs(user_id)
    if len(SAVED_CATALOGS) < 2:
        bot.reply_to(message, f"⚠️ You have uploaded {len(SAVED_CATALOGS)} catalog(s). Please upload at least 2 files first to export.", reply_markup=get_main_keyboard())
        return

    bot.reply_to(message, "📊 Generating your comparison spreadsheet...")

    supplier_names = list(SAVED_CATALOGS.keys())
    all_products = set()
    for catalog in SAVED_CATALOGS.values():
        all_products.update(catalog.keys())

    os.makedirs("files/output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"files/output/price_comparison_{user_id}_{timestamp}.csv"

    try:
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            header = ["Product Name"] + supplier_names + ["Lowest Price", "Best Supplier"]
            writer.writerow(header)

            for product in sorted(all_products):
                prices = {}
                for supplier in supplier_names:
                    if product in SAVED_CATALOGS[supplier]:
                        prices[supplier] = SAVED_CATALOGS[supplier][product]

                if len(prices) > 1:
                    cheapest_supplier = min(prices, key=prices.get)
                    lowest_price = prices[cheapest_supplier]

                    row = [product]
                    for supplier in supplier_names:
                        row.append(prices.get(supplier, "N/A"))
                    row.append(lowest_price)
                    row.append(cheapest_supplier)

                    writer.writerow(row)

        with open(csv_filename, 'rb') as doc:
            bot.send_document(
                message.chat.id,
                doc,
                caption="📁 Here is your multi-supplier price comparison report!",
                reply_markup=get_main_keyboard()
            )

    except Exception as e:
        bot.reply_to(message, f"❌ Error generating export: {e}")


if __name__ == "__main__":
    start_health_server()
    print("🤖 PriceSync Bot is running successfully...")
    bot.infinity_polling(skip_pending=True)