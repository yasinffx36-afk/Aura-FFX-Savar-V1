import telebot
from flask import Flask
import threading
import os
import yt_dlp
import requests

TOKEN = '8670679898:AAHKB5MmyveEDc3026ezmFLN7MSXdjYONd8'
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

@app.route('/')
def home():
    return "AURA FFX Telegram Bot is Running!"

def run_server():
    port = int(os.environ.get('PORT', 10000))
    # Run the dummy server to satisfy Render's port binding requirement
    app.run(host='0.0.0.0', port=port)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 Welcome to ꧁𓊈𒆜 𝐀𝐔𝐑𝐀 𝐅𝐅𝐗 𒆜𓊉꧂ Media Downloader Bot!\n\n"
        "Send me a link from **Facebook, Instagram, or TikTok**, "
        "and I will download the video/picture for you."
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    if not url.startswith('http'):
        bot.reply_to(message, "⚠️ Please send a valid URL (starting with http:// or https://).")
        return

    msg = bot.reply_to(message, "⏳ Processing your link... Please wait.")

    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'quiet': True,
        'outtmpl': '%(id)s.%(ext)s',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First try without downloading to send URL directly
            info = ydl.extract_info(url, download=False)
            
            video_url = info.get('url')
            title = info.get('title', 'AURA FFX Media')
            
            if not video_url:
                bot.edit_message_text("❌ Could not extract media link.", chat_id=message.chat.id, message_id=msg.message_id)
                return
                
            bot.edit_message_text("🚀 Sending media...", chat_id=message.chat.id, message_id=msg.message_id)
            
            try:
                # Try sending directly via URL (Telegram handles up to 50MB usually)
                bot.send_video(message.chat.id, video_url, caption=title)
                bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
            except Exception as e:
                print(f"Direct send failed: {e}")
                bot.edit_message_text("⏳ Direct send failed, downloading to server temporarily...", chat_id=message.chat.id, message_id=msg.message_id)
                
                # Fallback: Download the file and then send it
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                try:
                    with open(filename, 'rb') as video:
                        bot.send_video(message.chat.id, video, caption=title)
                    bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
                finally:
                    # Cleanup the file after sending
                    if os.path.exists(filename):
                        os.remove(filename)

    except Exception as e:
        bot.edit_message_text(f"❌ Failed to fetch media. Error: {str(e)}", chat_id=message.chat.id, message_id=msg.message_id)

if __name__ == "__main__":
    # 1. Start the Flask server in a separate thread
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    # 2. Start the bot polling
    print("Bot is starting...")
    bot.infinity_polling()
