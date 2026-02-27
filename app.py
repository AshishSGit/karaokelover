from flask import Flask, jsonify, request, render_template, Response
from dotenv import load_dotenv
import requests
import re
import os

load_dotenv()

app = Flask(__name__)

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'
LRCLIB_URL = 'https://lrclib.net/api'


def parse_song_info(video_title):
    """Extract artist and song name from a YouTube karaoke video title."""
    title = video_title

    # Strip common karaoke/lyric noise
    noise_patterns = [
        r'\(.*?karaoke.*?\)',
        r'\[.*?karaoke.*?\]',
        r'\(.*?instrumental.*?\)',
        r'\[.*?instrumental.*?\]',
        r'\(.*?with\s+lyrics?.*?\)',
        r'\[.*?with\s+lyrics?.*?\]',
        r'\(.*?no\s+guide.*?\)',
        r'\bkaraoke\s*(version|track|edition)?\b',
        r'\blyrics?\b',
        r'\(official.*?\)',
        r'\[official.*?\]',
        r'\(.*?hd.*?\)',
        r'\[.*?hd.*?\]',
        r'\(.*?audio.*?\)',
    ]
    for pat in noise_patterns:
        title = re.sub(pat, '', title, flags=re.IGNORECASE)

    title = title.strip(' -–—|_').strip()

    # Try "Artist - Song" or "Artist – Song" split
    parts = re.split(r'\s[-–—]\s', title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()

    return None, title.strip()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/sitemap.xml')
def sitemap():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.karaokelover.com/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>'''
    return Response(xml, mimetype='application/xml')


@app.route('/api/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query is required'}), 400

    params = {
        'key': YOUTUBE_API_KEY,
        'q': f'{query} karaoke',
        'part': 'snippet',
        'type': 'video',
        'videoCategoryId': '10',
        'maxResults': 20,
        'order': 'relevance',
    }

    try:
        resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if 'error' in data:
        return jsonify({'error': data['error']['message']}), 500

    results = []
    for item in data.get('items', []):
        vid_id = item.get('id', {}).get('videoId')
        if not vid_id:
            continue
        snippet = item['snippet']
        results.append({
            'video_id': vid_id,
            'title': snippet['title'],
            'channel': snippet['channelTitle'],
            'thumbnail': snippet['thumbnails']['medium']['url'],
            'published_at': snippet['publishedAt'],
        })

    return jsonify({'results': results})


@app.route('/api/lyrics')
def lyrics():
    video_title = request.args.get('title', '').strip()
    if not video_title:
        return jsonify({'error': 'title is required'}), 400

    artist, song = parse_song_info(video_title)

    try:
        # Search lrclib.net — works with or without artist
        query = f"{artist} {song}" if artist else song
        resp  = requests.get(f"{LRCLIB_URL}/search", params={'q': query}, timeout=8)
        results = resp.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if not results:
        return jsonify({'error': 'Lyrics not found'}), 404

    # Pick best match: prefer one with plain lyrics
    best = next((r for r in results if r.get('plainLyrics')), None)
    if not best:
        return jsonify({'error': 'Lyrics not found'}), 404

    return jsonify({
        'lyrics': best['plainLyrics'],
        'artist': best.get('artistName', artist or ''),
        'song':   best.get('trackName',  song),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)
