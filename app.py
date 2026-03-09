from flask import Flask, jsonify, request, render_template, Response
from dotenv import load_dotenv
import requests
import re
import os
import json
import html as _html
import time
import threading
import datetime

load_dotenv()

app = Flask(__name__)

YOUTUBE_SEARCH_URL  = 'https://www.googleapis.com/youtube/v3/search'
LRCLIB_URL          = 'https://lrclib.net/api'
ANTHROPIC_API_KEY   = os.getenv('ANTHROPIC_API_KEY')
N8N_LYRICS_WEBHOOK  = os.getenv('N8N_LYRICS_WEBHOOK')
N8N_TRENDING_SECRET = os.getenv('N8N_TRENDING_SECRET', '')
# Persistent data directory — set RAILWAY_DATA_DIR=/data in Railway env vars
# and mount a Railway volume at /data so caches survive across deploys.
# Falls back to the app directory if the env var isn't set.
_DATA_DIR     = os.getenv('RAILWAY_DATA_DIR', os.path.dirname(__file__))
TRENDING_FILE = os.path.join(_DATA_DIR, 'trending.json')

# YouTube API key rotation — add YOUTUBE_API_KEY_2 … _8 in Railway env vars
# for automatic failover when a key's daily quota is exhausted
_ALL_YT_KEYS = [k for k in [
    os.getenv('YOUTUBE_API_KEY'),
    os.getenv('YOUTUBE_API_KEY_2'),
    os.getenv('YOUTUBE_API_KEY_3'),
    os.getenv('YOUTUBE_API_KEY_4'),
    os.getenv('YOUTUBE_API_KEY_5'),
    os.getenv('YOUTUBE_API_KEY_6'),
    os.getenv('YOUTUBE_API_KEY_7'),
    os.getenv('YOUTUBE_API_KEY_8'),
] if k]
EXHAUSTED_KEYS_FILE = os.path.join(_DATA_DIR, 'exhausted_keys.json')
QUOTA_RESET_SECS    = 24 * 3600  # YouTube quota resets every 24 h

def _load_exhausted_keys():
    """Load exhausted key timestamps from disk; drop entries older than 24h."""
    try:
        if os.path.exists(EXHAUSTED_KEYS_FILE):
            with open(EXHAUSTED_KEYS_FILE) as f:
                raw = json.load(f)
            now = time.time()
            return {k: v for k, v in raw.items() if now - v < QUOTA_RESET_SECS}
    except Exception:
        pass
    return {}

EXHAUSTED_KEYS = _load_exhausted_keys()

def _get_active_key():
    """Return first key whose quota hasn't run out (or was exhausted >24h ago)."""
    now = time.time()
    for key in _ALL_YT_KEYS:
        if now - EXHAUSTED_KEYS.get(key, 0) > QUOTA_RESET_SECS:
            return key
    return None  # all keys exhausted

def _mark_exhausted(key):
    EXHAUSTED_KEYS[key] = time.time()
    try:
        with open(EXHAUSTED_KEYS_FILE, 'w') as f:
            json.dump(EXHAUSTED_KEYS, f)
    except Exception:
        pass


# ── Persistent cache ────────────────────────────────────────────────────────

def _load_cache():
    """Load search cache from disk on startup; discard expired entries."""
    global SEARCH_CACHE
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                raw = json.load(f)
            now = time.time()
            SEARCH_CACHE = {k: v for k, v in raw.items()
                            if now - v.get('ts', 0) < SEARCH_CACHE_TTL}
            print(f'[cache] Loaded {len(SEARCH_CACHE)} fresh entries from disk', flush=True)
    except Exception as e:
        print(f'[cache] Load error: {e}', flush=True)
        SEARCH_CACHE = {}


def _save_cache():
    """Persist search cache to disk."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(SEARCH_CACHE, f)
    except Exception as e:
        print(f'[cache] Save error: {e}', flush=True)


# ── Pre-warm ────────────────────────────────────────────────────────────────

def _prewarm_one(artist, song):
    """Fetch one song's karaoke results and store in cache. Returns True if API was called."""
    query     = f'{artist} {song}'
    cache_key = f'{query.lower()}|||'   # matches search route: query|language|region|era
    now       = time.time()
    cached    = SEARCH_CACHE.get(cache_key)
    # Skip if cached and still has >1 day of TTL remaining
    if cached and now - cached['ts'] < SEARCH_CACHE_TTL - 86400:
        return False
    params = {
        'q': f'{query} karaoke', 'part': 'snippet', 'type': 'video',
        'videoCategoryId': '10', 'maxResults': 20, 'order': 'relevance',
        'videoEmbeddable': 'true', 'videoSyndicated': 'true',
    }
    data, _ = _youtube_search(params)
    if data is None:
        return False
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
    if len(SEARCH_CACHE) >= SEARCH_CACHE_MAX:
        oldest = min(SEARCH_CACHE, key=lambda k: SEARCH_CACHE[k]['ts'])
        del SEARCH_CACHE[oldest]
    SEARCH_CACHE[cache_key] = {'results': results, 'ts': now}
    return True


def _prewarm_worker():
    """Background thread: warm top songs on startup, then re-warm stale entries at 2am UTC."""
    time.sleep(30)  # let app fully start first

    # ── Startup warm: top PREWARM_SONGS ──────────────────────────────────
    print(f'[prewarm] Startup warm: checking top {PREWARM_SONGS} songs…', flush=True)
    warmed = 0
    for song in SONG_PAGES[:PREWARM_SONGS]:
        try:
            if _prewarm_one(song['artist'], song['song']):
                warmed += 1
                time.sleep(3)   # 3s gap → ~150 quota units/min, well within limits
        except Exception as e:
            print(f'[prewarm] Error warming {song["song"]}: {e}', flush=True)
    if warmed:
        _save_cache()
    print(f'[prewarm] Startup done — {warmed} new entries fetched', flush=True)

    # ── Daily re-warm at 2am UTC ─────────────────────────────────────────
    while True:
        now_dt   = datetime.datetime.utcnow()
        next_2am = now_dt.replace(hour=2, minute=0, second=0, microsecond=0)
        if now_dt >= next_2am:
            next_2am += datetime.timedelta(days=1)
        wait_secs = (next_2am - now_dt).total_seconds()
        print(f'[prewarm] Next daily warm in {wait_secs/3600:.1f}h', flush=True)
        time.sleep(wait_secs)

        print('[prewarm] Daily re-warm starting…', flush=True)
        rewarmed = 0
        for song in SONG_PAGES:
            try:
                if _prewarm_one(song['artist'], song['song']):
                    rewarmed += 1
                    time.sleep(3)
            except Exception as e:
                print(f'[prewarm] Error: {e}', flush=True)
        if rewarmed:
            _save_cache()
        print(f'[prewarm] Daily warm done — {rewarmed} re-fetched', flush=True)


def _youtube_search(params):
    """Try each API key in order; rotate on quota error. Returns (data, err_msg)."""
    now = time.time()
    for key in _ALL_YT_KEYS:
        if now - EXHAUSTED_KEYS.get(key, 0) <= QUOTA_RESET_SECS:
            continue  # still exhausted, skip
        params['key'] = key
        try:
            resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10)
            data = resp.json()
        except Exception as e:
            return None, str(e)
        if 'error' in data:
            err = data['error']
            reasons = [e.get('reason', '') for e in err.get('errors', [])]
            if err.get('code') == 403 or 'quotaExceeded' in reasons:
                _mark_exhausted(key)
                continue  # try next key
            return None, 'YouTube search failed. Please try again.'
        return data, None
    return None, 'quota'

# Search result cache — avoids burning quota on repeated queries
SEARCH_CACHE     = {}          # key → {'results': [...], 'ts': float}
SEARCH_CACHE_TTL = 30 * 24 * 3600  # 30 days (karaoke results barely change)
SEARCH_CACHE_MAX = 5000            # generous limit; ~5MB RAM for 5000 entries
CACHE_FILE       = os.path.join(_DATA_DIR, 'search_cache.json')
PREWARM_SONGS    = 50              # warm top N songs on startup (100 units each; keep low to preserve quota)

# In-flight deduplication — prevents thundering herd:
# if 100 users hit the same uncached query simultaneously, only 1 API call is made
_INFLIGHT      = {}   # cache_key → threading.Event
_INFLIGHT_LOCK = threading.Lock()

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
    # Classic Rock Legends
    {'artist': 'The Beatles',       'song': 'Let It Be',                      'slug': 'let-it-be'},
    {'artist': 'The Beatles',       'song': 'Yesterday',                      'slug': 'yesterday'},
    {'artist': 'The Beatles',       'song': 'Come Together',                  'slug': 'come-together'},
    {'artist': 'Queen',             'song': "Don't Stop Me Now",              'slug': 'dont-stop-me-now'},
    {'artist': 'Queen',             'song': 'We Will Rock You',               'slug': 'we-will-rock-you'},
    {'artist': 'Queen',             'song': 'We Are the Champions',           'slug': 'we-are-the-champions'},
    {'artist': 'Led Zeppelin',      'song': 'Stairway to Heaven',             'slug': 'stairway-to-heaven'},
    {'artist': 'The Rolling Stones','song': 'Paint It Black',                 'slug': 'paint-it-black'},
    {'artist': 'Oasis',             'song': 'Wonderwall',                     'slug': 'wonderwall'},
    {'artist': 'The Killers',       'song': 'Mr. Brightside',                 'slug': 'mr-brightside'},
    {'artist': 'Nirvana',           'song': 'Smells Like Teen Spirit',        'slug': 'smells-like-teen-spirit'},
    {'artist': 'Radiohead',         'song': 'Creep',                          'slug': 'creep'},
    {'artist': 'Green Day',         'song': 'Good Riddance (Time of Your Life)', 'slug': 'good-riddance'},
    {'artist': 'Linkin Park',       'song': 'In the End',                     'slug': 'in-the-end'},
    {'artist': 'Linkin Park',       'song': 'Numb',                           'slug': 'linkin-park-numb'},
    {'artist': 'U2',                'song': 'With or Without You',            'slug': 'with-or-without-you'},
    {'artist': 'Toto',              'song': 'Africa',                         'slug': 'africa'},
    # 80s Pop
    {'artist': 'A-ha',              'song': 'Take On Me',                     'slug': 'take-on-me'},
    {'artist': 'George Michael',    'song': 'Careless Whisper',               'slug': 'careless-whisper'},
    {'artist': 'George Michael',    'song': 'Faith',                          'slug': 'george-michael-faith'},
    {'artist': 'Madonna',           'song': 'Like a Prayer',                  'slug': 'like-a-prayer'},
    {'artist': 'Madonna',           'song': 'Material Girl',                  'slug': 'material-girl'},
    {'artist': 'Cyndi Lauper',      'song': 'Girls Just Want to Have Fun',    'slug': 'girls-just-want-to-have-fun'},
    {'artist': 'Cyndi Lauper',      'song': 'Time After Time',                'slug': 'time-after-time'},
    {'artist': 'Billy Joel',        'song': 'Piano Man',                      'slug': 'piano-man'},
    {'artist': 'The Police',        'song': 'Every Breath You Take',          'slug': 'every-breath-you-take'},
    {'artist': 'Stevie Wonder',     'song': 'Superstition',                   'slug': 'superstition'},
    {'artist': 'Bonnie Tyler',      'song': 'Total Eclipse of the Heart',     'slug': 'total-eclipse-of-the-heart'},
    {'artist': 'Elton John',        'song': 'Tiny Dancer',                    'slug': 'tiny-dancer'},
    {'artist': 'Michael Jackson',   'song': 'Thriller',                       'slug': 'thriller'},
    {'artist': 'Michael Jackson',   'song': 'Man in the Mirror',              'slug': 'man-in-the-mirror'},
    # 90s Pop
    {'artist': 'Britney Spears',    'song': 'Baby One More Time',             'slug': 'baby-one-more-time'},
    {'artist': 'Britney Spears',    'song': 'Oops I Did It Again',            'slug': 'oops-i-did-it-again'},
    {'artist': 'Britney Spears',    'song': 'Toxic',                          'slug': 'britney-toxic'},
    {'artist': 'Spice Girls',       'song': 'Wannabe',                        'slug': 'wannabe'},
    {'artist': 'Backstreet Boys',   'song': 'I Want It That Way',             'slug': 'i-want-it-that-way'},
    {'artist': "N'Sync",            'song': 'Bye Bye Bye',                    'slug': 'bye-bye-bye'},
    {'artist': 'Christina Aguilera','song': 'Beautiful',                      'slug': 'beautiful-aguilera'},
    {'artist': 'No Doubt',          'song': "Don't Speak",                    'slug': 'dont-speak'},
    {"artist": "Destiny's Child",   'song': 'Say My Name',                    'slug': 'say-my-name'},
    {'artist': 'Celine Dion',       'song': 'Because You Loved Me',           'slug': 'because-you-loved-me'},
    {'artist': 'Mariah Carey',      'song': 'Fantasy',                        'slug': 'mariah-fantasy'},
    # 2000s
    {'artist': 'Kelly Clarkson',    'song': 'Since U Been Gone',              'slug': 'since-u-been-gone'},
    {'artist': 'Kelly Clarkson',    'song': 'Stronger',                       'slug': 'kelly-clarkson-stronger'},
    {'artist': 'Amy Winehouse',     'song': 'Rehab',                          'slug': 'rehab'},
    {'artist': 'Amy Winehouse',     'song': 'Back to Black',                  'slug': 'back-to-black'},
    {'artist': 'John Legend',       'song': 'All of Me',                      'slug': 'all-of-me'},
    {'artist': 'Gotye',             'song': 'Somebody That I Used to Know',   'slug': 'somebody-that-i-used-to-know'},
    {'artist': 'Jason Mraz',        'song': "I'm Yours",                      'slug': 'im-yours'},
    {'artist': 'Justin Timberlake', 'song': 'SexyBack',                       'slug': 'sexyback'},
    {'artist': 'Beyonce',           'song': 'Crazy in Love',                  'slug': 'crazy-in-love'},
    {'artist': 'Beyonce',           'song': 'Single Ladies',                  'slug': 'single-ladies'},
    {'artist': 'Usher',             'song': 'Yeah!',                          'slug': 'usher-yeah'},
    {'artist': 'Alicia Keys',       'song': 'No One',                         'slug': 'alicia-keys-no-one'},
    {'artist': 'Black Eyed Peas',   'song': 'I Gotta Feeling',               'slug': 'i-gotta-feeling'},
    # 2010s
    {'artist': 'Adele',             'song': 'Someone Like You',               'slug': 'someone-like-you'},
    {'artist': 'Adele',             'song': 'Set Fire to the Rain',           'slug': 'set-fire-to-the-rain'},
    {'artist': 'Adele',             'song': 'Skyfall',                        'slug': 'skyfall'},
    {'artist': 'Taylor Swift',      'song': 'Love Story',                     'slug': 'love-story'},
    {'artist': 'Taylor Swift',      'song': 'Shake It Off',                   'slug': 'shake-it-off'},
    {'artist': 'Taylor Swift',      'song': 'Blank Space',                    'slug': 'blank-space'},
    {'artist': 'Taylor Swift',      'song': 'Cruel Summer',                   'slug': 'cruel-summer'},
    {'artist': 'Taylor Swift',      'song': 'You Belong With Me',             'slug': 'you-belong-with-me'},
    {'artist': 'Katy Perry',        'song': 'Firework',                       'slug': 'firework'},
    {'artist': 'Katy Perry',        'song': 'Teenage Dream',                  'slug': 'teenage-dream'},
    {'artist': 'Sia',               'song': 'Chandelier',                     'slug': 'chandelier'},
    {'artist': 'Sia',               'song': 'Cheap Thrills',                  'slug': 'cheap-thrills'},
    {'artist': 'Sam Smith',         'song': "Writing's on the Wall",          'slug': 'writings-on-the-wall'},
    {'artist': 'James Arthur',      'song': "Say You Won't Let Go",           'slug': 'say-you-wont-let-go'},
    {'artist': 'One Direction',     'song': 'What Makes You Beautiful',       'slug': 'what-makes-you-beautiful'},
    {'artist': 'Charlie Puth',      'song': 'One Call Away',                  'slug': 'one-call-away'},
    {'artist': 'Meghan Trainor',    'song': 'All About That Bass',            'slug': 'all-about-that-bass'},
    {'artist': 'Lady Gaga',         'song': 'Poker Face',                     'slug': 'poker-face'},
    {'artist': 'Lady Gaga',         'song': 'Born This Way',                  'slug': 'born-this-way'},
    {'artist': 'Rihanna',           'song': 'We Found Love',                  'slug': 'we-found-love'},
    {'artist': 'Rihanna',           'song': 'Diamonds',                       'slug': 'rihanna-diamonds'},
    {'artist': 'Ed Sheeran',        'song': 'Thinking Out Loud',              'slug': 'thinking-out-loud'},
    {'artist': 'Ed Sheeran',        'song': 'Photograph',                     'slug': 'ed-sheeran-photograph'},
    {'artist': 'The Weeknd',        'song': "Can't Feel My Face",             'slug': 'cant-feel-my-face'},
    {'artist': 'The Weeknd',        'song': 'Starboy',                        'slug': 'starboy'},
    {'artist': 'The Weeknd',        'song': 'Save Your Tears',                'slug': 'save-your-tears'},
    {'artist': 'Bruno Mars',        'song': 'Grenade',                        'slug': 'grenade'},
    {'artist': 'Bruno Mars',        'song': 'When I Was Your Man',            'slug': 'when-i-was-your-man'},
    {'artist': 'Justin Bieber',     'song': 'Love Yourself',                  'slug': 'love-yourself'},
    {'artist': 'Ariana Grande',     'song': 'Problem',                        'slug': 'ariana-problem'},
    {'artist': 'Ariana Grande',     'song': '7 rings',                        'slug': 'ariana-7-rings'},
    {'artist': 'Dua Lipa',          'song': 'New Rules',                      'slug': 'new-rules'},
    {'artist': 'Dua Lipa',          'song': "Don't Start Now",                'slug': 'dont-start-now'},
    {'artist': 'Selena Gomez',      'song': 'Lose You to Love Me',            'slug': 'lose-you-to-love-me'},
    # 2020s
    {'artist': 'Harry Styles',      'song': 'As It Was',                      'slug': 'as-it-was'},
    {'artist': 'Olivia Rodrigo',    'song': 'Good 4 U',                       'slug': 'good-4-u'},
    {'artist': 'Olivia Rodrigo',    'song': 'vampire',                        'slug': 'olivia-vampire'},
    {'artist': 'Tones and I',       'song': 'Dance Monkey',                   'slug': 'dance-monkey'},
    {'artist': 'Sabrina Carpenter', 'song': 'Espresso',                       'slug': 'espresso'},
    {'artist': 'Glass Animals',     'song': 'Heat Waves',                     'slug': 'heat-waves'},
    {'artist': 'Billie Eilish',     'song': 'Happier Than Ever',              'slug': 'happier-than-ever'},
    # R&B / Soul Classics
    {'artist': 'Bill Withers',      'song': 'Lean on Me',                     'slug': 'lean-on-me'},
    {'artist': 'Ben E. King',       'song': 'Stand By Me',                    'slug': 'stand-by-me'},
    {'artist': 'Earth Wind & Fire', 'song': 'September',                      'slug': 'september'},
    {'artist': 'Stevie Wonder',     'song': "Isn't She Lovely",               'slug': 'isnt-she-lovely'},
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
    # ── More Pop Hits ──────────────────────────────────────────────────────
    {'artist': 'Taylor Swift',      'song': 'Style',                          'slug': 'taylor-style'},
    {'artist': 'Taylor Swift',      'song': 'Fearless',                       'slug': 'taylor-fearless'},
    {'artist': 'Taylor Swift',      'song': 'Red',                            'slug': 'taylor-red'},
    {'artist': 'Taylor Swift',      'song': 'Wildest Dreams',                 'slug': 'wildest-dreams'},
    {'artist': 'Taylor Swift',      'song': 'Cardigan',                       'slug': 'cardigan'},
    {'artist': 'Taylor Swift',      'song': 'August',                         'slug': 'august-taylor'},
    {'artist': 'Taylor Swift',      'song': 'All Too Well',                   'slug': 'all-too-well'},
    {'artist': 'Taylor Swift',      'song': 'Enchanted',                      'slug': 'enchanted'},
    {'artist': 'Ariana Grande',     'song': 'No Tears Left to Cry',          'slug': 'no-tears-left-to-cry'},
    {'artist': 'Ariana Grande',     'song': 'Into You',                       'slug': 'into-you'},
    {'artist': 'Ariana Grande',     'song': 'God Is a Woman',                 'slug': 'god-is-a-woman'},
    {'artist': 'Ariana Grande',     'song': 'positions',                      'slug': 'ariana-positions'},
    {'artist': 'Billie Eilish',     'song': 'Ocean Eyes',                     'slug': 'ocean-eyes'},
    {'artist': 'Billie Eilish',     'song': 'When the Party\'s Over',         'slug': 'when-the-partys-over'},
    {'artist': 'Billie Eilish',     'song': 'Lovely',                         'slug': 'lovely'},
    {'artist': 'Billie Eilish',     'song': 'What Was I Made For',            'slug': 'what-was-i-made-for'},
    {'artist': 'Olivia Rodrigo',    'song': 'brutal',                         'slug': 'brutal-olivia'},
    {'artist': 'Olivia Rodrigo',    'song': 'traitor',                        'slug': 'traitor-olivia'},
    {'artist': 'Olivia Rodrigo',    'song': 'deja vu',                        'slug': 'deja-vu-olivia'},
    {'artist': 'Olivia Rodrigo',    'song': 'favorite crime',                 'slug': 'favorite-crime'},
    {'artist': 'Dua Lipa',          'song': 'Physical',                       'slug': 'dua-physical'},
    {'artist': 'Dua Lipa',          'song': 'Be the One',                     'slug': 'be-the-one'},
    {'artist': 'Dua Lipa',          'song': 'IDGAF',                          'slug': 'dua-idgaf'},
    {'artist': 'Harry Styles',      'song': 'Adore You',                      'slug': 'adore-you'},
    {'artist': 'Harry Styles',      'song': 'Sign of the Times',              'slug': 'sign-of-the-times'},
    {'artist': 'Harry Styles',      'song': 'Golden',                         'slug': 'golden-harry'},
    {'artist': 'Ed Sheeran',        'song': 'Castle on the Hill',             'slug': 'castle-on-the-hill'},
    {'artist': 'Ed Sheeran',        'song': 'Galway Girl',                    'slug': 'galway-girl'},
    {'artist': 'Ed Sheeran',        'song': 'Happier',                        'slug': 'ed-happier'},
    {'artist': 'Ed Sheeran',        'song': 'Bad Habits',                     'slug': 'bad-habits'},
    {'artist': 'Ed Sheeran',        'song': 'Overpass Graffiti',              'slug': 'overpass-graffiti'},
    {'artist': 'Justin Bieber',     'song': 'Sorry',                          'slug': 'sorry-bieber'},
    {'artist': 'Justin Bieber',     'song': 'What Do You Mean',               'slug': 'what-do-you-mean'},
    {'artist': 'Justin Bieber',     'song': 'Peaches',                        'slug': 'peaches-bieber'},
    {'artist': 'Justin Bieber',     'song': 'Ghost',                          'slug': 'ghost-bieber'},
    {'artist': 'Selena Gomez',      'song': 'Same Old Love',                  'slug': 'same-old-love'},
    {'artist': 'Selena Gomez',      'song': 'Bad Liar',                       'slug': 'bad-liar'},
    {'artist': 'Selena Gomez',      'song': 'Wolves',                         'slug': 'wolves-selena'},
    {'artist': 'Selena Gomez',      'song': 'Come & Get It',                  'slug': 'come-and-get-it'},
    {'artist': 'Miley Cyrus',       'song': 'Wrecking Ball',                  'slug': 'wrecking-ball'},
    {'artist': 'Miley Cyrus',       'song': 'The Climb',                      'slug': 'the-climb'},
    {'artist': 'Miley Cyrus',       'song': 'Party in the USA',               'slug': 'party-in-the-usa'},
    {'artist': 'Sabrina Carpenter', 'song': 'Please Please Please',           'slug': 'please-please-please'},
    {'artist': 'Sabrina Carpenter', 'song': 'Feather',                        'slug': 'feather'},
    {'artist': 'Gracie Abrams',     'song': 'That\'s So True',                'slug': 'thats-so-true'},
    {'artist': 'Chappell Roan',     'song': 'Hot to Go',                      'slug': 'hot-to-go'},
    {'artist': 'Chappell Roan',     'song': 'Good Luck Babe',                 'slug': 'good-luck-babe'},
    {'artist': 'Charli XCX',        'song': 'Boom Clap',                      'slug': 'boom-clap'},
    {'artist': 'Charli XCX',        'song': 'Break the Rules',                'slug': 'break-the-rules'},
    {'artist': 'SZA',               'song': 'Good Days',                      'slug': 'sza-good-days'},
    {'artist': 'SZA',               'song': 'Kill Bill',                      'slug': 'sza-kill-bill'},
    {'artist': 'SZA',               'song': 'Snooze',                         'slug': 'sza-snooze'},
    {'artist': 'Khalid',            'song': 'Young Dumb & Broke',             'slug': 'young-dumb-and-broke'},
    {'artist': 'Khalid',            'song': 'Talk',                           'slug': 'khalid-talk'},
    {'artist': 'Halsey',            'song': 'Without Me',                     'slug': 'without-me-halsey'},
    {'artist': 'Halsey',            'song': 'Colors',                         'slug': 'colors-halsey'},
    {'artist': 'Camila Cabello',    'song': 'Crying in the Club',             'slug': 'crying-in-the-club'},
    {'artist': 'Camila Cabello',    'song': 'Never Be the Same',              'slug': 'never-be-the-same'},
    {'artist': 'Lana Del Rey',      'song': 'Summertime Sadness',             'slug': 'summertime-sadness'},
    {'artist': 'Lana Del Rey',      'song': 'Video Games',                    'slug': 'video-games-lana'},
    {'artist': 'Lana Del Rey',      'song': 'Young and Beautiful',            'slug': 'young-and-beautiful'},
    {'artist': 'Lana Del Rey',      'song': 'Born to Die',                    'slug': 'born-to-die'},
    {'artist': 'Troye Sivan',       'song': 'Rush',                           'slug': 'troye-rush'},
    {'artist': 'Troye Sivan',       'song': 'Heaven',                         'slug': 'troye-heaven'},
    {'artist': 'Shawn Mendes',      'song': 'Mercy',                          'slug': 'shawn-mercy'},
    {'artist': 'Shawn Mendes',      'song': 'In My Blood',                    'slug': 'in-my-blood'},
    {'artist': 'Shawn Mendes',      'song': 'Stitches',                       'slug': 'stitches'},
    {'artist': 'Niall Horan',       'song': 'Slow Hands',                     'slug': 'slow-hands'},
    {'artist': 'Niall Horan',       'song': 'This Town',                      'slug': 'this-town'},
    # ── More Rock & Alternative ─────────────────────────────────────────────
    {'artist': 'Foo Fighters',      'song': 'Best of You',                    'slug': 'best-of-you'},
    {'artist': 'Foo Fighters',      'song': 'Everlong',                       'slug': 'everlong'},
    {'artist': 'Foo Fighters',      'song': 'Learn to Fly',                   'slug': 'learn-to-fly'},
    {'artist': 'Coldplay',          'song': 'The Scientist',                  'slug': 'the-scientist'},
    {'artist': 'Coldplay',          'song': 'Clocks',                         'slug': 'clocks'},
    {'artist': 'Coldplay',          'song': 'Viva la Vida',                   'slug': 'viva-la-vida'},
    {'artist': 'Coldplay',          'song': 'A Sky Full of Stars',            'slug': 'sky-full-of-stars'},
    {'artist': 'Coldplay',          'song': 'Something Just Like This',       'slug': 'something-just-like-this'},
    {'artist': 'Muse',              'song': 'Madness',                        'slug': 'madness-muse'},
    {'artist': 'Muse',              'song': 'Uprising',                       'slug': 'uprising-muse'},
    {'artist': 'Arctic Monkeys',    'song': 'Do I Wanna Know',                'slug': 'do-i-wanna-know'},
    {'artist': 'Arctic Monkeys',    'song': 'R U Mine',                       'slug': 'r-u-mine'},
    {'artist': 'Arctic Monkeys',    'song': 'I Wanna Be Yours',               'slug': 'i-wanna-be-yours'},
    {'artist': 'The 1975',          'song': 'Chocolate',                      'slug': 'chocolate-1975'},
    {'artist': 'The 1975',          'song': 'Love It If We Made It',          'slug': 'love-it-if-we-made-it'},
    {'artist': 'Fall Out Boy',      'song': 'Sugar We\'re Going Down',        'slug': 'sugar-were-going-down'},
    {'artist': 'Fall Out Boy',      'song': 'Centuries',                      'slug': 'centuries'},
    {'artist': 'Panic! at the Disco','song': 'I Write Sins Not Tragedies',    'slug': 'i-write-sins'},
    {'artist': 'Panic! at the Disco','song': 'High Hopes',                    'slug': 'high-hopes'},
    {'artist': 'My Chemical Romance','song': 'Welcome to the Black Parade',   'slug': 'welcome-to-the-black-parade'},
    {'artist': 'My Chemical Romance','song': 'I\'m Not Okay',                 'slug': 'im-not-okay'},
    {'artist': 'Twenty One Pilots', 'song': 'Stressed Out',                   'slug': 'stressed-out'},
    {'artist': 'Twenty One Pilots', 'song': 'Ride',                           'slug': 'ride-top'},
    {'artist': 'Twenty One Pilots', 'song': 'Heathens',                       'slug': 'heathens'},
    {'artist': 'Paramore',          'song': 'Still Into You',                 'slug': 'still-into-you'},
    {'artist': 'Paramore',          'song': 'The Only Exception',             'slug': 'the-only-exception'},
    {'artist': 'Paramore',          'song': 'Decode',                         'slug': 'decode'},
    {'artist': 'Matchbox Twenty',   'song': '3 AM',                           'slug': '3am-matchbox'},
    {'artist': 'Snow Patrol',       'song': 'Chasing Cars',                   'slug': 'chasing-cars'},
    {'artist': 'OneRepublic',       'song': 'Apologize',                      'slug': 'apologize'},
    {'artist': 'OneRepublic',       'song': 'Counting Stars',                 'slug': 'counting-stars'},
    {'artist': 'Maroon 5',          'song': 'Moves Like Jagger',              'slug': 'moves-like-jagger'},
    {'artist': 'Maroon 5',          'song': 'She Will Be Loved',              'slug': 'she-will-be-loved'},
    {'artist': 'Maroon 5',          'song': 'Maps',                           'slug': 'maps-maroon'},
    {'artist': 'Train',             'song': 'Drops of Jupiter',               'slug': 'drops-of-jupiter'},
    {'artist': 'The Lumineers',     'song': 'Ho Hey',                         'slug': 'ho-hey'},
    {'artist': 'The Lumineers',     'song': 'Ophelia',                        'slug': 'ophelia-lumineers'},
    {'artist': 'Vance Joy',         'song': 'Riptide',                        'slug': 'riptide'},
    {'artist': 'Hozier',            'song': 'Take Me to Church',              'slug': 'take-me-to-church'},
    {'artist': 'Hozier',            'song': 'From Eden',                      'slug': 'from-eden'},
    {'artist': 'James Bay',         'song': 'Hold Back the River',            'slug': 'hold-back-the-river'},
    {'artist': 'James Bay',         'song': 'Let It Go',                      'slug': 'james-bay-let-it-go'},
    {'artist': 'Bon Iver',          'song': 'Skinny Love',                    'slug': 'skinny-love'},
    {'artist': 'Sufjan Stevens',    'song': 'Mystery of Love',                'slug': 'mystery-of-love'},
    # ── More R&B / Soul ─────────────────────────────────────────────────────
    {'artist': 'Beyonce',           'song': 'Lemonade',                       'slug': 'beyonce-lemonade'},
    {'artist': 'Beyonce',           'song': 'Love On Top',                    'slug': 'love-on-top'},
    {'artist': 'Beyonce',           'song': 'Drunk in Love',                  'slug': 'drunk-in-love'},
    {'artist': 'Frank Ocean',       'song': 'Thinking Bout You',              'slug': 'thinking-bout-you'},
    {'artist': 'Frank Ocean',       'song': 'Chanel',                         'slug': 'chanel-frank'},
    {'artist': 'The Weeknd',        'song': 'Earned It',                      'slug': 'earned-it'},
    {'artist': 'The Weeknd',        'song': 'After Hours',                    'slug': 'after-hours-weeknd'},
    {'artist': 'Daniel Caesar',     'song': 'Best Part',                      'slug': 'best-part'},
    {'artist': 'H.E.R.',            'song': 'Focus',                          'slug': 'focus-her'},
    {'artist': 'Giveon',            'song': 'Heartbreak Anniversary',         'slug': 'heartbreak-anniversary'},
    {'artist': 'Silk Sonic',        'song': 'Leave the Door Open',            'slug': 'leave-the-door-open'},
    {'artist': 'Bruno Mars',        'song': 'That\'s What I Like',            'slug': 'thats-what-i-like'},
    {'artist': 'Bruno Mars',        'song': 'Treasure',                       'slug': 'treasure'},
    {'artist': 'Bruno Mars',        'song': 'Locked Out of Heaven',           'slug': 'locked-out-of-heaven'},
    {'artist': 'Charlie Wilson',    'song': 'You Are',                        'slug': 'you-are-charlie'},
    {'artist': 'John Legend',       'song': 'Ordinary People',                'slug': 'ordinary-people'},
    {'artist': 'John Legend',       'song': 'Save Room',                      'slug': 'save-room'},
    {'artist': 'Alicia Keys',       'song': 'If I Ain\'t Got You',            'slug': 'if-i-aint-got-you'},
    {'artist': 'Alicia Keys',       'song': 'Empire State of Mind',           'slug': 'empire-state-of-mind'},
    {'artist': 'Alicia Keys',       'song': 'Girl on Fire',                   'slug': 'girl-on-fire'},
    {'artist': 'Mary J. Blige',     'song': 'No More Drama',                  'slug': 'no-more-drama'},
    # ── Country ─────────────────────────────────────────────────────────────
    {'artist': 'Dolly Parton',      'song': 'Jolene',                         'slug': 'jolene'},
    {'artist': 'Dolly Parton',      'song': '9 to 5',                         'slug': '9-to-5'},
    {'artist': 'Johnny Cash',       'song': 'Ring of Fire',                   'slug': 'ring-of-fire'},
    {'artist': 'Johnny Cash',       'song': 'Hurt',                           'slug': 'hurt-cash'},
    {'artist': 'Kenny Rogers',      'song': 'The Gambler',                    'slug': 'the-gambler'},
    {'artist': 'Garth Brooks',      'song': 'Friends in Low Places',          'slug': 'friends-in-low-places'},
    {'artist': 'Garth Brooks',      'song': 'The Dance',                      'slug': 'the-dance'},
    {'artist': 'Luke Bryan',        'song': 'Play It Again',                  'slug': 'play-it-again'},
    {'artist': 'Luke Combs',        'song': 'Fast Car',                       'slug': 'fast-car-combs'},
    {'artist': 'Luke Combs',        'song': 'When It Rains It Pours',         'slug': 'when-it-rains'},
    {'artist': 'Morgan Wallen',     'song': 'Wasted on You',                  'slug': 'wasted-on-you'},
    {'artist': 'Morgan Wallen',     'song': 'Last Night',                     'slug': 'last-night-wallen'},
    {'artist': 'Zac Brown Band',    'song': 'Chicken Fried',                  'slug': 'chicken-fried'},
    {'artist': 'Blake Shelton',     'song': 'God\'s Country',                 'slug': 'gods-country'},
    {'artist': 'Carrie Underwood',  'song': 'Before He Cheats',               'slug': 'before-he-cheats'},
    {'artist': 'Carrie Underwood',  'song': 'Blown Away',                     'slug': 'blown-away'},
    {'artist': 'Miranda Lambert',   'song': 'The House That Built Me',        'slug': 'the-house-that-built-me'},
    {'artist': 'Brad Paisley',      'song': 'Then',                           'slug': 'then-brad'},
    {'artist': 'Tim McGraw',        'song': 'Live Like You Were Dying',       'slug': 'live-like-you-were-dying'},
    {'artist': 'Keith Urban',       'song': 'Blue Ain\'t Your Color',         'slug': 'blue-aint-your-color'},
    {'artist': 'Thomas Rhett',      'song': 'Die a Happy Man',                'slug': 'die-a-happy-man'},
    # ── More Classics ───────────────────────────────────────────────────────
    {'artist': 'ABBA',              'song': 'Mamma Mia',                      'slug': 'mamma-mia'},
    {'artist': 'ABBA',              'song': 'Voulez-Vous',                    'slug': 'voulez-vous'},
    {'artist': 'ABBA',              'song': 'Fernando',                       'slug': 'fernando-abba'},
    {'artist': 'ABBA',              'song': 'The Winner Takes It All',        'slug': 'the-winner-takes-it-all'},
    {'artist': 'Elton John',        'song': 'Your Song',                      'slug': 'your-song'},
    {'artist': 'Elton John',        'song': 'Crocodile Rock',                 'slug': 'crocodile-rock'},
    {'artist': 'Elton John',        'song': 'Don\'t Let the Sun Go Down',     'slug': 'dont-let-the-sun-go-down'},
    {'artist': 'Michael Jackson',   'song': 'Beat It',                        'slug': 'beat-it'},
    {'artist': 'Michael Jackson',   'song': 'Rock With You',                  'slug': 'rock-with-you'},
    {'artist': 'Michael Jackson',   'song': 'Human Nature',                   'slug': 'human-nature'},
    {'artist': 'Prince',            'song': 'Purple Rain',                    'slug': 'purple-rain'},
    {'artist': 'Prince',            'song': 'Kiss',                           'slug': 'prince-kiss'},
    {'artist': 'Fleetwood Mac',     'song': 'Dreams',                         'slug': 'dreams-fleetwood'},
    {'artist': 'Fleetwood Mac',     'song': 'The Chain',                      'slug': 'the-chain'},
    {'artist': 'Fleetwood Mac',     'song': 'Landslide',                      'slug': 'landslide'},
    {'artist': 'Stevie Nicks',      'song': 'Edge of Seventeen',              'slug': 'edge-of-seventeen'},
    {'artist': 'Heart',             'song': 'Alone',                          'slug': 'alone-heart'},
    {'artist': 'Pat Benatar',       'song': 'Love Is a Battlefield',          'slug': 'love-is-a-battlefield'},
    {'artist': 'Joan Jett',         'song': 'I Love Rock \'n\' Roll',         'slug': 'i-love-rock-n-roll'},
    {'artist': 'Meat Loaf',         'song': 'I\'d Do Anything for Love',      'slug': 'id-do-anything-for-love'},
    {'artist': 'REO Speedwagon',    'song': 'Can\'t Fight This Feeling',      'slug': 'cant-fight-this-feeling'},
    {'artist': 'Journey',           'song': 'Open Arms',                      'slug': 'open-arms'},
    {'artist': 'Journey',           'song': 'Faithfully',                     'slug': 'faithfully'},
    {'artist': 'Steve Perry',       'song': 'Oh Sherrie',                     'slug': 'oh-sherrie'},
    {'artist': 'Bob Dylan',         'song': 'Blowin\' in the Wind',           'slug': 'blowin-in-the-wind'},
    {'artist': 'Simon & Garfunkel', 'song': 'The Sound of Silence',          'slug': 'sound-of-silence'},
    {'artist': 'Simon & Garfunkel', 'song': 'Mrs Robinson',                  'slug': 'mrs-robinson'},
    # ── Hip-Hop ─────────────────────────────────────────────────────────────
    {'artist': 'Eminem',            'song': 'Without Me',                     'slug': 'eminem-without-me'},
    {'artist': 'Eminem',            'song': 'Stan',                           'slug': 'stan'},
    {'artist': 'Eminem',            'song': 'The Real Slim Shady',            'slug': 'the-real-slim-shady'},
    {'artist': 'Drake',             'song': 'God\'s Plan',                    'slug': 'gods-plan'},
    {'artist': 'Drake',             'song': 'One Dance',                      'slug': 'one-dance'},
    {'artist': 'Drake',             'song': 'Hotline Bling',                  'slug': 'hotline-bling'},
    {'artist': 'Kendrick Lamar',    'song': 'HUMBLE.',                        'slug': 'humble-kendrick'},
    {'artist': 'Kendrick Lamar',    'song': 'DNA.',                           'slug': 'dna-kendrick'},
    {'artist': 'Cardi B',           'song': 'I Like It',                      'slug': 'i-like-it-cardi'},
    {'artist': 'Cardi B',           'song': 'WAP',                            'slug': 'wap'},
    {'artist': 'Nicki Minaj',       'song': 'Super Bass',                     'slug': 'super-bass'},
    {'artist': 'Post Malone',       'song': 'Rockstar',                       'slug': 'rockstar-post'},
    {'artist': 'Post Malone',       'song': 'Better Now',                     'slug': 'better-now-post'},
    {'artist': 'Post Malone',       'song': 'White Iverson',                  'slug': 'white-iverson'},
    {'artist': 'Juice WRLD',        'song': 'Lucid Dreams',                   'slug': 'lucid-dreams'},
    {'artist': 'Juice WRLD',        'song': 'Legends',                        'slug': 'legends-juice'},
    {'artist': 'XXXTentacion',      'song': 'Sad!',                           'slug': 'sad-xxxt'},
    {'artist': 'Lil Nas X',         'song': 'Old Town Road',                  'slug': 'old-town-road'},
    {'artist': 'Lil Nas X',         'song': 'Montero',                        'slug': 'montero'},
    {'artist': 'Jack Harlow',       'song': 'First Class',                    'slug': 'first-class-harlow'},
    {'artist': 'Doja Cat',          'song': 'Kiss Me More',                   'slug': 'kiss-me-more'},
    {'artist': 'Doja Cat',          'song': 'Woman',                          'slug': 'woman-doja'},
    {'artist': 'Megan Thee Stallion','song': 'Savage',                        'slug': 'savage-megan'},
    {'artist': 'Tyler the Creator', 'song': 'See You Again',                  'slug': 'see-you-again-tyler'},
    # ── More Christmas ───────────────────────────────────────────────────────
    {'artist': 'Wham!',             'song': 'Last Christmas',                 'slug': 'last-christmas'},
    {'artist': 'Bing Crosby',       'song': 'White Christmas',                'slug': 'white-christmas'},
    {'artist': 'Andy Williams',     'song': 'It\'s the Most Wonderful Time',  'slug': 'most-wonderful-time'},
    {'artist': 'Bobby Helms',       'song': 'Jingle Bell Rock',               'slug': 'jingle-bell-rock'},
    {'artist': 'Brenda Lee',        'song': 'Rockin\' Around the Christmas Tree','slug': 'rockin-around-christmas'},
    {'artist': 'Michael Bublé',     'song': 'It\'s Beginning to Look Like Christmas','slug': 'beginning-to-look-like-christmas'},
    {'artist': 'Michael Bublé',     'song': 'Santa Baby',                     'slug': 'santa-baby'},
    {'artist': 'Nat King Cole',     'song': 'The Christmas Song',             'slug': 'the-christmas-song'},
    # ── More OPM / Filipino ─────────────────────────────────────────────────
    {'artist': 'Eraserheads',       'song': 'Ang Huling El Bimbo',            'slug': 'ang-huling-el-bimbo'},
    {'artist': 'Eraserheads',       'song': 'Ligaya',                         'slug': 'ligaya'},
    {'artist': 'Rivermaya',         'song': 'You\'ll Be Safe Here',           'slug': 'youll-be-safe-here'},
    {'artist': 'Rivermaya',         'song': '214',                            'slug': 'rivermaya-214'},
    {'artist': 'Hale',              'song': 'The Day You Said Goodnight',     'slug': 'the-day-you-said-goodnight'},
    {'artist': 'December Avenue',   'song': 'Aking Araw',                     'slug': 'aking-araw'},
    {'artist': 'Arthur Nery',       'song': 'Palagi',                         'slug': 'palagi'},
    {'artist': 'Cup of Joe',        'song': 'Paraluman',                      'slug': 'paraluman'},
    # ── More K-Pop ───────────────────────────────────────────────────────────
    {'artist': 'EXO',               'song': 'Ko Ko Bop',                      'slug': 'exo-ko-ko-bop'},
    {'artist': 'EXO',               'song': 'Love Shot',                      'slug': 'exo-love-shot'},
    {'artist': 'Red Velvet',        'song': 'Psycho',                         'slug': 'rv-psycho'},
    {'artist': 'MAMAMOO',           'song': 'HIP',                            'slug': 'mamamoo-hip'},
    {'artist': 'aespa',             'song': 'Next Level',                     'slug': 'aespa-next-level'},
    {'artist': 'ITZY',              'song': 'LOCO',                           'slug': 'itzy-loco'},
    {'artist': 'GOT7',              'song': 'Not By the Moon',                'slug': 'got7-not-by-the-moon'},
    {'artist': 'SHINee',            'song': 'View',                           'slug': 'shinee-view'},
    # ── More Bollywood ───────────────────────────────────────────────────────
    {'artist': 'Arijit Singh',      'song': 'Ae Dil Hai Mushkil',            'slug': 'ae-dil-hai-mushkil'},
    {'artist': 'Arijit Singh',      'song': 'Channa Mereya',                  'slug': 'channa-mereya'},
    {'artist': 'Arijit Singh',      'song': 'Phir Le Aaya Dil',              'slug': 'phir-le-aaya-dil'},
    {'artist': 'Shreya Ghoshal',    'song': 'Teri Meri',                      'slug': 'teri-meri'},
    {'artist': 'Udit Narayan',      'song': 'Pehla Nasha',                    'slug': 'pehla-nasha'},
    {'artist': 'Kumar Sanu',        'song': 'Tujhe Dekha To',                 'slug': 'tujhe-dekha-to'},
    {'artist': 'Armaan Malik',      'song': 'Main Rahoon Ya Na Rahoon',       'slug': 'main-rahoon'},
    {'artist': 'Atif Aslam',        'song': 'Woh Lamhe',                      'slug': 'woh-lamhe'},
]
_SONG_BY_SLUG = {s['slug']: s for s in SONG_PAGES}

# ── Genre landing pages ─────────────────────────────────────────────────────
GENRES = {
    'pop': {
        'name': 'Pop',
        'title': 'Pop Karaoke Songs',
        'h1': 'Pop Karaoke',
        'description': 'The biggest pop karaoke hits — Taylor Swift, Dua Lipa, Ariana Grande, Ed Sheeran, and more. Sing the best pop songs free online.',
        'slugs': ['anti-hero','shape-of-you','blinding-lights','levitating','dont-start-now',
                  'new-rules','watermelon-sugar','as-it-was','drivers-license','good-4-u',
                  'thank-u-next','ariana-7-rings','perfect','thinking-out-loud',
                  'someone-you-loved','all-of-me','espresso','dance-monkey','heat-waves',
                  'love-yourself','attention','one-call-away'],
    },
    'rock': {
        'name': 'Rock',
        'title': 'Rock Karaoke Songs',
        'h1': 'Rock Karaoke',
        'description': 'Classic and modern rock karaoke — Queen, Nirvana, Linkin Park, Green Day, The Beatles, Guns N\' Roses, and more. Rock the mic free.',
        'slugs': ['bohemian-rhapsody','dont-stop-me-now','we-will-rock-you','we-are-the-champions',
                  'stairway-to-heaven','paint-it-black','wonderwall','mr-brightside',
                  'smells-like-teen-spirit','good-riddance','in-the-end','linkin-park-numb',
                  'sweet-child-o-mine','hotel-california','hey-jude','let-it-be','yesterday',
                  'with-or-without-you','africa','dont-stop-believin','livin-on-a-prayer',
                  'its-my-life','creep','radioactive'],
    },
    '80s': {
        'name': '80s',
        'title': '80s Karaoke Songs',
        'h1': '80s Karaoke',
        'description': 'The greatest 80s karaoke songs — Take On Me, Careless Whisper, Girls Just Want to Have Fun, Total Eclipse of the Heart, Piano Man, and more.',
        'slugs': ['take-on-me','careless-whisper','like-a-prayer','material-girl',
                  'girls-just-want-to-have-fun','time-after-time','piano-man',
                  'every-breath-you-take','superstition','total-eclipse-of-the-heart',
                  'tiny-dancer','thriller','man-in-the-mirror','rocket-man',
                  'george-michael-faith','bowie-heroes','my-way','sweet-caroline',
                  'dont-wanna-miss-a-thing'],
    },
    '90s': {
        'name': '90s',
        'title': '90s Karaoke Songs',
        'h1': '90s Karaoke',
        'description': 'All the best 90s karaoke bangers — Backstreet Boys, Spice Girls, Britney Spears, Whitney Houston, TLC, and more. Sing your favourites free.',
        'slugs': ['baby-one-more-time','oops-i-did-it-again','wannabe','i-want-it-that-way',
                  'bye-bye-bye','beautiful-aguilera','dont-speak','say-my-name',
                  'because-you-loved-me','mariah-fantasy','i-will-always-love-you',
                  'my-heart-will-go-on','dancing-queen','never-gonna-give-you-up',
                  'man-i-feel-like-a-woman','alanis-ironic','stand-by-me','lean-on-me'],
    },
    'rnb': {
        'name': 'R&B',
        'title': 'R&B Karaoke Songs',
        'h1': 'R&B Karaoke',
        'description': 'Smooth R&B karaoke — Beyoncé, Usher, Alicia Keys, Whitney Houston, Bruno Mars, and timeless soul classics. Sing R&B hits free online.',
        'slugs': ['beyonce-halo','crazy-in-love','single-ladies','usher-yeah','alicia-keys-no-one',
                  'i-gotta-feeling','say-my-name','all-of-me','september','lean-on-me',
                  'stand-by-me','isnt-she-lovely','sexyback','we-found-love','rihanna-diamonds',
                  'rihanna-umbrella','just-the-way-you-are','grenade',
                  'when-i-was-your-man','uptown-funk'],
    },
    'kpop': {
        'name': 'K-Pop',
        'title': 'K-Pop Karaoke Songs',
        'h1': 'K-Pop Karaoke',
        'description': 'Sing your favourite K-Pop karaoke songs — BTS, BLACKPINK, IU, TWICE, NewJeans, Stray Kids, and more. Free K-Pop karaoke online.',
        'slugs': ['bts-dynamite','bts-boy-with-luv','blackpink-how-you-like-that',
                  'blackpink-kill-this-love','iu-celebrity','twice-fancy',
                  'newjeans-hype-boy','stray-kids-gods-menu'],
    },
    'latin': {
        'name': 'Latin',
        'title': 'Latin Karaoke Songs',
        'h1': 'Latin Karaoke',
        'description': 'Hot Latin karaoke — Despacito, Hips Don\'t Lie, Havana, Vivir Mi Vida, and more Spanish hits. Free Latin karaoke online.',
        'slugs': ['despacito','hips-dont-lie','vivir-mi-vida','enrique-hero','havana',
                  'dakiti','conga','santana-smooth'],
    },
    'bollywood': {
        'name': 'Bollywood',
        'title': 'Bollywood Karaoke Songs',
        'h1': 'Bollywood Karaoke',
        'description': 'Sing the biggest Bollywood karaoke hits — Tum Hi Ho, Kesariya, Kal Ho Naa Ho, Raataan Lambiyan, and more Hindi songs free online.',
        'slugs': ['tum-hi-ho','kesariya','kal-ho-naa-ho','raataan-lambiyan',
                  'tujh-mein-rab','tera-hone-laga-hoon','lut-gaye','dil-deewana'],
    },
    'party': {
        'name': 'Party',
        'title': 'Party Karaoke Songs',
        'h1': 'Party Karaoke',
        'description': 'The ultimate party karaoke playlist — crowd favourites everyone knows, from Don\'t Stop Believin\' to Uptown Funk. Get the party started free.',
        'slugs': ['dont-stop-believin','livin-on-a-prayer','we-will-rock-you',
                  'dancing-queen','uptown-funk','i-gotta-feeling','sweet-caroline',
                  'bohemian-rhapsody','girls-just-want-to-have-fun','shake-it-off',
                  'wannabe','good-riddance','mr-brightside','somebody-that-i-used-to-know',
                  'all-about-that-bass','truth-hurts'],
    },
    'christmas': {
        'name': 'Christmas',
        'title': 'Christmas Karaoke Songs',
        'h1': 'Christmas Karaoke',
        'description': 'Sing the best Christmas karaoke songs — All I Want for Christmas Is You, Last Christmas, White Christmas, and more festive favourites free.',
        'slugs': ['all-i-want-for-christmas','last-christmas','white-christmas',
                  'most-wonderful-time','jingle-bell-rock','rockin-around-christmas',
                  'beginning-to-look-like-christmas','santa-baby','the-christmas-song'],
    },
}
_GENRE_SLUGS = set(GENRES.keys())


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


@app.route('/karaoke/<genre_slug>')
def genre_page(genre_slug):
    genre = GENRES.get(genre_slug)
    if not genre:
        return render_template('index.html'), 404
    songs = [_SONG_BY_SLUG[s] for s in genre['slugs'] if s in _SONG_BY_SLUG]
    return render_template('genre.html', genre=genre, songs=songs, genre_slug=genre_slug)


@app.route('/sing/<slug>')
def song_page(slug):
    song = _SONG_BY_SLUG.get(slug)
    if not song:
        return render_template('index.html'), 404
    # Related: same artist first, then popular picks (exclude current song)
    same_artist = [s for s in SONG_PAGES if s['artist'] == song['artist'] and s['slug'] != slug]
    others      = [s for s in SONG_PAGES if s['artist'] != song['artist']][:6]
    related     = (same_artist + others)[:6]
    return render_template('song.html', related=related, **song)


@app.route('/og-image')
def og_image():
    """Dynamic OG image as SVG — works for homepage and song pages."""
    song   = request.args.get('song', '')
    artist = request.args.get('artist', '')
    if song and artist:
        line1 = _html.escape(song[:40])
        line2 = _html.escape(f'by {artist}')
        sub   = 'Sing along free on Karaoke Lover'
    else:
        line1 = 'Karaoke Lover'
        line2 = 'Sing Any Song, Right Now'
        sub   = 'Free online karaoke — no downloads, no sign-up'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0d0521"/>
      <stop offset="50%" style="stop-color:#1a0640"/>
      <stop offset="100%" style="stop-color:#2d0a5e"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#9333ea"/>
      <stop offset="100%" style="stop-color:#ec4899"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect x="0" y="540" width="1200" height="6" fill="url(#accent)" opacity="0.9"/>
  <circle cx="80" cy="80" r="200" fill="#9333ea" opacity="0.07"/>
  <circle cx="1150" cy="580" r="250" fill="#ec4899" opacity="0.06"/>
  <text x="80" y="120" font-family="Arial,sans-serif" font-size="36" font-weight="700" fill="#9333ea" letter-spacing="3">KARAOKE LOVER</text>
  <text x="80" y="300" font-family="Arial,sans-serif" font-size="72" font-weight="900" fill="white" letter-spacing="-1">{line1}</text>
  <text x="80" y="390" font-family="Arial,sans-serif" font-size="48" font-weight="400" fill="#c084fc">{line2}</text>
  <text x="80" y="500" font-family="Arial,sans-serif" font-size="32" font-weight="400" fill="#6b7280">{sub}</text>
  <text x="1120" y="300" font-family="Arial,sans-serif" font-size="120" text-anchor="middle" fill="white" opacity="0.08">🎤</text>
</svg>'''
    return Response(svg, mimetype='image/svg+xml',
                    headers={'Cache-Control': 'public, max-age=86400'})


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
    for genre_slug in GENRES:
        urls.append(
            f'<url><loc>https://www.karaokelover.com/karaoke/{genre_slug}</loc>'
            f'<changefreq>monthly</changefreq><priority>0.9</priority></url>'
        )
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
    era      = request.args.get('era', '').strip()
    if not query:
        return jsonify({'error': 'Query is required'}), 400

    # --- Cache lookup (include era in key) ---
    cache_key = f'{query.lower()}|{language}|{region}|{era}'
    now = time.time()
    cached = SEARCH_CACHE.get(cache_key)
    if cached and now - cached['ts'] < SEARCH_CACHE_TTL:
        return jsonify({'results': cached['results'], 'cached': True})

    # --- In-flight deduplication: if same query is already being fetched, wait ---
    with _INFLIGHT_LOCK:
        if cache_key in _INFLIGHT:
            wait_event = _INFLIGHT[cache_key]
            is_leader  = False
        else:
            wait_event = threading.Event()
            _INFLIGHT[cache_key] = wait_event
            is_leader = True

    if not is_leader:
        # Another request is fetching — wait up to 15 s then serve from cache
        wait_event.wait(timeout=15)
        cached = SEARCH_CACHE.get(cache_key)
        if cached and cached.get('results'):
            return jsonify({'results': cached['results'], 'cached': True})
        return jsonify({'error': 'Search is temporarily unavailable. Please try again.'}), 503

    try:
        params = {
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
        # For 2020s, filter by upload date — karaoke uploads of new songs are recent
        # For older eras, date filtering doesn't help (old songs re-uploaded constantly)
        ERA_PUBLISHED_AFTER = {
            '2020s': '2019-12-31T00:00:00Z',
            '2010s': '2009-12-31T00:00:00Z',
        }
        ERA_PUBLISHED_BEFORE = {
            '2010s': '2020-01-01T00:00:00Z',
        }
        if era in ERA_PUBLISHED_AFTER:
            params['publishedAfter'] = ERA_PUBLISHED_AFTER[era]
        if era in ERA_PUBLISHED_BEFORE:
            params['publishedBefore'] = ERA_PUBLISHED_BEFORE[era]

        data, err_msg = _youtube_search(params)

        if data is None:
            # Serve stale cache if available — better than an error
            if cached and cached.get('results'):
                return jsonify({'results': cached['results'], 'cached': True})
            if err_msg == 'quota':
                return jsonify({'error': 'Search is temporarily unavailable — daily limit reached. Please try again later.'}), 503
            return jsonify({'error': err_msg or 'YouTube search failed. Please try again.'}), 500

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

        # --- Cache store (evict oldest entries if full) ---
        if len(SEARCH_CACHE) >= SEARCH_CACHE_MAX:
            oldest = min(SEARCH_CACHE, key=lambda k: SEARCH_CACHE[k]['ts'])
            del SEARCH_CACHE[oldest]
        SEARCH_CACHE[cache_key] = {'results': results, 'ts': now}
        _save_cache()   # persist so restarts don't lose warm cache

        return jsonify({'results': results})

    finally:
        # Signal any waiting followers and remove from in-flight tracker
        with _INFLIGHT_LOCK:
            ev = _INFLIGHT.pop(cache_key, None)
        if ev:
            ev.set()


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


@app.route('/api/trending')
def trending():
    import random
    # Return a random selection from our curated SONG_PAGES list.
    # This costs zero API quota and always shows karaoke-ready songs.
    pool = random.sample(SONG_PAGES, min(12, len(SONG_PAGES)))
    songs = [{'artist': s['artist'], 'song': s['song']} for s in pool]
    return jsonify({'songs': songs})


@app.route('/api/cache-stats')
def cache_stats():
    """Monitoring endpoint — shows cache health and quota key status."""
    now   = time.time()
    total = len(SEARCH_CACHE)
    fresh = sum(1 for v in SEARCH_CACHE.values() if now - v['ts'] < SEARCH_CACHE_TTL)
    ages  = [now - v['ts'] for v in SEARCH_CACHE.values()]
    active_keys = sum(
        1 for k in _ALL_YT_KEYS
        if now - EXHAUSTED_KEYS.get(k, 0) > QUOTA_RESET_SECS
    )
    return jsonify({
        'cache': {
            'total_entries':    total,
            'fresh':            fresh,
            'stale':            total - fresh,
            'oldest_age_hours': round(max(ages) / 3600, 1) if ages else None,
            'newest_age_hours': round(min(ages) / 3600, 1) if ages else None,
            'ttl_days':         round(SEARCH_CACHE_TTL / 86400, 1),
            'max_entries':      SEARCH_CACHE_MAX,
        },
        'quota': {
            'total_keys':  len(_ALL_YT_KEYS),
            'active_keys': active_keys,
            'exhausted':   len(_ALL_YT_KEYS) - active_keys,
        },
    })


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


# ── Startup ──────────────────────────────────────────────────────────────────
_load_cache()
threading.Thread(target=_prewarm_worker, daemon=True, name='prewarm').start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)
