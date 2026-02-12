import os
import time
import yt_dlp
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Render Environment Variable থেকে টোকেন নেবে
BOT_TOKEN = os.getenv("BOT_TOKEN")

def progress_hook(d, context, chat_id, message_id, loop):
    if d["status"] == "downloading":
        current_time = time.time()
        last_update = context.user_data.get("last_update", 0)

        if current_time - last_update > 5:
            percentage = d.get("_percent_str", "0%")
            speed = d.get("_speed_str", "0 KB/s")
            eta = d.get("_eta_str", "0s")

            text = (
                f"📥 **Downloading Video...**\n\n"
                f"📊 Progress: `{percentage}`\n"
                f"⚡ Speed: `{speed}`\n"
                f"⏳ ETA: `{eta}`"
            )

            asyncio.run_coroutine_threadsafe(
                context.bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode="Markdown",
                ),
                loop,
            )
            context.user_data["last_update"] = current_time

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello!\n\nSend me a YouTube link and I will download it for you 🎬")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        return

    status_msg = await update.message.reply_text("🔍 Fetching quality options...")
    ydl_config = {"quiet": True, "no_warnings": True}
    if os.path.exists("cookies.txt"):
        ydl_config["cookiefile"] = "cookies.txt"

    try:
        with yt_dlp.YoutubeDL(ydl_config) as ydl:
            # loop.run_in_executor ব্যবহার করা হয়েছে যাতে মেইন থ্রেড ব্লক না হয়
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            formats = info.get("formats", [])

        keyboard = []
        seen = set()
        for f in formats:
            height = f.get("height")
            if height and height not in seen and f.get("vcodec") != "none" and f.get("acodec") != "none":
                btn_text = f"🎬 {height}p ({f['ext'].upper()})"
                callback_data = f"{f['format_id']}|{url}"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
                seen.add(height)

        if not keyboard:
            await status_msg.edit_text("❌ No downloadable formats found.")
            return

        await status_msg.edit_text("✅ Select Quality:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await status_msg.edit_text(f"❌ Error:\n{str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    format_id, url = query.data.split("|")
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    file_path = f"video_{chat_id}_{int(time.time())}.mp4"
    context.user_data["last_update"] = 0
    loop = asyncio.get_running_loop()

    ydl_opts = {
        "format": f"{format_id}+bestaudio/best",
        "outtmpl": file_path,
        "quiet": True,
        "merge_output_format": "mp4",
        "progress_hooks": [lambda d: progress_hook(d, context, chat_id, message_id, loop)],
    }
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    try:
        await query.edit_message_text("🚀 Starting download...")
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))
        await context.bot.edit_message_text("📤 Uploading to Telegram...", chat_id=chat_id, message_id=message_id)
        
        with open(file_path, "rb") as video_file:
            await context.bot.send_video(chat_id=chat_id, video=video_file, supports_streaming=True, caption="✅ Video Ready!", read_timeout=1000, write_timeout=1000)
        await context.bot.delete_message(chat_id, message_id)
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Failed:\n{str(e)}")
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found in environment variables!")
        return

    # এখানে সরাসরি run_polling ব্যবহার না করে ইভেন্ট লুপ ম্যানেজ করা হয়েছে
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Bot is running on Render...")
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    # এরর এড়াতে মেইন ব্লকটি এভাবে সাজানো হয়েছে
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
