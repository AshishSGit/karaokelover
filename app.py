from flask import Flask, jsonify, request, render_template, Response
from dotenv import load_dotenv
import requests
import re
import os
import json

load_dotenv()

app = Flask(__name__)

YOUTUBE_API_KEY     = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_SEARCH_URL  = 'https://www.googleapis.com/youtube/v3/search'
LRCLIB_URL          = 'https://lrclib.net/api'
OPENAI_API_KEY      = os.getenv('OPENAI_API_KEY')
N8N_LYRICS_WEBHOOK  = os.getenv('N8N_LYRICS_WEBHOOK')
N8N_TRENDING_SECRET = os.getenv('N8N_TRENDING_SECRET', '')
TRENDING_FILE       = os.path.join(os.path.dirname(__file__), 'trending.json')

DEFAULT_TRENDING = [
    {'artist': 'Adele',           'song': 'Hello'},
    {'artist': 'Ed Sheeran',      'song': 'Shape of You'},
    {'artist': 'Queen',           'song': 'Bohemian Rhapsody'},
    {'artist': 'Taylor Swift',    'song': 'Anti-Hero'},
    {'artist': 'The Weeknd',      'song': 'Blinding Lights'},
    {'artist': 'Journey',         'song': "Don't Stop Believin'"},
    {'artist': 'Whitney Houston', 'song': 'I Will Always Love You'},
    {'artist': 'Billie Eilish',   'song': 'Bad Guy'},
]


def _regex_parse(video_title):
    """Fallback regex parser for YouTube karaoke titles."""
    title = video_title
    noise_patterns = [
        r'\(.*?karaoke.*?\)', r'\[.*?karaoke.*?\]',
        r'\(.*?instrumental.*?\)', r'\[.*?instrumental.*?\]',
        r'\(.*?with\s+lyrics?.*?\)', r'\[.*?with\s+lyrics?.*?\]',
        r'\(.*?no\s+guide.*?\)',
        r'\bkaraoke\s*(version|track|edition)?\b',
        r'\blyrics?\b',
        r'\(official.*?\)', r'\[official.*?\]',
        r'\(.*?hd.*?\)', r'\[.*?hd.*?\]',
        r'\(.*?audio.*?\)',
    ]
    for pat in noise_patterns:
        title = re.sub(pat, '', title, flags=re.IGNORECASE)
    title = title.strip(' -–—|_').strip()
    parts = re.split(r'\s[-–—]\s', title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, title.strip()


def _openai_chat(prompt, max_tokens=100):
    """Call OpenAI chat completions, returns text or raises."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model='gpt-4o-mini',
        max_tokens=max_tokens,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return resp.choices[0].message.content.strip()


def parse_song_info(video_title):
    """Extract artist and song name using OpenAI, falling back to regex."""
    if not OPENAI_API_KEY:
        return _regex_parse(video_title)
    try:
        text = _openai_chat(
            'Extract the artist name and song title from this YouTube karaoke video title. '
            'Return ONLY valid JSON with keys "artist" and "song", no extra text. '
            f'Use null for artist if unknown. Title: {video_title}'
        )
        parsed = json.loads(text)
        artist = parsed.get('artist') or None
        song   = parsed.get('song')   or video_title
        return artist, song
    except Exception:
        return _regex_parse(video_title)


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
            'video_id':     vid_id,
            'title':        snippet['title'],
            'channel':      snippet['channelTitle'],
            'thumbnail':    snippet['thumbnails']['medium']['url'],
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
        query = f"{artist} {song}" if artist else song
        resp  = requests.get(f"{LRCLIB_URL}/search", params={'q': query}, timeout=8)
        results = resp.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    best = next((r for r in results if r.get('plainLyrics')), None) if results else None
    if best:
        return jsonify({
            'lyrics': best['plainLyrics'],
            'artist': best.get('artistName', artist or ''),
            'song':   best.get('trackName',  song),
        })

    # LRCLib found nothing — try n8n AI lyrics fallback
    if N8N_LYRICS_WEBHOOK:
        try:
            n8n_resp = requests.post(
                N8N_LYRICS_WEBHOOK,
                json={'artist': artist or '', 'song': song},
                timeout=15
            )
            if n8n_resp.ok:
                n8n_data = n8n_resp.json()
                if n8n_data.get('lyrics'):
                    return jsonify({
                        'lyrics': n8n_data['lyrics'],
                        'artist': n8n_data.get('artist', artist or ''),
                        'song':   n8n_data.get('song', song),
                        'source': 'ai',
                    })
        except Exception:
            pass

    return jsonify({'error': 'Lyrics not found'}), 404


@app.route('/api/recommendations')
def recommendations():
    artist = request.args.get('artist', '').strip()
    song   = request.args.get('song', '').strip()
    if not song:
        return jsonify({'error': 'song is required'}), 400
    if not OPENAI_API_KEY:
        return jsonify({'recommendations': []}), 200
    try:
        prompt = (
            f'Someone just finished singing "{song}"'
            + (f' by {artist}' if artist else '')
            + '. Suggest 5 other popular karaoke songs they would enjoy. '
            'Return ONLY a JSON array of objects with keys "artist" and "song". No extra text.'
        )
        text = _openai_chat(prompt, max_tokens=300)
        recs = json.loads(text)
        return jsonify({'recommendations': recs[:5]})
    except Exception:
        return jsonify({'recommendations': []}), 200


@app.route('/api/trending')
def trending():
    try:
        if os.path.exists(TRENDING_FILE):
            with open(TRENDING_FILE) as f:
                songs = json.load(f)
            return jsonify({'songs': songs})
    except Exception:
        pass
    return jsonify({'songs': DEFAULT_TRENDING})


@app.route('/api/update-trending', methods=['POST'])
def update_trending():
    secret = request.headers.get('X-Trending-Secret', '')
    if N8N_TRENDING_SECRET and secret != N8N_TRENDING_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401
    data  = request.get_json(silent=True)
    songs = data.get('songs') if data else None
    if not songs or not isinstance(songs, list):
        return jsonify({'error': 'songs array required'}), 400
    try:
        with open(TRENDING_FILE, 'w') as f:
            json.dump(songs, f)
        return jsonify({'ok': True, 'count': len(songs)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)
