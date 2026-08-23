from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "꧁𓊈𒆜 𝐀𝐔𝐑𝐀 𝐅𝐅𝐗 𒆜𓊉꧂ FB/IG API is Running!"

@app.route('/api/download', methods=['GET', 'POST'])
def extract_media():
    # ── ১. ডাউনলোড বাটনে ক্লিক করলে (GET) ফোর্স ডাউনলোড হবে এবং কাস্টম নাম বসবে ──
    if request.method == 'GET':
        video_url = request.args.get('url')
        ext = request.args.get('ext', 'mp4') # mp4, mp3 বা jpg এক্সটেনশন নেবে
        
        # ওয়েবসাইট থেকে পাঠানো নামটা রিসিভ করবে, না পেলে ডিফল্ট নাম দেবে
        filename = request.args.get('filename', 'AURA_FFX_Media') 
        
        if not video_url:
            return "No URL provided", 400
        
        try:
            # ফেসবুক/ইনস্টাগ্রাম থেকে ডেটা স্ট্রিম করে সরাসরি ইউজারের কাছে পাঠানো হচ্ছে
            req = requests.get(video_url, stream=True)
            return Response(
                req.iter_content(chunk_size=1024 * 1024),
                content_type=req.headers.get('content-type'),
                headers={'Content-Disposition': f'attachment; filename="{filename}.{ext}"'}
            )
        except Exception as e:
            return str(e), 500

    # ── ২. ওয়েবসাইট থেকে লিংক পেস্ট করলে (POST) লিংকের ডেটা খুঁজবে ──
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "No URL provided"}), 400

    url = data['url']

    # yt-dlp অপশন (ফাইল সার্ভারে সেভ না করে শুধু লিংক নেবে)
    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'quiet': True,
        'skip_download': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            video_url = info.get('url')
            title = info.get('title', 'Facebook Video')
            thumbnail = info.get('thumbnail')

            audio_url = video_url
            for f in info.get('formats', []):
                if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                    audio_url = f.get('url')
                    break

            if not video_url:
                return jsonify({"error": "Could not extract video link."}), 400

            return jsonify({
                "play": video_url,
                "hdplay": video_url,
                "music": audio_url,
                "cover": thumbnail,
                "title": title
            })

    except Exception as e:
        return jsonify({"error": f"Failed to fetch media. Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
