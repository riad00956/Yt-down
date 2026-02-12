import os
import time
import yt_dlp
import asyncio
import threading
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- FLASK SERVER ---
server = Flask(__name__)

@server.route('/')
def ping():
    return "Bot is running!", 200

def run_flask():
    # Render ডিফল্টভাবে পোর্ট ১০০০০ ব্যবহার করে
    port = int(os.environ.get("PORT", 10000))
    server.run(host='0.0.0.0', port=port)

# --- BOT LOGIC ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

def progress_hook(d, context, chat_id, message_id, loop):
    if d["status"] == "downloading":
        current_time = time.time()
        last_update = context.user_data.get("last_update", 0)
        if current_time - last_update > 5:
            percentage = d.get("_percent_str", "0%")
            speed = d.get("_speed_str", "0 KB/s")
            text = f"📥 **Downloading...**\n📊 Progress: `{percentage}`\n⚡ Speed: `{speed}`"
            asyncio.run_coroutine_threadsafe(
                context.bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown"),
                loop
            )
            context.user_data["last_update"] = current_time

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 লিঙ্ক দিন, আমি ডাউনলোড করে দিচ্ছি!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"): return
    status_msg = await update.message.reply_text("🔍 ফরম্যাট চেক করছি...")
    
    ydl_opts = {"quiet": True, "no_warnings": True}
    if os.path.exists("cookies.txt"): ydl_opts["cookiefile"] = "cookies.txt"

    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            formats = info.get("formats", [])
        
        keyboard = []
        seen = set()
        for f in formats:
            h = f.get("height")
            if h and h not in seen and f.get("vcodec") != "none" and f.get("acodec") != "none":
                keyboard.append([InlineKeyboardButton(f"🎬 {h}p", callback_data=f"{f['format_id']}|{url}")])
                seen.add(h)
        await status_msg.edit_text("✅ কোয়ালিটি বেছে নিন:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await status_msg.edit_text(f"❌ ভুল হয়েছে: {str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    f_id, url = query.data.split("|")
    chat_id, msg_id = query.message.chat_id, query.message.message_id
    file_path = f"vid_{int(time.time())}.mp4"
    loop = asyncio.get_running_loop()

    ydl_opts = {
        "format": f"{f_id}+bestaudio/best",
        "outtmpl": file_path,
        "merge_output_format": "mp4",
        "progress_hooks": [lambda d: progress_hook(d, context, chat_id, msg_id, loop)],
    }
    if os.path.exists("cookies.txt"): ydl_opts["cookiefile"] = "cookies.txt"

    try:
        await query.edit_message_text("🚀 ডাউনলোড শুরু হয়েছে...")
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))
        await context.bot.edit_message_text("📤 আপলোড হচ্ছে...", chat_id=chat_id, message_id=msg_id)
        with open(file_path, "rb") as vf:
            await context.bot.send_video(chat_id=chat_id, video=vf, caption="✅ ডান!", read_timeout=1000)
        await context.bot.delete_message(chat_id, msg_id)
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ ফেইলড: {str(e)}")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    async with app:
        await app.initialize()
        await app.updater.start_polling(drop_pending_updates=True)
        await app.start()
        print("🤖 Bot is running with Flask...")
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN missing!")
    else:
        # Flask সার্ভারকে আলাদা থ্রেডে চালানো
        threading.Thread(target=run_flask, daemon=True).start()
        
        # বট চালানো
        try:
            asyncio.run(run_bot())
        except (KeyboardInterrupt, SystemExit):
            pass
