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

# Search result cache — avoids burning quota on repeated queries
SEARCH_CACHE     = {}   # key → {'results': [...], 'ts': float}
SEARCH_CACHE_TTL = 6 * 3600   # 6 hours
SEARCH_CACHE_MAX = 500         # max entries; evict oldest when full

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

    # --- Cache lookup ---
    cache_key = f'{query.lower()}|{language}|{region}'
    now = time.time()
    cached = SEARCH_CACHE.get(cache_key)
    if cached and now - cached['ts'] < SEARCH_CACHE_TTL:
        return jsonify({'results': cached['results'], 'cached': True})

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
        err = data['error']
        reasons = [e.get('reason', '') for e in err.get('errors', [])]
        if err.get('code') == 403 or 'quotaExceeded' in reasons or 'forbidden' in str(reasons).lower():
            # Serve stale cache if available — better than an error
            if cached and cached.get('results'):
                return jsonify({'results': cached['results'], 'cached': True})
            return jsonify({'error': 'Search is temporarily unavailable — daily limit reached. Please try again later.'}), 503
        return jsonify({'error': 'YouTube search failed. Please try again.'}), 500

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


@app.route('/api/trending')
def trending():
    import random
    # Return a random selection from our curated SONG_PAGES list.
    # This costs zero API quota and always shows karaoke-ready songs.
    pool = random.sample(SONG_PAGES, min(12, len(SONG_PAGES)))
    songs = [{'artist': s['artist'], 'song': s['song']} for s in pool]
    return jsonify({'songs': songs})


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
