"""
Aura TikTok Downloader Bot — Advanced Version
==============================================
Features:
  - TikWM API for ultra-fast downloads (no subprocess)
  - Slideshow / Photo Carousel support (downloads all images)
  - HD Video without watermark + Original Audio
  - Async architecture (aiogram 3.x + aiohttp)
  - yt-dlp fallback if TikWM fails
  - Concurrent image downloads with asyncio.gather
  - Real-time progress bar
  - Health check endpoint for Render
"""

import os
import re
import asyncio
import logging
import tempfile
import subprocess
import glob
from io import BytesIO

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InputMediaPhoto,
    BufferedInputFile,
    FSInputFile,
)
from aiogram.enums import ParseMode
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector

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

# aiohttp settings for speed
HTTP_TIMEOUT = ClientTimeout(total=60, connect=10)
MAX_CONNECTIONS = 30

# Telegram limits
TELEGRAM_PHOTO_ALBUM_LIMIT = 10  # max 10 media in one album

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("aura_bot")

# ─── Bot & Dispatcher ───────────────────────────────────────────────────────

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Global aiohttp session (reused across requests for connection pooling)
session: ClientSession | None = None


async def get_session() -> ClientSession:
    """Get or create the global aiohttp session with connection pooling."""
    global session
    if session is None or session.closed:
        connector = TCPConnector(limit=MAX_CONNECTIONS, ttl_dns_cache=300)
        session = ClientSession(
            timeout=HTTP_TIMEOUT,
            connector=connector,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
    return session


# ─── Caption Helpers ─────────────────────────────────────────────────────────

def video_caption(title: str) -> str:
    return (
        "┏ 📽 𝐓𝐢𝐤𝐓𝐨𝐤 𝐕𝐢𝐝𝐞𝐨 📽 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        f"📝 𝐓𝐢𝐭𝐥𝐞: {title}\n"
        "🔥 𝐐𝐮𝐚𝐥𝐢𝐭𝐲: HD (No Watermark)\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )


def audio_caption() -> str:
    return (
        "┏ 🎵 𝐓𝐢𝐤𝐓𝐨𝐤 𝐀𝐮𝐝𝐢𝐨 🎵 ┓\n"
        "┗━━━━━━━━━━━━━━━┛\n\n"
        "🎧 Original Soundtrack\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )


def slideshow_caption(title: str, count: int) -> str:
    return (
        "┏ 🖼 𝐓𝐢𝐤𝐓𝐨𝐤 𝐒𝐥𝐢𝐝𝐞𝐬𝐡𝐨𝐰 🖼 ┓\n"
        "┗━━━━━━━━━━━━━━━━━━┛\n\n"
        f"📝 𝐓𝐢𝐭𝐥𝐞: {title}\n"
        f"📸 𝐏𝐡𝐨𝐭𝐨𝐬: {count}\n\n"
        "✨ 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘷𝘪𝘢 𝘈𝘶𝘳𝘢 𝘉𝘰𝘵 ⚡"
    )


# ─── Progress Bar ───────────────────────────────────────────────────────────

PROGRESS_STAGES = [
    ("▒▒▒▒▒▒▒▒▒▒", "0%", "🔍 লিংক যাচাই হচ্ছে..."),
    ("███▒▒▒▒▒▒▒", "30%", "📡 ডাটা সংগ্রহ হচ্ছে..."),
    ("██████▒▒▒▒", "60%", "⬇️ ডাউনলোড হচ্ছে..."),
    ("████████▒▒", "80%", "📤 ফাইল পাঠানো হচ্ছে..."),
    ("██████████", "100%", "💥 𝐁𝐎𝐎𝐌! 💥"),
]


async def update_progress(chat_id: int, msg_id: int, stage: int):
    """Update progress bar message. Silently ignores edit failures."""
    if stage >= len(PROGRESS_STAGES):
        return
    bar, pct, text = PROGRESS_STAGES[stage]
    try:
        await bot.edit_message_text(
            f"{bar} {pct}\n\n{text}",
            chat_id=chat_id,
            message_id=msg_id,
        )
    except Exception:
        pass  # ignore rate-limit / message-not-modified errors


# ─── TikWM API ──────────────────────────────────────────────────────────────

async def fetch_tikwm(url: str) -> dict | None:
    """
    Call TikWM API to get video/slideshow data.
    Tries multiple endpoints for reliability.
    Returns the 'data' dict or None on failure.
    """
    s = await get_session()
    for endpoint in TIKWM_ENDPOINTS:
        for attempt in range(2):  # retry once per endpoint
            try:
                async with s.post(
                    endpoint,
                    data={"url": url, "hd": "1"},
                    timeout=ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        continue
                    result = await resp.json(content_type=None)
                    if result.get("code") == 0 and result.get("data"):
                        log.info("TikWM success via %s (attempt %d)", endpoint, attempt + 1)
                        return result["data"]
            except Exception as e:
                log.warning("TikWM %s attempt %d failed: %s", endpoint, attempt + 1, e)
                if attempt == 0:
                    await asyncio.sleep(0.5)  # brief pause before retry
    return None


async def download_bytes(url: str) -> bytes | None:
    """Download a URL and return raw bytes. Returns None on failure."""
    s = await get_session()
    try:
        async with s.get(url, timeout=ClientTimeout(total=45)) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as e:
        log.warning("Download failed for %s: %s", url[:80], e)
    return None


async def download_multiple(urls: list[str]) -> list[bytes]:
    """Download multiple URLs concurrently. Returns list of bytes (skips failures)."""
    tasks = [download_bytes(u) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, bytes)]


# ─── yt-dlp Fallback ────────────────────────────────────────────────────────

async def ytdlp_fallback(url: str) -> dict | None:
    """
    Fallback: use yt-dlp in subprocess to download.
    Returns dict with 'video_path', 'audio_path', 'title' or None.
    """
    log.info("Using yt-dlp fallback for %s", url)
    tmpdir = tempfile.mkdtemp(prefix="aura_")
    template = os.path.join(tmpdir, "%(title)s_%(format_id)s.%(ext)s")

    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--impersonate", "chrome",
            url, "-f", "best,bestaudio",
            "-o", template,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            log.error("yt-dlp failed: %s", stderr.decode(errors="ignore")[:300])
            return None

        # Find video
        vids = glob.glob(os.path.join(tmpdir, "*.mp4"))
        if not vids:
            return None

        vid_path = vids[0]
        filename = os.path.basename(vid_path)
        title = os.path.splitext(filename)[0].rsplit("_", 1)[0]
        title = re.sub(r"\s*\[\d+\]$", "", title)

        # Find audio
        auds = glob.glob(os.path.join(tmpdir, "*.mp3")) + glob.glob(os.path.join(tmpdir, "*.m4a"))
        aud_path = auds[0] if auds else None

        return {"video_path": vid_path, "audio_path": aud_path, "title": title, "tmpdir": tmpdir}

    except asyncio.TimeoutError:
        log.error("yt-dlp timed out for %s", url)
        return None
    except Exception as e:
        log.error("yt-dlp fallback error: %s", e)
        return None


def cleanup_tmpdir(tmpdir: str):
    """Remove temporary directory and all its contents."""
    try:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


# ─── Handlers ────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome = (
        "🌟 𝐀𝐮𝐫𝐚 𝐓𝐢𝐤𝐓𝐨𝐤 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "আমাকে একটি TikTok লিংক পাঠান, আমি ডাউনলোড করে দেবো!\n\n"
        "📽 𝐕𝐢𝐝𝐞𝐨 — HD without watermark\n"
        "🖼 𝐒𝐥𝐢𝐝𝐞𝐬𝐡𝐨𝐰 — সব ছবি ডাউনলোড\n"
        "🎵 𝐀𝐮𝐝𝐢𝐨 — Original soundtrack\n\n"
        "⚡ Ultra-fast downloads powered by Aura ⚡"
    )
    await message.reply(welcome)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
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
    await message.reply(help_text)


@router.message(F.text)
async def handle_link(message: types.Message):
    """Main handler: process TikTok links."""
    url = message.text.strip()

    # Validate TikTok URL
    if "tiktok.com" not in url and "tiktok" not in url.lower():
        await message.reply("❌ দয়া করে একটি সঠিক TikTok লিংক পাঠান।")
        return

    # Send initial progress message
    progress_msg = await message.reply("▒▒▒▒▒▒▒▒▒▒ 0%\n\n🔍 লিংক যাচাই হচ্ছে...")
    chat_id = message.chat.id
    msg_id = progress_msg.message_id

    try:
        # ─── Stage 1: Fetch data from TikWM API ─────────────────────────
        await update_progress(chat_id, msg_id, 1)
        data = await fetch_tikwm(url)

        if data:
            title = data.get("title", "TikTok Content") or "TikTok Content"
            images = data.get("images")
            music_url = data.get("music")

            if images and len(images) > 0:
                # ─── SLIDESHOW / PHOTO CAROUSEL ──────────────────────────
                await handle_slideshow(message, chat_id, msg_id, data, title, images, music_url)
            else:
                # ─── VIDEO ───────────────────────────────────────────────
                await handle_video_tikwm(message, chat_id, msg_id, data, title, music_url)
        else:
            # ─── FALLBACK: yt-dlp ────────────────────────────────────────
            log.info("TikWM failed, falling back to yt-dlp")
            await bot.edit_message_text(
                "███▒▒▒▒▒▒▒ 30%\n\n🔄 Alternative method চেষ্টা হচ্ছে...",
                chat_id=chat_id,
                message_id=msg_id,
            )
            await handle_video_ytdlp(message, chat_id, msg_id, url)

    except Exception as e:
        log.error("Unhandled error: %s", e, exc_info=True)
        try:
            await bot.edit_message_text(
                f"❌ একটি সমস্যা হয়েছে:\n{str(e)[:200]}\n\nদয়া করে আবার চেষ্টা করুন।",
                chat_id=chat_id,
                message_id=msg_id,
            )
        except Exception:
            pass


# ─── Slideshow Handler ───────────────────────────────────────────────────────

async def handle_slideshow(
    message: types.Message,
    chat_id: int,
    msg_id: int,
    data: dict,
    title: str,
    images: list,
    music_url: str | None,
):
    """Download and send all slideshow images as album(s) + audio."""
    image_count = len(images)
    log.info("Slideshow detected: %d images", image_count)

    await update_progress(chat_id, msg_id, 2)

    # Download all images concurrently
    image_bytes_list = await download_multiple(images)

    if not image_bytes_list:
        await bot.edit_message_text(
            "❌ ছবি ডাউনলোড করতে ব্যর্থ হয়েছে।\nদয়া করে আবার চেষ্টা করুন।",
            chat_id=chat_id,
            message_id=msg_id,
        )
        return

    await update_progress(chat_id, msg_id, 3)

    # Send images as album(s) — Telegram allows max 10 per album
    total_images = len(image_bytes_list)
    caption_text = slideshow_caption(title, total_images)

    for batch_start in range(0, total_images, TELEGRAM_PHOTO_ALBUM_LIMIT):
        batch = image_bytes_list[batch_start : batch_start + TELEGRAM_PHOTO_ALBUM_LIMIT]
        media_group = []
        for idx, img_bytes in enumerate(batch):
            photo = BufferedInputFile(img_bytes, filename=f"photo_{batch_start + idx + 1}.jpg")
            # Put caption only on first image of first batch
            cap = caption_text if (batch_start == 0 and idx == 0) else None
            media_group.append(InputMediaPhoto(media=photo, caption=cap))

        try:
            await bot.send_media_group(chat_id, media=media_group)
        except Exception as e:
            log.error("Failed to send album batch: %s", e)
            # Try sending images one by one as fallback
            for item in media_group:
                try:
                    await bot.send_photo(chat_id, photo=item.media, caption=item.caption)
                except Exception:
                    pass

    # Send audio if available
    if music_url:
        audio_bytes = await download_bytes(music_url)
        if audio_bytes:
            audio_file = BufferedInputFile(audio_bytes, filename="audio.mp3")
            try:
                await bot.send_audio(
                    chat_id,
                    audio=audio_file,
                    caption=audio_caption(),
                    title="Original Audio",
                    performer=data.get("author", {}).get("nickname", "Unknown"),
                )
            except Exception as e:
                log.warning("Failed to send audio: %s", e)

    await update_progress(chat_id, msg_id, 4)

    # Delete progress message
    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


# ─── Video Handler (TikWM) ──────────────────────────────────────────────────

async def handle_video_tikwm(
    message: types.Message,
    chat_id: int,
    msg_id: int,
    data: dict,
    title: str,
    music_url: str | None,
):
    """Download and send video via TikWM data."""
    # Get HD video URL (prefer hdplay > play)
    vid_url = data.get("hdplay") or data.get("play")
    if not vid_url:
        # No video URL found, try fallback
        await handle_video_ytdlp(message, chat_id, msg_id, message.text.strip())
        return

    await update_progress(chat_id, msg_id, 2)

    # Download video and audio concurrently
    download_tasks = [download_bytes(vid_url)]
    if music_url:
        download_tasks.append(download_bytes(music_url))

    results = await asyncio.gather(*download_tasks, return_exceptions=True)
    vid_bytes = results[0] if isinstance(results[0], bytes) else None
    aud_bytes = results[1] if len(results) > 1 and isinstance(results[1], bytes) else None

    if not vid_bytes:
        # TikWM download failed, try yt-dlp fallback
        log.warning("TikWM video download failed, trying yt-dlp")
        await handle_video_ytdlp(message, chat_id, msg_id, message.text.strip())
        return

    await update_progress(chat_id, msg_id, 3)

    # Send video
    video_file = BufferedInputFile(vid_bytes, filename="video.mp4")
    try:
        await bot.send_video(
            chat_id,
            video=video_file,
            caption=video_caption(title),
            supports_streaming=True,
        )
    except Exception as e:
        log.error("Failed to send video: %s", e)
        await bot.edit_message_text(
            "❌ ভিডিও পাঠাতে ব্যর্থ হয়েছে।\nফাইল সাইজ অতিরিক্ত বড় হতে পারে।",
            chat_id=chat_id,
            message_id=msg_id,
        )
        return

    # Send audio
    if aud_bytes:
        audio_file = BufferedInputFile(aud_bytes, filename="audio.mp3")
        try:
            await bot.send_audio(
                chat_id,
                audio=audio_file,
                caption=audio_caption(),
                title="Original Audio",
                performer=data.get("author", {}).get("nickname", "Unknown"),
            )
        except Exception as e:
            log.warning("Failed to send audio: %s", e)

    await update_progress(chat_id, msg_id, 4)

    # Delete progress message
    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


# ─── Video Handler (yt-dlp fallback) ────────────────────────────────────────

async def handle_video_ytdlp(
    message: types.Message,
    chat_id: int,
    msg_id: int,
    url: str,
):
    """Fallback: download via yt-dlp subprocess."""
    await bot.edit_message_text(
        "██████▒▒▒▒ 60%\n\n⬇️ yt-dlp দিয়ে ডাউনলোড হচ্ছে...",
        chat_id=chat_id,
        message_id=msg_id,
    )

    result = await ytdlp_fallback(url)
    if not result:
        await bot.edit_message_text(
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
        await bot.edit_message_text(
            "████████▒▒ 80%\n\n📤 ফাইল পাঠানো হচ্ছে...",
            chat_id=chat_id,
            message_id=msg_id,
        )

        # Send video
        vid_file = FSInputFile(result["video_path"])
        await bot.send_video(
            chat_id,
            video=vid_file,
            caption=video_caption(result["title"]),
            supports_streaming=True,
        )

        # Send audio
        if result.get("audio_path"):
            aud_file = FSInputFile(result["audio_path"])
            await bot.send_audio(
                chat_id,
                audio=aud_file,
                caption=audio_caption(),
                title="Original Audio",
                performer="Unknown artist",
            )

        await bot.edit_message_text(
            "██████████ 100%\n\n💥 𝐁𝐎𝐎𝐌! 💥",
            chat_id=chat_id,
            message_id=msg_id,
        )

        # Delete progress message
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    finally:
        cleanup_tmpdir(result.get("tmpdir", ""))


# ─── Health Check Web Server ────────────────────────────────────────────────

async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text="Bot is running!")


async def start_health_server():
    """Start a lightweight HTTP server for Render health checks."""
    app = web.Application()
    app.router.add_get("/", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Health check server started on port %d", PORT)


# ─── Main ────────────────────────────────────────────────────────────────────

async def on_startup():
    """Run on bot startup."""
    log.info("Aura Bot starting...")
    await start_health_server()
    log.info("Bot is ready!")


async def on_shutdown():
    """Cleanup on bot shutdown."""
    global session
    if session and not session.closed:
        await session.close()
    log.info("Bot shut down.")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
