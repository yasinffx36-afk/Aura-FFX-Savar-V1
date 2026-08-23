import yt_dlp
import os

url = "https://vt.tiktok.com/ZSVu1x8jD/"
download_path = r"C:\Users\YASIN FFX\Desktop\FDA\video\downloads"
os.makedirs(download_path, exist_ok=True)

ydl_opts = {
    'format': 'best',
    'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
    'quiet': False,
    'no_warnings': True,
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"Downloading {url} to {download_path}")
        ydl.download([url])
        print("Download successful!")
except Exception as e:
    print(f"An error occurred: {e}")
