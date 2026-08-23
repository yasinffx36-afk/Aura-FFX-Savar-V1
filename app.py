import os
import threading
import urllib.request
import urllib.parse
import json
import time
import tempfile
import telebot
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!"

TOKEN = '8670679898:AAHKB5MmyveEDc3026ezmFLN7MSXdjYONd8'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Send me a TikTok video link and I will download it for you in HD without watermark + Audio.")

def get_video_caption(title):
    caption = (
        "┏ 📽 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐕𝐈𝐃𝐄𝐎 📽 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        f"📝 𝐓𝐢𝐭𝐥𝐞: {title}\n"
        "🔥 𝐐𝐮𝐚𝐥𝐢𝐭𝐲: HD (No Watermark)\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )
    return caption

def get_audio_caption():
    caption = (
        "┏ 🎵 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐀𝐔𝐃𝐈𝐎 🎵 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        "🎧 Original Soundtrack\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )
    return caption

def download_file(url, filepath):
    import cloudscraper
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url, stream=True)
    response.raise_for_status()
    with open(filepath, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if 'tiktok.com' not in url:
        bot.reply_to(message, "Please send a valid TikTok link.")
        return
        
    msg = bot.reply_to(message, "▒▒▒▒▒▒▒▒▒▒ 0% Loading...")
    
    try:
        time.sleep(0.5)
        bot.edit_message_text("████▒▒▒▒▒▒ 40% Loading...", chat_id=message.chat.id, message_id=msg.message_id)
        
        api_url = "https://www.tikwm.com/api/?url=" + urllib.parse.quote(url) + "&hd=1"
        import cloudscraper
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(api_url)
        data = resp.json()
        
        if data.get('code') != 0:
            bot.edit_message_text(f"Failed to get video. Error: {data.get('msg')}", chat_id=message.chat.id, message_id=msg.message_id)
            return

        time.sleep(0.5)
        bot.edit_message_text("███████▒▒▒ 75% Loading...", chat_id=message.chat.id, message_id=msg.message_id)
        
        video_url = data['data'].get('hdplay') or data['data'].get('play')
        audio_url = data['data'].get('music')
        title = data['data'].get('title', 'TikTok Video')
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_vid:
            vid_filepath = tmp_vid.name
        download_file(video_url, vid_filepath)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_aud:
            aud_filepath = tmp_aud.name
        if audio_url:
            download_file(audio_url, aud_filepath)
            
        time.sleep(0.5)
        bot.edit_message_text("██████████ 100%\n\n💥 𝐁𝐎𝐎𝐌! 💥", chat_id=message.chat.id, message_id=msg.message_id)
        
        with open(vid_filepath, 'rb') as video_file:
            bot.send_video(message.chat.id, video_file, caption=get_video_caption(title))
            
        if audio_url:
            with open(aud_filepath, 'rb') as audio_file:
                performer = "Unknown artist"
                if data.get('data') and data['data'].get('music_info'):
                     performer = data['data']['music_info'].get('author', 'Unknown artist')
                audio_title = "Original Audio"
                bot.send_audio(message.chat.id, audio_file, caption=get_audio_caption(), title=audio_title, performer=performer)
        
        os.remove(vid_filepath)
        if audio_url:
            os.remove(aud_filepath)
            
        bot.delete_message(message.chat.id, msg.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"An error occurred: {str(e)}\nPlease try again later.", chat_id=message.chat.id, message_id=msg.message_id)


def run_bot():
    bot.infinity_polling()

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
