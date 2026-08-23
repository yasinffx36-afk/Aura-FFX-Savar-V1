import os
import threading
import tempfile
import telebot
import subprocess
import glob
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

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if 'tiktok.com' not in url:
        bot.reply_to(message, "Please send a valid TikTok link.")
        return
        
    msg = bot.reply_to(message, "▒▒▒▒▒▒▒▒▒▒ 0% Loading...")
    
    try:
        import time
        time.sleep(0.5)
        bot.edit_message_text("████▒▒▒▒▒▒ 40% Downloading Video...", chat_id=message.chat.id, message_id=msg.message_id)
        
        # Use yt-dlp to download video and get title
        with tempfile.TemporaryDirectory() as tmpdir:
            # Download video
            vid_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
            subprocess.run(['yt-dlp', url, '-o', vid_template], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Find the downloaded video file
            downloaded_vids = glob.glob(os.path.join(tmpdir, "*.mp4"))
            if not downloaded_vids:
                bot.edit_message_text("Failed to download video.", chat_id=message.chat.id, message_id=msg.message_id)
                return
            vid_filepath = downloaded_vids[0]
            
            # Extract title from filename (removing the extension)
            filename = os.path.basename(vid_filepath)
            title = os.path.splitext(filename)[0]
            # Remove the ID part [12345] at the end if it exists (yt-dlp sometimes adds it)
            import re
            title = re.sub(r'\s*\[\d+\]$', '', title)
            
            time.sleep(0.5)
            bot.edit_message_text("███████▒▒▒ 75% Downloading Audio...", chat_id=message.chat.id, message_id=msg.message_id)
            
            # Download audio separately
            aud_template = os.path.join(tmpdir, "audio.%(ext)s")
            subprocess.run(['yt-dlp', url, '-f', 'bestaudio', '-o', aud_template], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            downloaded_auds = glob.glob(os.path.join(tmpdir, "audio.*"))
            aud_filepath = downloaded_auds[0] if downloaded_auds else None
            
            time.sleep(0.5)
            bot.edit_message_text("██████████ 100%\n\n💥 𝐁𝐎𝐎𝐌! 💥", chat_id=message.chat.id, message_id=msg.message_id)
            
            with open(vid_filepath, 'rb') as video_file:
                bot.send_video(message.chat.id, video_file, caption=get_video_caption(title))
                
            if aud_filepath:
                with open(aud_filepath, 'rb') as audio_file:
                    bot.send_audio(message.chat.id, audio_file, caption=get_audio_caption(), title="Original Audio", performer="Unknown artist")
            
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
