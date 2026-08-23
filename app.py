"""
Aura TikTok Downloader Bot — Advanced Version
==============================================
Features:
  - TikWM API for ultra-fast downloads (no yt-dlp subprocess needed)
  - Slideshow / Photo Carousel support (downloads all images)
  - HD Video without watermark + Original Audio
  - yt-dlp fallback if TikWM fails
  - Concurrent image downloads with ThreadPoolExecutor
  - Real-time progress bar
  - Health check endpoint for Render
"""

import os
import re
import threading
import tempfile
import subprocess
import glob
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import requests
import telebot
from telebot.types import InputMediaPhoto
from flask import Flask

# ─── Configuration ───────────────────────────────────────────────────────────

TOKEN = os.environ.get(
    "BOT_TOKEN",
    "8670679898:AAHKB5MmyveEDc3026ezmFLN7MSXdjYONd8",
)
PORT = int(os.environ.get("PORT", 5000))

# TikWM API endpoints (primary + fallback)
TIKWM_ENDPOINTS = [
    "https://www.tikwm.com/api/",
    "https://tikwm.com/api/",
]

# Telegram limits
TELEGRAM_PHOTO_ALBUM_LIMIT = 10  # max 10 media in one album

# Reusable HTTP session with connection pooling
http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
})
adapter = requests.adapters.HTTPAdapter(
    pool_connections=20,
    pool_maxsize=20,
    max_retries=requests.adapters.Retry(total=2, backoff_factor=0.3),
)
http_session.mount("https://", adapter)
http_session.mount("http://", adapter)

# Thread pool for concurrent downloads
download_pool = ThreadPoolExecutor(max_workers=10)

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("aura_bot")

# ─── Flask & Bot ─────────────────────────────────────────────────────────────

app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)


@app.route("/")
def health_check():
    return "Bot is running!"


# ─── Caption Helpers ─────────────────────────────────────────────────────────

def video_caption(title):
    return (
        "┏ 📽 𝐓𝐢𝐤𝐓𝐨𝐤 𝐕𝐢𝐝𝐞𝐨 📽 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        f"📝 𝐓𝐢𝐭𝐥𝐞: {title}\n"
        "🔥 𝐐𝐮𝐚𝐥𝐢𝐭𝐲: HD (No Watermark)\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )


def audio_caption():
    return (
        "┏ 🎵 𝐓𝐢𝐤𝐓𝐨𝐤 𝐀𝐮𝐝𝐢𝐨 🎵 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        "🎧 Original Soundtrack\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )


def slideshow_caption(title, count):
    return (
        "┏ 🖼 𝐓𝐢𝐤𝐓𝐨𝐤 𝐒𝐥𝐢𝐝𝐞𝐬𝐡𝐨𝐰 🖼 ┓\n"
        "┗━━━━━━━━━━━━━━━━━━┛\n\n"
        f"📝 𝐓𝐢𝐭𝐥𝐞: {title}\n"
        f"📸 𝐏𝐡𝐨𝐭𝐨𝐬: {count}\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )


# ─── TikWM API ──────────────────────────────────────────────────────────────

def fetch_tikwm(url):
    """
    Call TikWM API to get video/slideshow data.
    Tries multiple endpoints for reliability.
    Returns the 'data' dict or None on failure.
    """
    for endpoint in TIKWM_ENDPOINTS:
        for attempt in range(2):
            try:
                resp = http_session.post(
                    endpoint,
                    data={"url": url, "hd": "1"},
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue
                result = resp.json()
                if result.get("code") == 0 and result.get("data"):
                    log.info("TikWM success via %s (attempt %d)", endpoint, attempt + 1)
                    return result["data"]
            except Exception as e:
                log.warning("TikWM %s attempt %d failed: %s", endpoint, attempt + 1, e)
                if attempt == 0:
                    time.sleep(0.3)
    return None


def download_bytes(url):
    """Download a URL and return raw bytes. Returns None on failure."""
    try:
        resp = http_session.get(url, timeout=45)
        if resp.status_code == 200:
            return resp.content
    except Exception as e:
        log.warning("Download failed for %s: %s", url[:80], e)
    return None


def download_multiple_concurrent(urls):
    """Download multiple URLs concurrently using thread pool. Returns list of (index, bytes)."""
    results = [None] * len(urls)
    futures = {}
    for idx, u in enumerate(urls):
        future = download_pool.submit(download_bytes, u)
        futures[future] = idx
    for future in as_completed(futures):
        idx = futures[future]
        try:
            data = future.result()
            if data:
                results[idx] = data
        except Exception:
            pass
    return results


# ─── yt-dlp Fallback ────────────────────────────────────────────────────────

def ytdlp_fallback(url):
    """
    Fallback: use yt-dlp subprocess to download.
    Returns dict with 'video_path', 'audio_path', 'title', 'tmpdir' or None.
    """
    log.info("Using yt-dlp fallback for %s", url)
    tmpdir = tempfile.mkdtemp(prefix="aura_")
    template = os.path.join(tmpdir, "%(title)s_%(format_id)s.%(ext)s")

    try:
        result = subprocess.run(
            ["yt-dlp", "--impersonate", "chrome", url, "-f", "best,bestaudio", "-o", template],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        log.error("yt-dlp timed out for %s", url)
        cleanup_tmpdir(tmpdir)
        return None
    except subprocess.CalledProcessError as e:
        log.error("yt-dlp failed: %s", e.stderr.decode(errors="ignore")[:300] if e.stderr else "")
        cleanup_tmpdir(tmpdir)
        return None
    except Exception as e:
        log.error("yt-dlp fallback error: %s", e)
        cleanup_tmpdir(tmpdir)
        return None

    # Find video
    vids = glob.glob(os.path.join(tmpdir, "*.mp4"))
    if not vids:
        cleanup_tmpdir(tmpdir)
        return None

    vid_path = vids[0]
    filename = os.path.basename(vid_path)
    title = os.path.splitext(filename)[0].rsplit("_", 1)[0]
    title = re.sub(r"\s*\[\d+\]$", "", title)

    # Find audio
    auds = glob.glob(os.path.join(tmpdir, "*.mp3")) + glob.glob(os.path.join(tmpdir, "*.m4a"))
    aud_path = auds[0] if auds else None

    return {"video_path": vid_path, "audio_path": aud_path, "title": title, "tmpdir": tmpdir}


def cleanup_tmpdir(tmpdir):
    """Remove temporary directory."""
    try:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


# ─── Progress Helper ────────────────────────────────────────────────────────

def update_progress(chat_id, msg_id, bar, pct, text):
    """Update progress bar message. Silently ignores errors."""
    try:
        bot.edit_message_text(
            f"{bar} {pct}\n\n{text}",
            chat_id=chat_id,
            message_id=msg_id,
        )
    except Exception:
        pass


# ─── Slideshow Handler ──────────────────────────────────────────────────────

def handle_slideshow(message, chat_id, msg_id, data, title, images, music_url):
    """Download and send all slideshow images as album(s) + audio."""
    image_count = len(images)
    log.info("Slideshow detected: %d images", image_count)

    update_progress(chat_id, msg_id, "██████▒▒▒▒", "60%", "⬇️ ছবি ডাউনলোড হচ্ছে...")

    # Download all images concurrently
    image_bytes_list = download_multiple_concurrent(images)

    # Filter out failures, keep order
    valid_images = [(i, b) for i, b in enumerate(image_bytes_list) if b is not None]

    if not valid_images:
        bot.edit_message_text(
            "❌ ছবি ডাউনলোড করতে ব্যর্থ হয়েছে।\nদয়া করে আবার চেষ্টা করুন।",
            chat_id=chat_id,
            message_id=msg_id,
        )
        return

    update_progress(chat_id, msg_id, "████████▒▒", "80%", "📤 ছবি পাঠানো হচ্ছে...")

    total_images = len(valid_images)
    caption_text = slideshow_caption(title, total_images)

    # Send images as album(s) — Telegram allows max 10 per album
    all_bytes = [b for _, b in valid_images]
    for batch_start in range(0, total_images, TELEGRAM_PHOTO_ALBUM_LIMIT):
        batch = all_bytes[batch_start: batch_start + TELEGRAM_PHOTO_ALBUM_LIMIT]
        media_group = []
        for idx, img_bytes in enumerate(batch):
            # Caption on first photo of first batch only
            cap = caption_text if (batch_start == 0 and idx == 0) else None
            media_group.append(
                InputMediaPhoto(
                    media=BytesIO(img_bytes),
                    caption=cap,
                )
            )

        try:
            bot.send_media_group(chat_id, media=media_group)
        except Exception as e:
            log.error("Failed to send album batch: %s", e)
            # Fallback: send images one by one
            for idx, img_bytes in enumerate(batch):
                try:
                    cap = caption_text if (batch_start == 0 and idx == 0) else None
                    bot.send_photo(chat_id, photo=BytesIO(img_bytes), caption=cap)
                except Exception:
                    pass

    # Send audio if available
    if music_url:
        update_progress(chat_id, msg_id, "█████████▒", "90%", "🎵 অডিও পাঠানো হচ্ছে...")
        audio_bytes = download_bytes(music_url)
        if audio_bytes:
            try:
                author_name = "Unknown"
                author_info = data.get("author")
                if isinstance(author_info, dict):
                    author_name = author_info.get("nickname", "Unknown")
                bot.send_audio(
                    chat_id,
                    audio=BytesIO(audio_bytes),
                    caption=audio_caption(),
                    title="Original Audio",
                    performer=author_name,
                )
            except Exception as e:
                log.warning("Failed to send audio: %s", e)

    # Done — delete progress message
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


# ─── Video Handler (TikWM) ──────────────────────────────────────────────────

def handle_video_tikwm(message, chat_id, msg_id, data, title, music_url):
    """Download and send video via TikWM data."""
    vid_url = data.get("hdplay") or data.get("play")
    if not vid_url:
        handle_video_ytdlp(message, chat_id, msg_id, message.text.strip())
        return

    update_progress(chat_id, msg_id, "██████▒▒▒▒", "60%", "⬇️ ভিডিও ডাউনলোড হচ্ছে...")

    # Download video and audio concurrently
    urls_to_download = [vid_url]
    if music_url:
        urls_to_download.append(music_url)

    results = download_multiple_concurrent(urls_to_download)
    vid_bytes = results[0]
    aud_bytes = results[1] if len(results) > 1 else None

    if not vid_bytes:
        log.warning("TikWM video download failed, trying yt-dlp")
        handle_video_ytdlp(message, chat_id, msg_id, message.text.strip())
        return

    update_progress(chat_id, msg_id, "████████▒▒", "80%", "📤 ভিডিও পাঠানো হচ্ছে...")

    # Send video
    try:
        bot.send_video(
            chat_id,
            video=BytesIO(vid_bytes),
            caption=video_caption(title),
            supports_streaming=True,
        )
    except Exception as e:
        log.error("Failed to send video: %s", e)
        bot.edit_message_text(
            "❌ ভিডিও পাঠাতে ব্যর্থ হয়েছে।\nফাইল সাইজ অতিরিক্ত বড় হতে পারে।",
            chat_id=chat_id,
            message_id=msg_id,
        )
        return

    # Send audio
    if aud_bytes:
        try:
            author_name = "Unknown"
            author_info = data.get("author")
            if isinstance(author_info, dict):
                author_name = author_info.get("nickname", "Unknown")
            bot.send_audio(
                chat_id,
                audio=BytesIO(aud_bytes),
                caption=audio_caption(),
                title="Original Audio",
                performer=author_name,
            )
        except Exception as e:
            log.warning("Failed to send audio: %s", e)

    # Done — delete progress message
    try:
        bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


# ─── Video Handler (yt-dlp fallback) ────────────────────────────────────────

def handle_video_ytdlp(message, chat_id, msg_id, url):
    """Fallback: download via yt-dlp subprocess."""
    update_progress(chat_id, msg_id, "██████▒▒▒▒", "60%", "🔄 Alternative method চেষ্টা হচ্ছে...")

    result = ytdlp_fallback(url)
    if not result:
        bot.edit_message_text(
            "❌ ডাউনলোড করতে ব্যর্থ হয়েছে।\n\n"
            "সম্ভাব্য কারণ:\n"
            "• লিংকটি ভুল বা মেয়াদোত্তীর্ণ\n"
            "• TikTok সার্ভারে সমস্যা\n\n"
            "দয়া করে আবার চেষ্টা করুন।",
            chat_id=chat_id,
            message_id=msg_id,
        )
        return

    try:
        update_progress(chat_id, msg_id, "████████▒▒", "80%", "📤 ফাইল পাঠানো হচ্ছে...")

        with open(result["video_path"], "rb") as vf:
            bot.send_video(chat_id, video=vf, caption=video_caption(result["title"]), supports_streaming=True)

        if result.get("audio_path"):
            with open(result["audio_path"], "rb") as af:
                bot.send_audio(chat_id, audio=af, caption=audio_caption(), title="Original Audio", performer="Unknown artist")

        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    finally:
        cleanup_tmpdir(result.get("tmpdir", ""))


# ─── Main Message Handler ───────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    welcome = (
        "🌟 𝐀𝐮𝐫𝐚 𝐓𝐢𝐤𝐓𝐨𝐤 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "আমাকে একটি TikTok লিংক পাঠান, আমি ডাউনলোড করে দেবো!\n\n"
        "📽 𝐕𝐢𝐝𝐞𝐨 — HD without watermark\n"
        "🖼 𝐒𝐥𝐢𝐝𝐞𝐬𝐡𝐨𝐰 — সব ছবি ডাউনলোড\n"
        "🎵 𝐀𝐮𝐝𝐢𝐨 — Original soundtrack\n\n"
        "⚡ Ultra-fast downloads powered by Aura ⚡"
    )
    bot.reply_to(message, welcome)


@bot.message_handler(commands=["help"])
def cmd_help(message):
    help_text = (
        "📖 𝐇𝐨𝐰 𝐭𝐨 𝐮𝐬𝐞:\n\n"
        "1️⃣ TikTok অ্যাপ থেকে ভিডিও/ফটো লিংক কপি করুন\n"
        "2️⃣ এখানে পেস্ট করে পাঠান\n"
        "3️⃣ ভিডিও + অডিও / সব ছবি পেয়ে যাবেন!\n\n"
        "✅ ভিডিও — HD, no watermark\n"
        "✅ স্লাইডশো/ফটো — সবগুলো ছবি\n"
        "✅ অডিও — Original sound\n\n"
        "⚡ Powered by 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵"
    )
    bot.reply_to(message, help_text)


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()

    if "tiktok.com" not in url and "tiktok" not in url.lower():
        bot.reply_to(message, "❌ দয়া করে একটি সঠিক TikTok লিংক পাঠান।")
        return

    # Send initial progress
    msg = bot.reply_to(message, "▒▒▒▒▒▒▒▒▒▒ 0%\n\n🔍 লিংক যাচাই হচ্ছে...")
    chat_id = message.chat.id
    msg_id = msg.message_id

    try:
        # ─── Stage 1: Fetch data from TikWM API ─────────────────────
        update_progress(chat_id, msg_id, "███▒▒▒▒▒▒▒", "30%", "📡 ডাটা সংগ্রহ হচ্ছে...")
        data = fetch_tikwm(url)

        if data:
            title = data.get("title", "TikTok Content") or "TikTok Content"
            images = data.get("images")
            music_url = data.get("music")

            if images and len(images) > 0:
                # ─── SLIDESHOW / PHOTO CAROUSEL ──────────────────────
                handle_slideshow(message, chat_id, msg_id, data, title, images, music_url)
            else:
                # ─── VIDEO ───────────────────────────────────────────
                handle_video_tikwm(message, chat_id, msg_id, data, title, music_url)
        else:
            # ─── FALLBACK: yt-dlp ────────────────────────────────────
            log.info("TikWM failed, falling back to yt-dlp")
            handle_video_ytdlp(message, chat_id, msg_id, url)

    except Exception as e:
        log.error("Unhandled error: %s", e, exc_info=True)
        try:
            bot.edit_message_text(
                f"❌ একটি সমস্যা হয়েছে:\n{str(e)[:200]}\n\nদয়া করে আবার চেষ্টা করুন।",
                chat_id=chat_id,
                message_id=msg_id,
            )
        except Exception:
            pass


# ─── Run ─────────────────────────────────────────────────────────────────────

def run_bot():
    log.info("Aura Bot starting polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    log.info("Health check server starting on port %d", PORT)
    app.run(host="0.0.0.0", port=PORT)
