from flask import Flask, jsonify, request, render_template, Response
from dotenv import load_dotenv
import requests
import re
import os
import json
import html as _html
import time

load_dotenv()

app = Flask(__name__)

YOUTUBE_API_KEY     = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_SEARCH_URL  = 'https://www.googleapis.com/youtube/v3/search'
LRCLIB_URL          = 'https://lrclib.net/api'
ANTHROPIC_API_KEY   = os.getenv('ANTHROPIC_API_KEY')
N8N_LYRICS_WEBHOOK  = os.getenv('N8N_LYRICS_WEBHOOK')
N8N_TRENDING_SECRET = os.getenv('N8N_TRENDING_SECRET', '')
TRENDING_FILE       = os.path.join(os.path.dirname(__file__), 'trending.json')
YOUTUBE_VIDEOS_URL  = 'https://www.googleapis.com/youtube/v3/videos'
TRENDING_CACHE      = {'songs': None, 'ts': 0}
TRENDING_TTL        = 7200  # 2 hours

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

# Static song pages for SEO — each gets a /sing/<slug> URL indexed by Google
SONG_PAGES = [
    {'artist': 'Queen',             'song': 'Bohemian Rhapsody',              'slug': 'bohemian-rhapsody'},
    {'artist': 'Adele',             'song': 'Hello',                          'slug': 'adele-hello'},
    {'artist': 'Ed Sheeran',        'song': 'Shape of You',                   'slug': 'shape-of-you'},
    {'artist': 'Taylor Swift',      'song': 'Anti-Hero',                      'slug': 'anti-hero'},
    {'artist': 'The Weeknd',        'song': 'Blinding Lights',                'slug': 'blinding-lights'},
    {'artist': 'Journey',           'song': "Don't Stop Believin'",           'slug': 'dont-stop-believin'},
    {'artist': 'Whitney Houston',   'song': 'I Will Always Love You',         'slug': 'i-will-always-love-you'},
    {'artist': 'Billie Eilish',     'song': 'Bad Guy',                        'slug': 'bad-guy'},
    {'artist': 'Celine Dion',       'song': 'My Heart Will Go On',            'slug': 'my-heart-will-go-on'},
    {'artist': 'Coldplay',          'song': 'Yellow',                         'slug': 'coldplay-yellow'},
    {'artist': 'Bon Jovi',          'song': "Livin' on a Prayer",             'slug': 'livin-on-a-prayer'},
    {'artist': 'ABBA',              'song': 'Dancing Queen',                  'slug': 'dancing-queen'},
    {'artist': 'Michael Jackson',   'song': 'Billie Jean',                    'slug': 'billie-jean'},
    {'artist': 'Eminem',            'song': 'Lose Yourself',                  'slug': 'lose-yourself'},
    {'artist': 'Mariah Carey',      'song': 'All I Want for Christmas Is You','slug': 'all-i-want-for-christmas'},
    {'artist': 'Bruno Mars',        'song': 'Just the Way You Are',           'slug': 'just-the-way-you-are'},
    {'artist': 'Katy Perry',        'song': 'Roar',                           'slug': 'katy-perry-roar'},
    {'artist': 'Lady Gaga',         'song': 'Bad Romance',                    'slug': 'bad-romance'},
    {'artist': 'Rihanna',           'song': 'Umbrella',                       'slug': 'rihanna-umbrella'},
    {'artist': 'Beyonce',           'song': 'Halo',                           'slug': 'beyonce-halo'},
    {'artist': 'Pink',              'song': 'Just Give Me a Reason',          'slug': 'just-give-me-a-reason'},
    {'artist': 'Alanis Morissette', 'song': 'Ironic',                         'slug': 'alanis-ironic'},
    {'artist': 'Guns N Roses',      'song': 'Sweet Child O Mine',             'slug': 'sweet-child-o-mine'},
    {'artist': 'Eagles',            'song': 'Hotel California',               'slug': 'hotel-california'},
    {'artist': 'The Beatles',       'song': 'Hey Jude',                       'slug': 'hey-jude'},
    {'artist': 'Elton John',        'song': 'Rocket Man',                     'slug': 'rocket-man'},
    {'artist': 'Rick Astley',       'song': 'Never Gonna Give You Up',        'slug': 'never-gonna-give-you-up'},
    {'artist': 'Imagine Dragons',   'song': 'Radioactive',                    'slug': 'radioactive'},
    {'artist': 'Sam Smith',         'song': 'Stay With Me',                   'slug': 'sam-smith-stay-with-me'},
    {'artist': 'Ariana Grande',     'song': 'Thank U Next',                   'slug': 'thank-u-next'},
    {'artist': 'Dua Lipa',          'song': 'Levitating',                     'slug': 'levitating'},
    {'artist': 'Harry Styles',      'song': 'Watermelon Sugar',               'slug': 'watermelon-sugar'},
    {'artist': 'Olivia Rodrigo',    'song': 'Drivers License',                'slug': 'drivers-license'},
    {'artist': 'Miley Cyrus',       'song': 'Flowers',                        'slug': 'miley-flowers'},
    {'artist': 'Fleetwood Mac',     'song': 'Go Your Own Way',                'slug': 'go-your-own-way'},
    {'artist': 'Don McLean',        'song': 'American Pie',                   'slug': 'american-pie'},
    {'artist': 'Lizzo',             'song': 'Good as Hell',                   'slug': 'good-as-hell'},
    {'artist': 'Post Malone',       'song': 'Circles',                        'slug': 'post-malone-circles'},
    {'artist': 'Shawn Mendes',      'song': 'Treat You Better',               'slug': 'treat-you-better'},
    {'artist': 'David Bowie',       'song': 'Heroes',                         'slug': 'bowie-heroes'},
    # English classics & pop
    {'artist': 'Frank Sinatra',     'song': 'My Way',                         'slug': 'my-way'},
    {'artist': 'Neil Diamond',      'song': 'Sweet Caroline',                 'slug': 'sweet-caroline'},
    {'artist': 'Bon Jovi',          'song': "It's My Life",                   'slug': 'its-my-life'},
    {'artist': 'Aerosmith',         'song': "I Don't Want to Miss a Thing",   'slug': 'dont-wanna-miss-a-thing'},
    {'artist': 'Shania Twain',      'song': 'Man I Feel Like a Woman',        'slug': 'man-i-feel-like-a-woman'},
    {'artist': 'Train',             'song': 'Hey Soul Sister',                'slug': 'hey-soul-sister'},
    {'artist': 'Adele',             'song': 'Rolling in the Deep',            'slug': 'rolling-in-the-deep'},
    {'artist': 'Coldplay',          'song': 'Fix You',                        'slug': 'fix-you'},
    {'artist': 'Bruno Mars',        'song': 'Uptown Funk',                    'slug': 'uptown-funk'},
    {'artist': 'Ed Sheeran',        'song': 'Perfect',                        'slug': 'perfect'},
    {'artist': 'Justin Bieber',     'song': 'Baby',                           'slug': 'justin-bieber-baby'},
    {'artist': 'Lewis Capaldi',     'song': 'Someone You Loved',              'slug': 'someone-you-loved'},
    {'artist': 'Charlie Puth',      'song': 'Attention',                      'slug': 'attention'},
    {'artist': 'Sam Smith',         'song': "I'm Not The Only One",           'slug': 'im-not-the-only-one'},
    {'artist': 'Maroon 5',          'song': 'Sugar',                          'slug': 'maroon-5-sugar'},
    {'artist': 'Post Malone',       'song': 'Sunflower',                      'slug': 'sunflower'},
    {'artist': 'Lizzo',             'song': 'Truth Hurts',                    'slug': 'truth-hurts'},
    {'artist': 'Doja Cat',          'song': 'Say So',                         'slug': 'say-so'},
    # Hindi / Bollywood
    {'artist': 'Arijit Singh',      'song': 'Tum Hi Ho',                      'slug': 'tum-hi-ho'},
    {'artist': 'Arijit Singh',      'song': 'Kesariya',                       'slug': 'kesariya'},
    {'artist': 'Sonu Nigam',        'song': 'Kal Ho Naa Ho',                  'slug': 'kal-ho-naa-ho'},
    {'artist': 'Arijit Singh',      'song': 'Raataan Lambiyan',               'slug': 'raataan-lambiyan'},
    {'artist': 'Shreya Ghoshal',    'song': 'Tujh Mein Rab Dikhta Hai',      'slug': 'tujh-mein-rab'},
    {'artist': 'Atif Aslam',        'song': 'Tera Hone Laga Hoon',           'slug': 'tera-hone-laga-hoon'},
    {'artist': 'Jubin Nautiyal',    'song': 'Lut Gaye',                       'slug': 'lut-gaye'},
    {'artist': 'Kumar Sanu',        'song': 'Dil Deewana',                    'slug': 'dil-deewana'},
    # Filipino / OPM
    {'artist': 'Yeng Constantino',  'song': 'Ikaw',                           'slug': 'ikaw-yeng'},
    {'artist': 'Gary Valenciano',   'song': 'Simpleng Tulad Mo',              'slug': 'simpleng-tulad-mo'},
    {'artist': 'Christian Bautista','song': 'The Way You Look At Me',         'slug': 'christian-bautista-way'},
    {'artist': 'Moira Dela Torre',  'song': 'Paubaya',                        'slug': 'paubaya'},
    {'artist': 'Regine Velasquez',  'song': 'Kung Ikaw Ay Aalis Na',          'slug': 'kung-ikaw-ay-aalis'},
    {'artist': 'Bamboo',            'song': 'Noypi',                          'slug': 'noypi'},
    {'artist': 'Parokya Ni Edgar',  'song': 'Your Song',                      'slug': 'parokya-your-song'},
    {'artist': 'Ben&Ben',           'song': 'Kathang Isip',                   'slug': 'kathang-isip'},
    # K-Pop
    {'artist': 'BTS',               'song': 'Dynamite',                       'slug': 'bts-dynamite'},
    {'artist': 'BTS',               'song': 'Boy With Luv',                   'slug': 'bts-boy-with-luv'},
    {'artist': 'BLACKPINK',         'song': 'How You Like That',              'slug': 'blackpink-how-you-like-that'},
    {'artist': 'BLACKPINK',         'song': 'Kill This Love',                 'slug': 'blackpink-kill-this-love'},
    {'artist': 'IU',                'song': 'Celebrity',                      'slug': 'iu-celebrity'},
    {'artist': 'TWICE',             'song': 'Fancy',                          'slug': 'twice-fancy'},
    {'artist': 'NewJeans',          'song': 'Hype Boy',                       'slug': 'newjeans-hype-boy'},
    {'artist': 'Stray Kids',        'song': "God's Menu",                     'slug': 'stray-kids-gods-menu'},
    # Latin
    {'artist': 'Luis Fonsi',        'song': 'Despacito',                      'slug': 'despacito'},
    {'artist': 'Shakira',           'song': "Hips Don't Lie",                 'slug': 'hips-dont-lie'},
    {'artist': 'Marc Anthony',      'song': 'Vivir Mi Vida',                  'slug': 'vivir-mi-vida'},
    {'artist': 'Enrique Iglesias',  'song': 'Hero',                           'slug': 'enrique-hero'},
    {'artist': 'Camila Cabello',    'song': 'Havana',                         'slug': 'havana'},
    {'artist': 'Bad Bunny',         'song': 'Dakiti',                         'slug': 'dakiti'},
    {'artist': 'Gloria Estefan',    'song': 'Conga',                          'slug': 'conga'},
    {'artist': 'Carlos Santana',    'song': 'Smooth',                         'slug': 'santana-smooth'},
    # Chinese / Mandarin
    {'artist': 'Jay Chou',          'song': 'Qinghua Ci',                     'slug': 'qinghua-ci'},
    {'artist': 'Teresa Teng',       'song': 'Tian Mi Mi',                     'slug': 'tian-mi-mi'},
    {'artist': 'Jay Chou',          'song': 'Qilixiang',                      'slug': 'qilixiang'},
    {'artist': 'G.E.M.',            'song': 'Light Years Away',               'slug': 'gem-light-years-away'},
    # Japanese
    {'artist': 'Hikaru Utada',      'song': 'First Love',                     'slug': 'first-love-utada'},
    {'artist': 'Aimyon',            'song': 'Marigold',                       'slug': 'marigold-aimyon'},
    {'artist': 'YOASOBI',           'song': 'Idol',                           'slug': 'yoasobi-idol'},
    {'artist': 'Official HIGE DANdism', 'song': 'Pretender',                  'slug': 'pretender-higedan'},
]
_SONG_BY_SLUG = {s['slug']: s for s in SONG_PAGES}


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


def _claude_chat(prompt, max_tokens=256):
    """Call Anthropic Claude, returns text or raises."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=max_tokens,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return msg.content[0].text.strip()


def parse_song_info(video_title):
    """Extract artist and song name using Claude, falling back to regex."""
    if not ANTHROPIC_API_KEY:
        return _regex_parse(video_title)
    try:
        text = _claude_chat(
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


@app.route('/sing/<slug>')
def song_page(slug):
    song = _SONG_BY_SLUG.get(slug)
    if not song:
        return render_template('index.html'), 404
    return render_template('song.html', **song)


@app.route('/robots.txt')
def robots():
    content = (
        'User-agent: *\n'
        'Allow: /\n'
        'Disallow: /api/\n'
        'Sitemap: https://www.karaokelover.com/sitemap.xml\n'
    )
    return Response(content, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap():
    urls = [
        '<url><loc>https://www.karaokelover.com/</loc>'
        '<changefreq>weekly</changefreq><priority>1.0</priority></url>'
    ]
    for s in SONG_PAGES:
        urls.append(
            f'<url><loc>https://www.karaokelover.com/sing/{s["slug"]}</loc>'
            f'<changefreq>monthly</changefreq><priority>0.8</priority></url>'
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(f'  {u}' for u in urls)
        + '\n</urlset>'
    )
    return Response(xml, mimetype='application/xml')


@app.route('/api/search')
def search():
    query    = request.args.get('q', '').strip()
    language = request.args.get('language', '').strip()
    region   = request.args.get('region', '').strip()
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
        'videoEmbeddable': 'true',
        'videoSyndicated': 'true',
    }
    if language:
        params['relevanceLanguage'] = language
    if region:
        params['regionCode'] = region

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
            'title':        _html.unescape(snippet['title']),
            'channel':      _html.unescape(snippet['channelTitle']),
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
    if not ANTHROPIC_API_KEY:
        return jsonify({'recommendations': []}), 200
    try:
        prompt = (
            f'Someone just finished singing "{song}"'
            + (f' by {artist}' if artist else '')
            + '. Suggest 5 other popular karaoke songs they would enjoy. '
            'Return ONLY a JSON array of objects with keys "artist" and "song". No extra text.'
        )
        text = _claude_chat(prompt, max_tokens=300)
        recs = json.loads(text)
        return jsonify({'recommendations': recs[:5]})
    except Exception:
        return jsonify({'recommendations': []}), 200


def _fetch_youtube_trending():
    """Fetch top music videos from YouTube mostPopular chart, extract artist/song."""
    if not YOUTUBE_API_KEY:
        return None
    try:
        resp = requests.get(YOUTUBE_VIDEOS_URL, params={
            'key': YOUTUBE_API_KEY,
            'chart': 'mostPopular',
            'videoCategoryId': '10',  # Music
            'regionCode': 'US',
            'maxResults': 12,
            'part': 'snippet',
        }, timeout=8)
        items = resp.json().get('items', [])
        songs = []
        for item in items:
            title = _html.unescape(item['snippet']['title'])
            artist, song = _regex_parse(title)
            if song:
                songs.append({'artist': artist or '', 'song': song})
        return songs[:10] if songs else None
    except Exception:
        return None


@app.route('/api/trending')
def trending():
    now = time.time()
    # Return cached result if still fresh
    if TRENDING_CACHE['songs'] and now - TRENDING_CACHE['ts'] < TRENDING_TTL:
        return jsonify({'songs': TRENDING_CACHE['songs']})

    # Try live YouTube chart first
    live = _fetch_youtube_trending()
    if live:
        TRENDING_CACHE['songs'] = live
        TRENDING_CACHE['ts'] = now
        return jsonify({'songs': live})

    # Fall back to manually curated trending.json or defaults
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
