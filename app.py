import os
import threading
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
        "┏ 📽 𝐓𝐢𝐤𝐓𝐨𝐤 𝐕𝐢𝐝𝐞𝐨 📽 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        f"📝 𝐓𝐢𝐭𝐥𝐞: {title}\n"
        "🔥 𝐐𝐮𝐚𝐥𝐢𝐭𝐲: HD (No Watermark)\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )
    return caption

def get_audio_caption():
    caption = (
        "┏ 🎵 𝐓𝐢𝐤𝐓𝐨𝐤 𝐀𝐮𝐝𝐢𝐨 🎵 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        "🎧 Original Soundtrack\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )
    return caption

from telebot.types import InputMediaPhoto
import requests

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if 'tiktok.com' not in url:
        bot.reply_to(message, "Please send a valid TikTok link.")
        return
        
    msg = bot.reply_to(message, "▒▒▒▒▒▒▒▒▒▒ 0% Fetching data...")
    
    try:
        bot.edit_message_text("█████▒▒▒▒▒ 50% Downloading media...", chat_id=message.chat.id, message_id=msg.message_id)
        
        # Use tikwm API via POST to avoid parsing errors
        api_url = "https://www.tikwm.com/api/"
        response = requests.post(
            api_url,
            data={'url': url, 'hd': 1},
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        try:
            res = response.json()
        except ValueError:
            bot.edit_message_text("API Error: Invalid response from server. Please try again later.", chat_id=message.chat.id, message_id=msg.message_id)
            return
            
        if res.get('code') != 0:
            bot.edit_message_text(f"API Error: {res.get('msg', 'Failed to fetch details.')}", chat_id=message.chat.id, message_id=msg.message_id)
            return
            
        data = res.get('data', {})
        title = data.get('title', 'TikTok Video')
        images = data.get('images')
        
        with tempfile.TemporaryDirectory() as tmpdir:
            bot.edit_message_text("██████████ 100%\n\n💥 𝐁𝐎𝐎𝐌! 💥 Uploading to Telegram...", chat_id=message.chat.id, message_id=msg.message_id)
            
            if images and isinstance(images, list):
                # Download images to tmpdir
                media_group = []
                opened_files = [] # To keep file references open until sent
                
                for i, img_url in enumerate(images):
                    img_path = os.path.join(tmpdir, f"img_{i}.jpg")
                    r = requests.get(img_url)
                    with open(img_path, 'wb') as f:
                        f.write(r.content)
                    
                    file_obj = open(img_path, 'rb')
                    opened_files.append(file_obj)
                    
                    if i == 0:
                        media_group.append(InputMediaPhoto(file_obj, caption=get_video_caption(title)))
                    else:
                        media_group.append(InputMediaPhoto(file_obj))
                        
                # Telegram allows max 10 items in a media group
                for i in range(0, len(media_group), 10):
                    bot.send_media_group(message.chat.id, media_group[i:i+10])
                
                for f in opened_files:
                    f.close()
                
                # Audio for images
                audio_url = data.get('music')
                if audio_url:
                    aud_path = os.path.join(tmpdir, "audio.mp3")
                    r = requests.get(audio_url)
                    with open(aud_path, 'wb') as f:
                        f.write(r.content)
                    with open(aud_path, 'rb') as f:
                        bot.send_audio(message.chat.id, f, caption=get_audio_caption(), title="Original Audio", performer="TikTok")
            
            else:
                # It's a Video
                video_url = data.get('hdplay') or data.get('play')
                audio_url = data.get('music')
                
                if video_url:
                    vid_path = os.path.join(tmpdir, "video.mp4")
                    r = requests.get(video_url, stream=True)
                    with open(vid_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    with open(vid_path, 'rb') as f:
                        bot.send_video(message.chat.id, f, caption=get_video_caption(title))
                        
                if audio_url:
                    aud_path = os.path.join(tmpdir, "audio.mp3")
                    r = requests.get(audio_url, stream=True)
                    with open(aud_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    with open(aud_path, 'rb') as f:
                        bot.send_audio(message.chat.id, f, caption=get_audio_caption(), title="Original Audio", performer="TikTok")
                        
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
