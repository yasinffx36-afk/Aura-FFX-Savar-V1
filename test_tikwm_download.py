import urllib.request
import urllib.parse
import json
import os

url = "https://vt.tiktok.com/ZSVu1x8jD/"
api_url = "https://www.tikwm.com/api/?url=" + urllib.parse.quote(url) + "&hd=1"
req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    response = urllib.request.urlopen(req).read().decode('utf-8')
    data = json.loads(response)
    if data.get('code') == 0:
        video_url = data['data']['hdplay'] # hd video
        title = data['data']['title']
        print(f"Found video: {title}")
        print(f"Download URL: {video_url}")
        
        # Download the video
        download_path = r"C:\Users\YASIN FFX\Desktop\FDA\video\downloads"
        os.makedirs(download_path, exist_ok=True)
        filename = "downloaded_video.mp4"
        filepath = os.path.join(download_path, filename)
        
        print("Downloading...")
        urllib.request.urlretrieve(video_url, filepath)
        print(f"Downloaded to {filepath}")
    else:
        print("API Error:", data.get('msg'))
except Exception as e:
    print("Error:", e)
