import os
import json
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# === Yuklashlar ===
load_dotenv()
TOKEN = os.getenv("TOKEN")
DOWNLOAD_DIR = "downloads"
DATA_FILE = "data.json"

if not TOKEN:
    raise ValueError("❌ .env faylda TOKEN aniqlanmagan!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === JSON funksiyalar ===
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"manhwa": []}
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load_data()
upload_state = {}
addname_state = {}

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Botga xush kelibsiz!\n\n"
        "🆕 Manhwa yaratish: /addname <id> <nom>"
    )

# === /addname ===
async def addname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("❗ Foydalanish: /addname <id> <nom>")
    manhwa_id = context.args[0]
    title = " ".join(context.args[1:])
    addname_state[update.effective_user.id] = {
        "id": manhwa_id,
        "title": title,
        "step": "cover"
    }
    await update.message.reply_text("🖼 Rasm (cover) yuboring...")

# === addname davom ettirish ===
async def handle_addname_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in addname_state:
        return
    state = addname_state[user_id]
    msg = update.message

    if state["step"] == "cover":
        if not msg.photo:
            return await msg.reply_text("❗ Iltimos, rasm yuboring.")
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        photo = msg.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        filename = f"{state['id']}-cover.jpg"
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        await file.download_to_drive(filepath)
        state["cover"] = f"{DOWNLOAD_DIR}/{filename}"
        state["step"] = "genre"
        return await msg.reply_text("🎭 Janrini kiriting...")

    elif state["step"] == "genre":
        state["genre"] = msg.text
        state["step"] = "author"
        return await msg.reply_text("✍️ Muallif ismini kiriting...")

    elif state["step"] == "author":
        state["author"] = msg.text
        state["step"] = "desc"
        return await msg.reply_text("ℹ️ Manhwa haqida qisqacha ma'lumot yozing...")

    elif state["step"] == "desc":
        state["description"] = msg.text
        state["parts"] = []
        data["manhwa"].append(state)
        save_data(data)
        addname_state.pop(user_id)
        return await msg.reply_text("✅ Manhwa qo‘shildi! Endi qismlarni qo‘shish uchun: /addpart <id>")

# === /addpart ===
async def addpart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        return await update.message.reply_text("❗ Foydalanish: /addpart <id>")
    manhwa_id = context.args[0]
    upload_state[update.effective_user.id] = manhwa_id
    await update.message.reply_text("📤 Endi ketma-ket PDF fayllarni yuboring...")

# === PDF qabul qilish ===
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    manhwa_id = upload_state.get(user_id)
    if not manhwa_id:
        return await update.message.reply_text("❗ Avval /addpart <id> buyrug‘ini yuboring.")

    document = update.message.document
    if not document.mime_type.startswith("application/pdf"):
        return await update.message.reply_text("❌ Faqat PDF fayl qabul qilinadi.")

    if document.file_size > 50 * 1024 * 1024:
        return await update.message.reply_text("❌ Fayl hajmi 50MB dan katta, uni bo‘lib yuboring.")

    existing = next((m for m in data["manhwa"] if m["id"] == manhwa_id), None)
    if not existing:
        return await update.message.reply_text("❌ Manhwa topilmadi.")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file = await context.bot.get_file(document.file_id)

    # === Avtomatik bob nomini topish ===
    existing_parts = existing.get("parts", [])
    existing_titles = [p["title"] for p in existing_parts]
    max_bob = 0
    for title in existing_titles:
        if title.lower().startswith("0-bob"):
            max_bob = max(max_bob, 0)
        elif title.lower().startswith("1-bob"):
            max_bob = max(max_bob, 1)
        else:
            try:
                num = int(title.split("-")[0])
                max_bob = max(max_bob, num)
            except:
                continue
    new_bob = max_bob + 1

    filename = f"{manhwa_id}-{new_bob}.pdf"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    await file.download_to_drive(filepath)

    existing["parts"].append({
        "title": f"{new_bob}-bob",
        "file": f"{DOWNLOAD_DIR}/{filename}"
    })

    save_data(data)
    await update.message.reply_text(
        f"✅ {new_bob}-bob saqlandi.\n"
        f"📖 Ko‘rish: read.html?id={manhwa_id}&n={new_bob-1}"
    )

# === /list ===
async def list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not data["manhwa"]:
        return await update.message.reply_text("❌ Hech qanday manhwa topilmadi.")
    buttons = [
        [InlineKeyboardButton(m["title"], callback_data=f"show|{m['id']}")]
        for m in data["manhwa"]
    ]
    await update.message.reply_text("📚 Manhwa ro‘yxati:", reply_markup=InlineKeyboardMarkup(buttons))

# === Tugma bosilganda ===
async def show_manhwa_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, manhwa_id = query.data.split("|", 1)
    manhwa = next((m for m in data["manhwa"] if m["id"] == manhwa_id), None)
    if not manhwa:
        return await query.edit_message_text("❌ Manhwa topilmadi.")
    text = (
        f"📌 <b>{manhwa['title']}</b>\n"
        f"🎭 <b>Janr:</b> {manhwa.get('genre', 'Noma’lum')}\n"
        f"✍️ <b>Muallif:</b> {manhwa.get('author', 'Noma’lum')}\n"
        f"🆔 <code>{manhwa['id']}</code>\n"
        f"📚 <b>Boblar:</b> {len(manhwa.get('parts', []))}\n"
        f"📝 <i>{manhwa.get('description', '')}</i>"
    )
    await query.edit_message_text(text, parse_mode="HTML")

# === Botni ishga tushurish ===
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addname", addname))
    app.add_handler(CommandHandler("addpart", addpart))
    app.add_handler(CommandHandler("list", list_handler))
    app.add_handler(CallbackQueryHandler(show_manhwa_info, pattern=r"^show\|"))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_addname_steps))
    app.add_handler(MessageHandler(filters.PHOTO, handle_addname_steps))
    logger.info("✅ Bot ishga tushdi.")
    app.run_polling()

if __name__ == "__main__":
    main()
