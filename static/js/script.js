/* ==========================================
   Karaoke Lover v3
   Search · Player · Lyrics · History
   Auto-play · Mini Player
   Keyboard Shortcuts · Shuffle · Sing Mode
   ========================================== */

// ---- Global state ----
let ytPlayer       = null;
let ytReady        = false;
let pendingVideoId     = null;
let _pendingStartSec   = 0;

// ---- Playback position persistence ----
const _POS_KEY  = 'klLastPlay';
const _PPOS_KEY = 'klPositions';

function _savePosition() {
  if (!currentVideo || !ytPlayer || !ytPlayer.getCurrentTime) return;
  const t = ytPlayer.getCurrentTime();
  if (t < 3) return;
  try {
    localStorage.setItem(_POS_KEY, JSON.stringify({
      video_id: currentVideo.video_id, title: currentVideo.title,
      channel: currentVideo.channel || '', thumbnail: currentVideo.thumbnail || '',
      time: t, savedAt: Date.now(),
      hasLyrics: playerSection.classList.contains('has-lyrics')
    }));
    const pp = JSON.parse(localStorage.getItem(_PPOS_KEY) || '{}');
    pp[currentVideo.video_id] = t;
    localStorage.setItem(_PPOS_KEY, JSON.stringify(pp));
  } catch {}
}

function _getSavedTime(videoId) {
  try {
    const pp = JSON.parse(localStorage.getItem(_PPOS_KEY) || '{}');
    return pp[videoId] || 0;
  } catch { return 0; }
}

// ---- URL State (refresh/back button persistence) ----
function _updateVideoUrl(videoId) {
  try {
    const url = new URL(window.location);
    const hadVideo = url.searchParams.has('v');
    url.searchParams.set('v', videoId);
    url.searchParams.delete('q');
    if (hadVideo) {
      history.replaceState({ videoId }, '', url.toString());
    } else {
      // First video play in session — push so back button returns to home
      history.pushState({ videoId }, '', url.toString());
    }
    // Pulse the share button to signal the URL is now shareable
    if (typeof shareSongBtn !== 'undefined' && shareSongBtn) {
      shareSongBtn.classList.remove('url-updated');
      void shareSongBtn.offsetWidth;
      shareSongBtn.classList.add('url-updated');
      setTimeout(() => shareSongBtn.classList.remove('url-updated'), 700);
    }
  } catch {}
}

// Save position every 5 seconds while playing
setInterval(() => {
  if (ytPlayer && ytPlayer.getPlayerState &&
      ytPlayer.getPlayerState() === 1 /* PLAYING */) {
    _savePosition();
  }
}, 5000);
let currentResults = [];
let currentIndex   = -1;
let shuffleMode    = false;
let currentVideo   = null;
let miniVisible      = false;
let songQueue        = [];
let _currentUid      = null;
let progressInterval = null;

// ---- Feature constants (must be before INIT) ----
const FAV_MAX = 100;
const QUEUE_KEY = 'ks_queue';

function favKey() {
  return _currentUid ? `ks_favorites_${_currentUid}` : null;
}

// ---- Filter state ----
const MOOD_KEYWORDS = {
  'Party':    'party hits dance',
  'Romantic': 'love romantic slow',
  'Sad':      'sad ballad heartbreak',
  'Pump Up':  'pump up workout energy',
  'Chill':    'chill relaxing mellow',
};
const LANGUAGE_LABELS = {
  'en':'English','tl':'Filipino','hi':'Hindi','es':'Spanish',
  'ko':'Korean','zh':'Chinese','ja':'Japanese','th':'Thai',
  'ar':'Arabic','vi':'Vietnamese','ms':'Malay','pt':'Portuguese',
  'fr':'French','de':'German','tr':'Turkish','it':'Italian',
};
const activeFilters = { genre: null, era: null, language: null, mood: null };

// ---- DOM ----
const searchForm     = document.getElementById('searchForm');
const searchInput    = document.getElementById('searchInput');
const searchBtn      = searchForm.querySelector('.search-btn');
const resultsSection = document.getElementById('resultsSection');
const resultsGrid    = document.getElementById('resultsGrid');
const resultsTitle   = document.getElementById('resultsTitle');
const tabsBar        = document.getElementById('tabsBar');
const tabAll         = document.getElementById('tabAll');
const playerSection  = document.getElementById('playerSection');
const playerTitle    = document.getElementById('playerTitle');
const playerChannel  = document.getElementById('playerChannel');
const playerContainer= document.querySelector('.player-container');
const closePlayerBtn = document.getElementById('closePlayer');
const prevBtn        = document.getElementById('prevBtn');
const nextBtn        = document.getElementById('nextBtn');
const shuffleBtn     = document.getElementById('shuffleBtn');
const shuffleAllBtn  = document.getElementById('shuffleAllBtn');
const lyricsSection  = document.getElementById('lyricsSection');
const lyricsTitle    = document.getElementById('lyricsTitle');
const lyricsArtist   = document.getElementById('lyricsArtist');
const lyricsLoading  = document.getElementById('lyricsLoading');
const lyricsText     = document.getElementById('lyricsText');
const lyricsNotFound = document.getElementById('lyricsNotFound');
const lyricsBody     = document.getElementById('lyricsBody');
const lyricsExpand   = document.getElementById('lyricsExpand');
const nowPlayingCard = document.getElementById('nowPlayingCard');
const npTitle        = document.getElementById('npTitle');
const npArtist       = document.getElementById('npArtist');
const singMode       = document.getElementById('singMode');
const singClose      = document.getElementById('singClose');
const singTitle      = document.getElementById('singTitle');
const singArtist     = document.getElementById('singArtist');
const singBody       = document.getElementById('singBody');
const historySection = document.getElementById('historySection');
const historyStrip   = document.getElementById('historyStrip');
const loadingOverlay = document.getElementById('loadingOverlay');
const emptyState     = document.getElementById('emptyState');
const errorState     = document.getElementById('errorState');
const errorMsg       = document.getElementById('errorMsg');
const equalizer      = document.getElementById('equalizer');
const toastContainer = document.getElementById('toastContainer');
const miniPlayer       = document.getElementById('miniPlayer');
const miniProgressFill = document.getElementById('miniProgressFill');
const miniProgress     = document.getElementById('miniProgress');
const miniStop         = document.getElementById('miniStop');
const playerBackdrop   = document.getElementById('playerBackdrop');
const miniEq           = document.getElementById('miniEq');
const recSection     = document.getElementById('recSection');
const recChips       = document.getElementById('recChips');
const recLoading     = document.getElementById('recLoading');
const trendingChips  = document.getElementById('trendingChips');
const miniThumb      = document.getElementById('miniThumb');
const miniTitle      = document.getElementById('miniTitle');
const miniChannel    = document.getElementById('miniChannel');
const miniPrev       = document.getElementById('miniPrev');
const miniPlayPause  = document.getElementById('miniPlayPause');
const miniNext       = document.getElementById('miniNext');
const miniBack       = document.getElementById('miniBack');
const filterBadgeList  = document.getElementById('filterBadgeList');
const filterClearAll   = document.getElementById('filterClearAll');
const filterMoreBtn    = document.getElementById('filterMoreBtn');
const filterExpanded   = document.getElementById('filterExpanded');
const filterMoreCount  = document.getElementById('filterMoreCount');
const playerArtBg      = document.getElementById('playerArtBg');
const stageArtBg       = document.getElementById('stageArtBg');
const playerArtThumb   = document.getElementById('playerArtThumb');
const favoritesSection = document.getElementById('favoritesSection');
const favoritesStrip   = document.getElementById('favoritesStrip');
const favHeading       = document.getElementById('favHeading');
const favClearBtn      = document.getElementById('favClearBtn');
const queueToggleBtn   = document.getElementById('queueToggleBtn');
const queueCount       = document.getElementById('queueCount');
const queuePanel       = document.getElementById('queuePanel');
const queueSub         = document.getElementById('queueSub');
const queuePlay        = document.getElementById('queuePlay');
const queueClear       = document.getElementById('queueClear');
const queueClose       = document.getElementById('queueClose');
const queueList        = document.getElementById('queueList');
const playerFavBtn     = document.getElementById('playerFavBtn');
const shareSongBtn     = document.getElementById('shareSongBtn');
const shareModal       = document.getElementById('shareModal');
const shareModalClose  = document.getElementById('shareModalClose');
const shareModalThumb  = document.getElementById('shareModalThumb');
const shareModalTitle  = document.getElementById('shareModalTitle');
const shareModalChannel= document.getElementById('shareModalChannel');
const shareModalLink   = document.getElementById('shareModalLink');
const shareCopyBtn     = document.getElementById('shareCopyBtn');
const shareTwitter     = document.getElementById('shareTwitter');
const shareWhatsapp    = document.getElementById('shareWhatsapp');
const searchDropdown   = document.getElementById('searchDropdown');
const sdList           = document.getElementById('sdList');
const sdClear          = document.getElementById('sdClear');
const particles        = document.getElementById('particles');
const resumeBanner     = document.getElementById('resumeBanner');
const resumeBannerText = document.getElementById('resumeBannerText');
const resumeBannerBtn  = document.getElementById('resumeBannerBtn');
const resumeBannerDismiss = document.getElementById('resumeBannerDismiss');
const playerResumeOverlay = document.getElementById('playerResumeOverlay');
const proThumb    = document.getElementById('proThumb');
const proPosition = document.getElementById('proPosition');
const proBtn      = document.getElementById('proBtn');

// ==========================================
// INIT
// ==========================================

initParticles();
renderHistory();
renderFavorites();
loadQueue();
fetchTrending();
initFilters();
initSearchDropdown();
// URL state takes priority — if ?v= is in URL, load that video directly
if (!_checkUrlState()) _checkLastPlaying();
// Auto-search if ?q= was shared (backward compat)
const _initQ = new URLSearchParams(location.search).get('q');
if (_initQ) doSearch(_initQ);

function _checkLastPlaying() {
  showResumeBanner(); // unified — showResumeBanner checks _POS_KEY first
}

// ---- URL state: auto-load video on refresh or shared link ----
function _checkUrlState() {
  const videoId = new URLSearchParams(location.search).get('v');
  if (!videoId) return false;

  try {
    // Collapse hero → player section is immediately visible, no scrolling required.
    document.body.classList.add('url-video');

    // Find saved metadata: prefer _POS_KEY (same device refresh), then history
    let v = null, startSec = 0, savedHasLyrics = null;
    try {
      const saved = JSON.parse(localStorage.getItem(_POS_KEY) || 'null');
      if (saved && saved.video_id === videoId) {
        v = { video_id: saved.video_id, title: saved.title, channel: saved.channel || '', thumbnail: saved.thumbnail || '' };
        startSec = Math.max(0, (saved.time || 0) - 2);
        savedHasLyrics = saved.hasLyrics === true || saved.hasLyrics === false ? saved.hasLyrics : null;
      }
    } catch {}

    if (!v) {
      let hist = getHistory();
      if (!hist.length) try { hist = JSON.parse(localStorage.getItem('ks_history') || '[]'); } catch { hist = []; }
      const found = hist.find(h => h.video_id === videoId);
      if (found) { v = found; startSec = Math.max(0, _getSavedTime(videoId) - 2); }
    }

    // Shared link from another device — no metadata available, load gracefully
    if (!v) v = { video_id: videoId, title: 'Loading…', channel: '', thumbnail: '' };

    currentResults = [v]; currentIndex = 0; currentVideo = v;
    playerTitle.textContent   = v.title;
    playerChannel.textContent = v.channel;
    _setPlayerArt(v);
    historySection.style.display   = 'none';
    favoritesSection.style.display = 'none';
    playerSection.style.display    = 'block';
    updateMiniInfo(v);

    // Hero is collapsed (body.url-video), so player section is near the top.
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    requestAnimationFrame(() => {
      const y = playerSection.getBoundingClientRect().top + window.scrollY - 65;
      window.scrollTo(0, Math.max(0, y));
    });

    // Show resume overlay — don't autoplay on refresh (browsers block it).
    if (playerResumeOverlay) {
      if (proThumb) proThumb.src = v.thumbnail || '';
      if (proPosition) {
        if (startSec > 2) {
          const mm = Math.floor(startSec / 60);
          const ss = String(Math.floor(startSec % 60)).padStart(2, '0');
          proPosition.textContent = `Paused at ${mm}:${ss}`;
        } else {
          proPosition.textContent = 'Tap to start';
        }
      }
      playerResumeOverlay.style.display = 'flex';
      if (proBtn) proBtn.onclick = () => {
        playerResumeOverlay.style.display = 'none';
        if (ytReady) loadPlayer(videoId, startSec);
        else { pendingVideoId = videoId; _pendingStartSec = startSec; }
      };
    } else {
      if (ytReady) loadPlayer(videoId, startSec);
      else { pendingVideoId = videoId; _pendingStartSec = startSec; }
    }

    if (v.title !== 'Loading…') {
      if (savedHasLyrics === false) {
        showToast('[DEBUG] refresh: no-lyrics path (vibes card)', '');
        _showNowPlayingCard();
      } else {
        showToast('[DEBUG] refresh: lyrics path, savedHasLyrics=' + savedHasLyrics + ', title=' + v.title.substring(0, 30), '');
        fetchLyrics(v.title, true);
      }
      fetchRecommendations(v.title);
      addToHistory(v);
      updatePlayerFavBtn();
    } else {
      showToast('[DEBUG] refresh: Loading… path (vibes card)', '');
      _showNowPlayingCard();
    }
  } catch (e) {
    console.error('[KL] _checkUrlState error:', e);
  }

  return true;
}

// Save position when user leaves / hides the tab
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') _savePosition();
});

// ==========================================
// SEARCH HISTORY DROPDOWN
// ==========================================

const QUERY_MAX = 4;

function queryKey() {
  return _currentUid ? `ks_queries_${_currentUid}` : null;
}

function getQueries() {
  const key = queryKey();
  if (!key) return [];
  try { return JSON.parse(localStorage.getItem(key) || '[]'); }
  catch { return []; }
}

function saveQuery(q) {
  const key = queryKey();
  if (!key || !q || q.length < 2) return;
  let list = getQueries().filter(x => x.toLowerCase() !== q.toLowerCase());
  list.unshift(q);
  if (list.length > QUERY_MAX) list = list.slice(0, QUERY_MAX);
  localStorage.setItem(key, JSON.stringify(list));
}

function renderDropdown(filter) {
  const all = getQueries();
  const f   = (filter || '').toLowerCase().trim();
  const items = f ? all.filter(q => q.toLowerCase().includes(f)) : all;
  sdList.innerHTML = '';
  items.forEach(q => {
    const div  = document.createElement('div');
    div.className = 'sd-item';
    div.innerHTML = `<span class="sd-item-icon">🕐</span><span class="sd-item-text">${escapeHtml(q)}</span>`;
    div.addEventListener('mousedown', (e) => {
      e.preventDefault(); // prevent blur before click fires
      searchInput.value = q;
      hideDropdown();
      doSearch(q);
    });
    sdList.appendChild(div);
  });
  if (items.length > 0) {
    searchDropdown.classList.add('open');
    searchForm.classList.add('dropdown-open');
  } else {
    searchDropdown.classList.remove('open');
    searchForm.classList.remove('dropdown-open');
  }
}

function showDropdown() {
  renderDropdown(searchInput.value.trim());
  // Only hide filters/popular when dropdown is actually open (has items)
  if (searchDropdown.classList.contains('open')) {
    searchForm.classList.add('dropdown-open');
  }
}

function hideDropdown() {
  searchDropdown.classList.remove('open');
  searchForm.classList.remove('dropdown-open');
}

let _dropdownPending = false; // user clicked search before auth resolved

function initSearchDropdown() {
  searchInput.addEventListener('focus', () => {
    if (!_currentUid) { _dropdownPending = true; return; } // auth not ready yet
    showDropdown();
  });
  searchInput.addEventListener('input', () => renderDropdown(searchInput.value.trim()));
  searchInput.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideDropdown(); });
  // On mobile: blur fires when user taps outside the input; delay 200ms so
  // mousedown on a dropdown item (which uses e.preventDefault to keep focus) fires first
  searchInput.addEventListener('blur', () => { _dropdownPending = false; setTimeout(hideDropdown, 200); });
  sdClear.addEventListener('click', () => {
    const key = queryKey();
    if (key) localStorage.removeItem(key);
    hideDropdown();
  });

  window.addEventListener('authStateChanged', async ({ detail: { user, isSignOut } }) => {
    _currentUid = user ? user.uid : null;
    if (isSignOut) {
      hideDropdown();
      renderHistory();
      renderFavorites();
    } else if (user) {
      // User clicked search before auth resolved — show dropdown now
      if (_dropdownPending) { _dropdownPending = false; showDropdown(); }
      // Consolidate history from all possible sources into the UID key
      const _read = k => { try { return JSON.parse(localStorage.getItem(k) || '[]'); } catch { return []; } };
      const uidHist   = _read(histKey());
      const guestHist = _read('ks_history_guest');
      const oldHist   = _read('ks_history'); // pre-UID global key
      if (guestHist.length > 0 || oldHist.length > 0) {
        // Merge: uid entries first, then guest, then old — deduplicate by video_id
        const merged = [...uidHist];
        for (const e of [...guestHist, ...oldHist]) {
          const id = e.video_id || e.videoId || '';
          if (id && !merged.some(h => (h.video_id || h.videoId) === id)) merged.push(e);
        }
        merged.splice(10);
        localStorage.setItem(histKey(), JSON.stringify(merged));
      }

      // Show from localStorage immediately (may be empty on first sign-in)
      renderHistory();
      renderFavorites();
      showResumeBanner();

      // Sync from Firestore — then re-show history + banner with full data
      try {
        const firestoreHist = await window.karaokAuth.getHistory();
        if (firestoreHist && firestoreHist.length > 0) {
          const normalized = firestoreHist.map(h => ({
            video_id:  h.videoId  || h.video_id || '',
            title:     h.title    || '',
            channel:   h.channel  || '',
            thumbnail: h.thumbnail || '',
          }));
          localStorage.setItem(histKey(), JSON.stringify(normalized));
          renderHistory();
          showResumeBanner(); // re-call now that data is in localStorage
        }
      } catch { /* non-critical */ }
    }
  });
  document.addEventListener('click', (e) => {
    if (!searchForm.contains(e.target)) hideDropdown();
  });
}

// ==========================================
// SMART FILTERS
// ==========================================

function initFilters() {
  document.getElementById('filterBar').addEventListener('click', (e) => {
    const chip = e.target.closest('.filter-chip');
    if (!chip) return;
    const category = chip.dataset.filter;
    const value    = chip.dataset.value;

    if (activeFilters[category] === value) {
      activeFilters[category] = null;
      chip.classList.remove('active');
    } else {
      document.querySelectorAll(`.filter-chip[data-filter="${category}"].active`)
        .forEach(c => c.classList.remove('active'));
      activeFilters[category] = value;
      chip.classList.add('active');
    }
    updateFilterBadges();
    maybeReSearch();
  });

  filterMoreBtn.addEventListener('click', () => {
    const isOpen = filterExpanded.classList.toggle('open');
    filterMoreBtn.classList.toggle('active', isOpen);
    filterMoreBtn.querySelector('.filter-more-text').textContent = isOpen ? 'Less' : 'Filters';
    filterMoreBtn.querySelector('.filter-more-icon').textContent = isOpen ? '⊖' : '⊕';
  });

  filterClearAll.addEventListener('click', () => {
    clearAllFilters();
    maybeReSearch();
  });
}

function clearAllFilters() {
  Object.keys(activeFilters).forEach(k => { activeFilters[k] = null; });
  document.querySelectorAll('.filter-chip.active').forEach(c => c.classList.remove('active'));
  updateFilterBadges();
}

function updateFilterBadges() {
  filterBadgeList.innerHTML = '';
  let count = 0;
  Object.entries(activeFilters).forEach(([category, value]) => {
    if (!value) return;
    count++;
    const label = category === 'language' ? (LANGUAGE_LABELS[value] || value) : value;
    const badge = document.createElement('div');
    badge.className = 'filter-badge';
    badge.innerHTML = `${escapeHtml(label)}<button class="filter-badge-remove" aria-label="Remove ${escapeHtml(label)} filter">×</button>`;
    badge.querySelector('.filter-badge-remove').addEventListener('click', () => {
      const chip = document.querySelector(`.filter-chip[data-filter="${category}"][data-value="${CSS.escape(value)}"]`);
      if (chip) chip.classList.remove('active');
      activeFilters[category] = null;
      updateFilterBadges();
      maybeReSearch();
    });
    filterBadgeList.appendChild(badge);
  });
  const hasAny = count > 0;
  const footer = document.getElementById('filterFooter');
  if (footer) footer.style.display = hasAny ? 'flex' : 'none';

  // Update "More Filters" button badge (era + lang + mood only)
  const moreCount = ['era', 'language', 'mood'].filter(k => activeFilters[k]).length;
  if (filterMoreCount) {
    filterMoreCount.textContent = moreCount;
    filterMoreCount.style.display = moreCount > 0 ? 'inline' : 'none';
  }
  // Auto-open expanded section if a hidden filter is active
  if (moreCount > 0 && filterExpanded && !filterExpanded.classList.contains('open')) {
    filterExpanded.classList.add('open');
    filterMoreBtn.classList.add('active');
    filterMoreBtn.querySelector('.filter-more-text').textContent = 'Less';
    filterMoreBtn.querySelector('.filter-more-icon').textContent = '⊖';
  }
}

// More specific era text so YouTube understands what decade we mean
const ERA_QUERIES = {
  '70s':   '1970s classic',
  '80s':   '1980s classic',
  '90s':   '1990s',
  '2000s': 'early 2000s',
  '2010s': '2010s',
  '2020s': '2020 2021 2022 2023 2024 new',
};

function buildQuery(baseQuery) {
  const base = baseQuery.trim();
  const parts = base ? [base] : [];
  if (activeFilters.genre) parts.push(activeFilters.genre);
  if (activeFilters.era) {
    const eraText = ERA_QUERIES[activeFilters.era] || activeFilters.era;
    parts.push(base ? eraText : `${eraText} hits`);
  }
  if (activeFilters.mood)  parts.push(MOOD_KEYWORDS[activeFilters.mood] || activeFilters.mood);
  // Always include language name in query — relevanceLanguage alone is only a hint
  if (activeFilters.language) parts.push(LANGUAGE_LABELS[activeFilters.language] || activeFilters.language);
  return parts.join(' ');
}

function getDiscoveryTitle() {
  const parts = [];
  if (activeFilters.mood)     parts.push(activeFilters.mood);
  if (activeFilters.genre)    parts.push(activeFilters.genre);
  if (activeFilters.era)      parts.push(activeFilters.era);
  if (activeFilters.language) parts.push(LANGUAGE_LABELS[activeFilters.language] || activeFilters.language);
  return parts.join(' · ');
}

function maybeReSearch() {
  const query = searchInput.value.trim();
  if (query) { doSearch(query); return; }
  const hasFilters = Object.values(activeFilters).some(Boolean);
  if (hasFilters) doSearch('');
}

// ==========================================
// PARTICLES
// ==========================================

function initParticles() {
  const notes = ['♪', '♫', '♩', '♬', '🎵', '🎶', '♭', '♮'];
  const count = window.innerWidth < 640 ? 10 : 20;

  for (let i = 0; i < count; i++) {
    const el = document.createElement('span');
    el.className = 'particle';
    el.textContent = notes[Math.floor(Math.random() * notes.length)];
    const dur = 12 + Math.random() * 18;
    const delay = -Math.random() * dur;
    const op = 0.04 + Math.random() * 0.1;
    el.style.cssText = `
      left: ${Math.random() * 100}vw;
      font-size: ${10 + Math.random() * 18}px;
      animation-duration: ${dur}s;
      animation-delay: ${delay}s;
      --op: ${op};
      opacity: ${op};
      color: hsl(${270 + Math.random() * 60}, 80%, 70%);
    `;
    particles.appendChild(el);
  }
}

// ==========================================
// YOUTUBE IFRAME API
// ==========================================

function waitForYtReady(timeout = 8000) {
  return new Promise(resolve => {
    if (ytReady) return resolve();
    const iv = setInterval(() => { if (ytReady) { clearInterval(iv); resolve(); } }, 150);
    setTimeout(() => { clearInterval(iv); resolve(); }, timeout);
  });
}

function onYouTubeIframeAPIReady() {
  ytReady = true;
  if (pendingVideoId !== null) {
    loadPlayer(pendingVideoId, _pendingStartSec);
    pendingVideoId = null;
    _pendingStartSec = 0;
  }
}

function loadPlayer(videoId, startSeconds = 0) {
  resumeBanner.style.display = 'none';
  if (playerResumeOverlay) playerResumeOverlay.style.display = 'none';
  _updateVideoUrl(videoId);
  if (ytPlayer) {
    if (startSeconds > 2) {
      ytPlayer.loadVideoById({ videoId, startSeconds: Math.floor(startSeconds) });
    } else {
      ytPlayer.loadVideoById(videoId);
    }
  } else {
    const playerVars = { autoplay: 1, rel: 0, modestbranding: 1, origin: window.location.origin };
    if (startSeconds > 2) playerVars.start = Math.floor(startSeconds);
    ytPlayer = new YT.Player('ytPlayer', {
      videoId,
      playerVars,
      events: {
        onReady: (e) => {
          e.target.playVideo();
          // If video was loaded via shared URL with no local metadata, fetch it now
          if (currentVideo && currentVideo.title === 'Loading…') {
            const d = e.target.getVideoData();
            if (d && d.title) {
              currentVideo.title   = d.title;
              currentVideo.channel = d.author || '';
              playerTitle.textContent   = d.title;
              playerChannel.textContent = d.author || '';
              updateMiniInfo(currentVideo);
              fetchLyrics(d.title);
              fetchRecommendations(d.title);
              addToHistory(currentVideo);
              updatePlayerFavBtn();
            }
          }
        },
        onStateChange: onPlayerStateChange,
        onError:       onPlayerError,
      },
    });
  }
}

function onPlayerStateChange(e) {
  const playing = e.data === YT.PlayerState.PLAYING;
  equalizer.classList.toggle('playing', playing);
  playerContainer.classList.toggle('playing', playing);
  document.body.classList.toggle('concert-live', playing);
  miniPlayPause.textContent = playing ? '⏸' : '▶';

  // EQ bars: animate when playing, freeze when paused/stopped
  if (miniEq) miniEq.classList.toggle('paused', !playing);

  // Progress bar: poll when playing, pause otherwise
  if (playing) _startProgressBar();
  else if (e.data !== YT.PlayerState.BUFFERING) _stopProgressBar();

  // Synced lyrics: start on PLAYING, pause interval on PAUSED/STOPPED (not BUFFERING)
  if (_syncActive) {
    const targetBody = singMode.style.display !== 'none' ? singBody : lyricsBody;
    if (playing) {
      startLrcSync(targetBody);
    } else if (e.data === YT.PlayerState.PAUSED || e.data === YT.PlayerState.ENDED) {
      _pauseSyncInterval();
    }
  }

  if (e.data === YT.PlayerState.ENDED) playNext();
}

function onPlayerError(e) {
  // 101/150 = video blocked for embedding, 2 = invalid ID, 5 = HTML5 error
  const blocked = [2, 101, 150];
  if (blocked.includes(e.data)) {
    showToast('Skipping blocked video…');
    // Remove from results so it doesn't loop back
    if (currentResults.length > 1) {
      currentResults.splice(currentIndex, 1);
      currentIndex = Math.min(currentIndex, currentResults.length - 1);
    }
    playNext();
  }
}

// ==========================================
// SEARCH
// ==========================================

searchForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = searchInput.value.trim();
  if (!query) return;

  await doSearch(query);
});

async function doSearch(query) {
  setLoading(true);
  hideAllStates();
  historySection.style.display  = 'none';
  favoritesSection.style.display = 'none';

  try {
    const builtQuery = buildQuery(query);
    const url = new URL('/api/search', window.location.origin);
    url.searchParams.set('q', builtQuery || 'karaoke');
    if (activeFilters.language) url.searchParams.set('language', activeFilters.language);
    if (activeFilters.era)      url.searchParams.set('era', activeFilters.era);
    const res  = await fetch(url.toString());
    const data = await res.json();
    if (!res.ok || data.error) { showError(data.error || 'API error'); return; }
    const results = data.results || [];
    if (results.length === 0) { showEmpty(); return; }
    currentResults = results;
    currentIndex   = -1;
    renderResults(query || getDiscoveryTitle() || builtQuery, results);
    if (query) saveQuery(query);
    hideDropdown();
  } catch {
    showError('Network error — check your connection.');
  } finally {
    setLoading(false);
  }
}

// ==========================================
// RENDER RESULTS
// ==========================================

function renderResults(query, results) {
  resultsTitle.innerHTML = `Karaoke results for <span>"${escapeHtml(query)}"</span>`;
  resultsGrid.innerHTML = '';
  results.forEach((video, i) => {
    resultsGrid.appendChild(createCard(video, i));
  });
  resultsSection.style.display = 'block';
  setTimeout(() => resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
}

function createCard(video, index) {
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.index = index;
  const faved = isFavorited(video.video_id);

  card.innerHTML = `
    <div class="card-thumb-wrap">
      <img class="card-thumb" src="${escapeHtml(video.thumbnail)}" alt="${escapeHtml(video.title)}" loading="lazy" />
      <div class="card-play-overlay">▶</div>
    </div>
    <div class="card-num">#${index + 1}</div>
    <button class="heart-btn ${faved ? 'active' : ''}" title="Save to favorites" type="button">${faved ? '❤️' : '🤍'}</button>
    <button class="queue-btn" title="Add to queue" type="button">＋</button>
    <div class="card-body">
      <div class="card-title">${escapeHtml(video.title)}</div>
      <div class="card-channel">${escapeHtml(video.channel)}</div>
    </div>
  `;

  card.querySelector('.heart-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    const btn = e.currentTarget;
    const isNowFaved = toggleFavorite(video);
    btn.classList.toggle('active', isNowFaved);
    btn.textContent = isNowFaved ? '❤️' : '🤍';
  });

  card.querySelector('.queue-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    addToQueue(video);
  });

  card.addEventListener('click', () => onCardClick(card, video, index));
  return card;
}

function _setPlayerArt(video) {
  const thumb = video.thumbnail || '';
  if (playerArtBg) {
    playerArtBg.style.backgroundImage = thumb ? `url(${thumb})` : '';
  }
  if (stageArtBg) {
    stageArtBg.style.backgroundImage = thumb ? `url(${thumb})` : '';
  }
  if (playerArtThumb) {
    if (thumb) {
      playerArtThumb.style.backgroundImage = `url(${thumb})`;
      playerArtThumb.classList.add('loaded');
    } else {
      playerArtThumb.style.backgroundImage = '';
      playerArtThumb.classList.remove('loaded');
    }
  }
}

function onCardClick(card, video, index) {
  // Update active card
  document.querySelectorAll('.card.active').forEach(c => {
    c.classList.remove('active');
    const ov = c.querySelector('.card-play-overlay');
    if (ov) ov.innerHTML = '▶';
  });
  card.classList.add('active');
  card.querySelector('.card-play-overlay').innerHTML =
    `<span style="font-size:9px;font-weight:800;letter-spacing:1.5px">NOW SINGING</span><span>♪</span>`;

  currentIndex  = index;
  currentVideo  = video;

  // Update main player info
  playerTitle.textContent   = video.title;
  playerChannel.textContent = video.channel;
  _setPlayerArt(video);
  historySection.style.display  = 'none';
  favoritesSection.style.display = 'none';
  playerSection.style.display = 'block';
  setTimeout(() => window.scrollTo(0, Math.max(0, playerSection.offsetTop - 65)), 0);

  // Update mini player
  updateMiniInfo(video);

  // Load YouTube
  if (ytReady) loadPlayer(video.video_id);
  else pendingVideoId = video.video_id;

  addToHistory(video);
  fetchLyrics(video.title);
  fetchRecommendations(video.title);
  updatePlayerFavBtn();
}

// ==========================================
// NAVIGATION
// ==========================================

prevBtn.addEventListener('click', () => playPrev());
nextBtn.addEventListener('click', () => playNext());
shuffleBtn.addEventListener('click', toggleShuffle);
shuffleAllBtn.addEventListener('click', () => {
  if (currentResults.length === 0) return;
  shuffleMode = true;
  shuffleBtn.classList.add('shuffle-active');
  playAtIndex(Math.floor(Math.random() * currentResults.length));
  showToast('Shuffling all results ⇄', 'success');
});

function toggleShuffle() {
  shuffleMode = !shuffleMode;
  shuffleBtn.classList.toggle('shuffle-active', shuffleMode);
  showToast(shuffleMode ? 'Shuffle ON ⇄' : 'Shuffle OFF', '');
}

function playNext() {
  if (currentResults.length === 0) return;
  let next;
  if (shuffleMode) {
    next = Math.floor(Math.random() * currentResults.length);
  } else {
    next = (currentIndex + 1) % currentResults.length;
  }
  playAtIndex(next);
  const video = currentResults[next];
  if (video) showToast(`▶ ${video.title.substring(0, 40)}...`, 'upnext');
}

function playPrev() {
  if (currentResults.length === 0) return;
  const prev = (currentIndex - 1 + currentResults.length) % currentResults.length;
  playAtIndex(prev);
}

function playAtIndex(index) {
  if (index < 0 || index >= currentResults.length) return;
  const video = currentResults[index];
  const cards = resultsGrid.querySelectorAll('.card');
  if (cards[index]) {
    onCardClick(cards[index], video, index);
  } else {
    // No DOM cards (e.g. playing from queue/history) — load directly
    currentIndex  = index;
    currentVideo  = video;
    playerTitle.textContent   = video.title;
    playerChannel.textContent = video.channel || '';
    _setPlayerArt(video);
    historySection.style.display  = 'none';
    favoritesSection.style.display = 'none';
    playerSection.style.display = 'block';
    setTimeout(() => window.scrollTo(0, Math.max(0, playerSection.offsetTop - 65)), 0);
    updateMiniInfo(video);
    if (ytReady) loadPlayer(video.video_id);
    else pendingVideoId = video.video_id;
    addToHistory(video);
    fetchLyrics(video.title);
    fetchRecommendations(video.title);
    updatePlayerFavBtn();
  }
  // Refresh now-playing highlight in queue panel if open
  if (queuePanel && queuePanel.style.display !== 'none') renderQueueList();
}

// ==========================================
// CLOSE PLAYER
// ==========================================

playerFavBtn.addEventListener('click', () => {
  if (!currentVideo) return;
  const isNowFaved = toggleFavorite(currentVideo);
  updatePlayerFavBtn();
  // Also sync heart btn on the active card in results grid
  const activeCard = document.querySelector('.card.active');
  if (activeCard) {
    const hb = activeCard.querySelector('.heart-btn');
    if (hb) { hb.classList.toggle('active', isNowFaved); hb.textContent = isNowFaved ? '❤️' : '🤍'; }
  }
});

closePlayerBtn.addEventListener('click', () => {
  document.body.classList.remove('url-video'); // restore full hero
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// Backdrop is hidden in stage mode; no-op
playerBackdrop.addEventListener('click', () => {});

// Back button: if URL no longer has ?v=, restore hero and scroll home
window.addEventListener('popstate', () => {
  if (!new URLSearchParams(location.search).get('v')) {
    document.body.classList.remove('url-video');
    if (currentVideo) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      showToast('Music keeps playing ↓', '');
    }
  }
});

// Mini-stop: actually stop everything
miniStop.addEventListener('click', () => {
  document.body.classList.remove('url-video');
  playerSection.classList.remove('has-lyrics');
  if (ytPlayer) ytPlayer.stopVideo();
  currentVideo = null;
  try { history.replaceState({}, '', '/'); } catch {}
  hideMiniPlayer();
  playerSection.style.display = 'none';
  lyricsSection.style.display = 'none';
  equalizer.classList.remove('playing');
  playerContainer.classList.remove('playing');
  if (playerArtBg) playerArtBg.style.backgroundImage = '';
  if (stageArtBg)  stageArtBg.style.backgroundImage  = '';
  if (playerArtThumb) { playerArtThumb.style.backgroundImage = ''; playerArtThumb.classList.remove('loaded'); }
  document.querySelectorAll('.card.active').forEach(c => {
    c.classList.remove('active');
    const ov = c.querySelector('.card-play-overlay');
    if (ov) ov.innerHTML = '▶';
  });
  _hideNowPlayingCard();
  renderHistory();
  renderFavorites();
  updatePlayerFavBtn();
});

// ==========================================
// LYRICS
// ==========================================

// ==========================================
// LYRICS — Synced (LRC) + Plain fallback
// ==========================================

let _lrcLines      = [];    // [{time, text, el}]
let _syncInterval  = null;  // setInterval ID
let _syncActive    = false; // true when synced LRC data is loaded
let _userScrolling = false;
let _scrollTimer   = null;

const LRC_OFFSET = 1.5; // seconds — delays highlight to match karaoke track (tune if needed)

function parseLRC(lrc) {
  const lines = [];
  const re = /\[(\d+):(\d+(?:\.\d+)?)\](.*)/g;
  let m;
  while ((m = re.exec(lrc)) !== null) {
    const time = parseInt(m[1], 10) * 60 + parseFloat(m[2]) + LRC_OFFSET;
    lines.push({ time, text: m[3].trim() });
  }
  return lines.sort((a, b) => a.time - b.time);
}

function renderSyncedLyrics(lines, container) {
  container.innerHTML = '';
  lines.forEach((line, i) => {
    const el = document.createElement('div');
    el.className = 'lyric-line' + (line.text ? '' : ' lyric-blank');
    el.textContent = line.text || '';
    container.appendChild(el);
    _lrcLines[i].el = el;
  });
}

// Only clears the polling interval — keeps _lrcLines and _syncActive intact
function _pauseSyncInterval() {
  if (_syncInterval) { clearInterval(_syncInterval); _syncInterval = null; }
}

// Full reset — call when loading a new song
function resetLrcState() {
  _pauseSyncInterval();
  _lrcLines   = [];
  _syncActive = false;
}

function startLrcSync(targetBody) {
  _pauseSyncInterval();                        // stop old interval only
  if (!_lrcLines.length || !ytPlayer) return; // data still intact
  let lastIdx = -1;

  _syncInterval = setInterval(() => {
    if (!ytPlayer || typeof ytPlayer.getCurrentTime !== 'function') return;
    const t = ytPlayer.getCurrentTime();
    let idx = -1;
    for (let i = 0; i < _lrcLines.length; i++) {
      if (_lrcLines[i].time <= t) idx = i;
      else break;
    }
    if (idx === lastIdx || idx < 0) return;
    lastIdx = idx;

    _lrcLines.forEach((l, i) => {
      if (!l.el) return;
      l.el.classList.toggle('lyric-active', i === idx);
      l.el.classList.toggle('lyric-past',   i < idx);
    });

    if (!_userScrolling && _lrcLines[idx].el) {
      _scrollActiveLyric(_lrcLines[idx].el);
    }
  }, 200);
}

// Scroll active lyric into view within its container ONLY — never touch page scroll
function _scrollActiveLyric(el) {
  let node = el.parentElement;
  while (node && node !== document.body) {
    const oy = window.getComputedStyle(node).overflowY;
    if (oy === 'auto' || oy === 'scroll') {
      const elRect   = el.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      node.scrollBy({ top: elRect.top - nodeRect.top - node.clientHeight / 2 + el.clientHeight / 2, behavior: 'smooth' });
      return;
    }
    node = node.parentElement;
  }
  // No scrollable container found (mobile layout) — don't scroll the page
}

function _showNowPlayingCard() {
  lyricsSection.style.display = 'none';
  playerSection.classList.add('no-lyrics');
  playerSection.classList.remove('has-lyrics'); // ensure single-column until lyrics ready
  nowPlayingCard.style.display = 'block';
  if (currentVideo) {
    npTitle.textContent  = currentVideo.title || '';
    npArtist.textContent = currentVideo.channel ? `by ${currentVideo.channel}` : '';
  }
}

function _hideNowPlayingCard() {
  playerSection.classList.remove('no-lyrics');
  nowPlayingCard.style.display = 'none';
}

async function fetchLyrics(videoTitle, preserveLayout) {
  resetLrcState();

  if (preserveLayout) {
    // Refresh mode: keep 2-column layout, show loading skeleton in lyrics panel
    playerSection.classList.add('has-lyrics');
    nowPlayingCard.style.display  = 'none';
    lyricsLoading.style.display   = 'block';
    lyricsText.style.display      = 'none';
    lyricsNotFound.style.display  = 'none';
    lyricsSection.style.display   = 'block';
    showToast('[DEBUG] skeleton shown', '');
  } else {
    // Normal mode: start with vibes card, upgrade to 2-column if lyrics found
    _showNowPlayingCard();
    lyricsSection.style.display = 'none';
  }

  try {
    const res  = await fetch(`/api/lyrics?title=${encodeURIComponent(videoTitle)}`);
    const data = await res.json();
    showToast('[DEBUG] fetch done: ' + (data.error || (data.lyrics ? 'has lyrics' : 'empty')), '');
    if (!res.ok || data.error) {
      if (preserveLayout) {
        playerSection.classList.remove('has-lyrics');
        _showNowPlayingCard();
        lyricsSection.style.display = 'none';
      }
      return;
    }

    lyricsTitle.textContent = data.song || 'Lyrics';
    const artistLabel = data.artist ? `by ${data.artist}` : '';
    const aiBadge = data.source === 'ai' ? ' <span class="ai-badge">✦ AI</span>' : '';
    lyricsArtist.innerHTML = escapeHtml(artistLabel) + aiBadge;
    lyricsLoading.style.display  = 'none';
    lyricsNotFound.style.display = 'none';

    if (data.syncedLyrics) {
      _lrcLines  = parseLRC(data.syncedLyrics);
      _syncActive = true;
      lyricsText.className = 'lyrics-text synced';
      renderSyncedLyrics(_lrcLines, lyricsText);
      lyricsText.style.display = 'block';
      lyricsBody.scrollTop = 0;
    } else {
      _syncActive = false;
      lyricsText.className = 'lyrics-text';
      lyricsText.innerHTML = formatLyrics(data.lyrics);
      lyricsText.style.display = 'block';
      lyricsBody.scrollTop = 0;
    }

    playerSection.classList.add('has-lyrics');
    _hideNowPlayingCard();
    lyricsSection.style.display = 'block';
    showToast('[DEBUG] lyrics populated OK', '');

    if (_syncActive && ytPlayer && ytPlayer.getPlayerState &&
        ytPlayer.getPlayerState() === YT.PlayerState.PLAYING) {
      startLrcSync(lyricsBody);
    }
  } catch (err) {
    showToast('[DEBUG] ERROR: ' + err.message, '');
    playerSection.classList.remove('has-lyrics');
    _showNowPlayingCard();
    lyricsSection.style.display = 'none';
  }
}

function formatLyrics(raw) {
  return escapeHtml(raw).split('\n').map(line => {
    if (line.trim().length > 3 && line.trim() === line.trim().toUpperCase() && /[A-Z]/.test(line)) {
      return `<span class="chorus-line">${line}</span>`;
    }
    return line;
  }).join('\n');
}

// Pause auto-scroll briefly when user manually scrolls the lyrics panel
// Listen on lyricsSection too — that's the real scroller in player context
function _onManualScroll() {
  _userScrolling = true;
  clearTimeout(_scrollTimer);
  _scrollTimer = setTimeout(() => { _userScrolling = false; }, 3000);
}
lyricsBody.addEventListener('scroll',    _onManualScroll, { passive: true });
lyricsSection.addEventListener('scroll', _onManualScroll, { passive: true });

// ---- Sing Mode ----
lyricsExpand.addEventListener('click', openSingMode);
singClose.addEventListener('click', closeSingMode);

function openSingMode() {
  if (lyricsText.style.display === 'none') return;
  singTitle.textContent  = lyricsTitle.textContent;
  singArtist.innerHTML   = lyricsArtist.innerHTML;
  singMode.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  if (_syncActive && _lrcLines.length) {
    // Re-render synced lines in sing mode body
    singBody.innerHTML = '';
    singBody.className = 'sing-body synced';
    _lrcLines.forEach((line, i) => {
      const el = document.createElement('div');
      el.className = 'lyric-line';
      if (_lrcLines[i].el) el.className = _lrcLines[i].el.className; // carry over active/past
      el.textContent = line.text || ' ';
      if (!line.text) el.classList.add('lyric-blank');
      singBody.appendChild(el);
      _lrcLines[i].el = el; // redirect sync to sing mode elements
    });
    startLrcSync(singBody);

    // Pause scrolling on manual scroll in sing mode too
    singBody.addEventListener('scroll', () => {
      _userScrolling = true;
      clearTimeout(_scrollTimer);
      _scrollTimer = setTimeout(() => { _userScrolling = false; }, 3000);
    }, { passive: true, once: false });
  } else {
    singBody.innerHTML = lyricsText.innerHTML;
    singBody.className = 'sing-body';
  }
}

function closeSingMode() {
  singMode.style.display = 'none';
  document.body.style.overflow = '';
  // Redirect sync back to the sidebar lyrics panel
  if (_syncActive && _lrcLines.length) {
    _lrcLines.forEach((line, i) => {
      const el = lyricsText.children[i];
      if (el) _lrcLines[i].el = el;
    });
    startLrcSync(lyricsBody);
  }
}


// ==========================================
// HISTORY
// ==========================================

// ==========================================
// RESUME BANNER
// ==========================================

function showResumeBanner() {
  if (resumeBanner.style.display === 'flex') return; // already showing
  if (playerSection.style.display === 'block') return; // player already open — no banner needed

  // Prefer _POS_KEY (most recent position, always consistent with continue-singing strip)
  let v = null, startSec = 0;
  try {
    const saved = JSON.parse(localStorage.getItem(_POS_KEY) || 'null');
    if (saved && saved.video_id && (Date.now() - saved.savedAt < 4 * 3600 * 1000)) {
      v = { video_id: saved.video_id, title: saved.title, channel: saved.channel || '', thumbnail: saved.thumbnail || '' };
      startSec = Math.max(0, (saved.time || 0) - 2);
    } else if (saved) {
      localStorage.removeItem(_POS_KEY);
    }
  } catch {}

  // Fall back to history if no recent position saved
  if (!v) {
    let hist = getHistory();
    if (!hist.length) {
      try { hist = JSON.parse(localStorage.getItem('ks_history') || '[]'); } catch { hist = []; }
    }
    if (!hist.length) return;
    v = hist[0];
    if (!v || !v.video_id) return;
    startSec = Math.max(0, _getSavedTime(v.video_id) - 2);
  }

  resumeBannerBtn.style.display = '';
  resumeBannerText.textContent = v.title;
  resumeBanner.style.display = 'flex';

  resumeBannerBtn.onclick = () => {
    resumeBanner.style.display = 'none';
    currentResults = [v]; currentIndex = 0; currentVideo = v;
    playerTitle.textContent   = v.title;
    playerChannel.textContent = v.channel || '';
    _setPlayerArt(v);
    historySection.style.display  = 'none';
    favoritesSection.style.display = 'none';
    playerSection.style.display = 'block';
    setTimeout(() => window.scrollTo(0, Math.max(0, playerSection.offsetTop - 65)), 0);
    updateMiniInfo(v);
    showMiniPlayer();
    fetchLyrics(v.title);
    addToHistory(v);
    updatePlayerFavBtn();
    waitForYtReady().then(() => loadPlayer(v.video_id, startSec));
  };

  resumeBannerDismiss.onclick = () => {
    resumeBanner.style.display = 'none';
  };
}

const HIST_MAX = 10;

function histKey() {
  return _currentUid ? `ks_history_${_currentUid}` : 'ks_history_guest';
}

function getHistory() {
  try { return JSON.parse(localStorage.getItem(histKey()) || '[]'); }
  catch { return []; }
}

function addToHistory(video) {
  let hist = getHistory().filter(v => v.video_id !== video.video_id);
  hist.unshift({ video_id: video.video_id, title: video.title, channel: video.channel, thumbnail: video.thumbnail });
  if (hist.length > HIST_MAX) hist = hist.slice(0, HIST_MAX);
  localStorage.setItem(histKey(), JSON.stringify(hist));

  /* Sync to Firestore if user is signed in */
  if (window.karaokAuth?.user) window.karaokAuth.saveHistory(video);
}

function renderHistory() {
  const hist = getHistory();
  if (hist.length === 0 || resultsSection.style.display !== 'none' || playerSection.style.display === 'block') {
    historySection.style.display = 'none'; return;
  }
  historyStrip.innerHTML = hist.map(v => `
    <div class="history-card" data-id="${escapeHtml(v.video_id)}">
      <img src="${escapeHtml(v.thumbnail)}" alt="${escapeHtml(v.title)}" loading="lazy" />
      <div class="history-card-title">${escapeHtml(v.title)}</div>
      <button class="strip-queue-btn" title="Add to queue" type="button">＋</button>
    </div>
  `).join('');
  historyStrip.querySelectorAll('.history-card').forEach(hc => {
    hc.querySelector('.strip-queue-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      const video = hist.find(v => v.video_id === hc.dataset.id);
      if (video) addToQueue(video);
    });
    hc.addEventListener('click', () => {
      const video = hist.find(v => v.video_id === hc.dataset.id);
      if (!video) return;
      currentResults = [video]; currentIndex = 0; currentVideo = video;
      playerTitle.textContent   = video.title;
      playerChannel.textContent = video.channel;
      _setPlayerArt(video);
      historySection.style.display  = 'none';
      favoritesSection.style.display = 'none';
      playerSection.style.display = 'block';
      setTimeout(() => window.scrollTo(0, Math.max(0, playerSection.offsetTop - 65)), 0);
      updateMiniInfo(video);
      const _hs = Math.max(0, _getSavedTime(video.video_id) - 2);
      if (ytReady) loadPlayer(video.video_id, _hs);
      else { pendingVideoId = video.video_id; _pendingStartSec = _hs; }
      fetchLyrics(video.title);
      addToHistory(video);
      updatePlayerFavBtn();
    });
  });
  historySection.style.display = 'block';
}

// ==========================================
// MINI PLAYER
// ==========================================

function updateMiniInfo(video) {
  const alreadyVisible = miniVisible;
  if (alreadyVisible) {
    // Fade info out, swap, fade back in
    miniPlayer.classList.add('song-changing');
    setTimeout(() => {
      miniTitle.textContent   = video.title;
      miniChannel.textContent = video.channel || '';
      if (video.thumbnail) miniThumb.src = video.thumbnail;
      miniPlayer.classList.remove('song-changing');
      _triggerMiniGlow();
    }, 160);
  } else {
    miniTitle.textContent   = video.title;
    miniChannel.textContent = video.channel || '';
    if (video.thumbnail) miniThumb.src = video.thumbnail;
  }
  _startProgressBar();
}

function _triggerMiniGlow() {
  miniPlayer.classList.remove('song-loaded');
  void miniPlayer.offsetWidth; // reflow to restart animation
  miniPlayer.classList.add('song-loaded');
  setTimeout(() => miniPlayer.classList.remove('song-loaded'), 1000);
}

function _startProgressBar() {
  clearInterval(progressInterval);
  progressInterval = setInterval(() => {
    if (!miniProgressFill || !ytPlayer || typeof ytPlayer.getCurrentTime !== 'function') return;
    try {
      const curr = ytPlayer.getCurrentTime();
      const dur  = ytPlayer.getDuration();
      if (dur > 0) miniProgressFill.style.width = ((curr / dur) * 100).toFixed(2) + '%';
    } catch { /* ytPlayer not ready */ }
  }, 500);
}

function _stopProgressBar() {
  clearInterval(progressInterval);
  progressInterval = null;
}

function showMiniPlayer() {
  if (!currentVideo) return;
  miniPlayer.style.display = 'flex';
  miniVisible = true;
  _triggerMiniGlow();
  _startProgressBar(); // restart interval — hideMiniPlayer() cleared it and reset bar to 0%
}

function hideMiniPlayer() {
  miniPlayer.style.display = 'none';
  miniVisible = false;
  _stopProgressBar();
  if (miniProgressFill) miniProgressFill.style.width = '0%';
}

// IntersectionObserver: show mini player when main player is out of view
const playerObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (!currentVideo) return;
    if (entry.isIntersecting) {
      hideMiniPlayer();
    } else {
      showMiniPlayer();
    }
  });
}, { threshold: 0.1 });

// Observe playerSection whenever it becomes visible
const playerSectionObserver = new MutationObserver(() => {
  if (playerSection.style.display !== 'none') {
    playerObserver.observe(playerSection);
    // Immediately hide mini player; each caller handles its own scroll.
    hideMiniPlayer();
  } else {
    playerObserver.unobserve(playerSection);
    if (currentVideo) showMiniPlayer();
    else hideMiniPlayer();
  }
});
playerSectionObserver.observe(playerSection, { attributes: true, attributeFilter: ['style'] });

// Mini player controls
miniPrev.addEventListener('click', playPrev);
miniNext.addEventListener('click', playNext);
miniPlayPause.addEventListener('click', () => {
  if (!ytPlayer) return;
  const state = ytPlayer.getPlayerState();
  if (state === YT.PlayerState.PLAYING) ytPlayer.pauseVideo();
  else ytPlayer.playVideo();
});
miniBack.addEventListener('click', () => {
  // Scroll to the stage (it's already visible in the page flow)
  if (currentVideo) playerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

// Seekable progress bar: click to seek
miniProgress.addEventListener('click', (e) => {
  if (!ytPlayer || typeof ytPlayer.getDuration !== 'function') return;
  try {
    const rect = miniProgress.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const duration = ytPlayer.getDuration();
    if (duration > 0) ytPlayer.seekTo(ratio * duration, true);
  } catch { /* ytPlayer not ready */ }
});

// ==========================================
// KEYBOARD SHORTCUTS
// ==========================================

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (singMode.style.display !== 'none' && e.key === 'Escape') { closeSingMode(); return; }

  switch (e.key) {
    case ' ':
    case 'k':
      e.preventDefault();
      if (!ytPlayer) return;
      if (ytPlayer.getPlayerState() === YT.PlayerState.PLAYING) ytPlayer.pauseVideo();
      else ytPlayer.playVideo();
      break;
    case 'ArrowRight':
    case 'n':
      e.preventDefault();
      playNext();
      break;
    case 'ArrowLeft':
    case 'p':
      e.preventDefault();
      playPrev();
      break;
    case 'f':
      e.preventDefault();
      openSingMode();
      break;
    case 'Escape':
      closeSingMode();
      break;
  }
});

// ==========================================
// TOASTS
// ==========================================

function showToast(message, type = '') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('dismissing');
    setTimeout(() => toast.remove(), 220);
  }, 3000);
}

// ==========================================
// STATE HELPERS
// ==========================================

function hideAllStates() {
  resultsSection.style.display  = 'none';
  emptyState.style.display      = 'none';
  errorState.style.display      = 'none';
  lyricsSection.style.display   = 'none';
}

function setLoading(on) {
  loadingOverlay.style.display = on ? 'block' : 'none';
  searchBtn.disabled = on;
  // Update text node inside button (last child after the emoji span)
  const spans = searchBtn.querySelectorAll('span');
  if (spans.length >= 2) spans[1].textContent = on ? ' Searching...' : ' Search';
}

function showEmpty() { emptyState.style.display = 'block'; }
function showError(msg) {
  errorMsg.textContent = msg || 'Could not load results — try a different search or check your connection.';
  errorState.style.display = 'block';
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ==========================================
// TRENDING
// ==========================================

async function fetchTrending() {
  try {
    const res  = await fetch('/api/trending');
    const data = await res.json();
    const songs = data.songs || [];
    trendingChips.innerHTML = '';
    songs.forEach(s => {
      const q = s.artist ? `${s.artist} ${s.song}` : s.song;
      const btn = document.createElement('button');
      btn.className = 'qp-chip';
      btn.dataset.q = q;
      btn.textContent = s.song;
      btn.addEventListener('click', () => {
        searchInput.value = q;
        clearAllFilters();
        doSearch(q);
      });
      trendingChips.appendChild(btn);
    });
  } catch { /* keep default chips empty on error */ }
}

// ==========================================
// RECOMMENDATIONS
// ==========================================

// ==========================================
// FAVORITES
// ==========================================

function getFavorites() {
  const key = favKey();
  if (!key) return [];
  try { return JSON.parse(localStorage.getItem(key) || '[]'); }
  catch { return []; }
}

function isFavorited(video_id) {
  return getFavorites().some(v => v.video_id === video_id);
}

function toggleFavorite(video) {
  const key = favKey();
  if (!key) { showToast('Sign in to save songs ❤️', ''); return false; }
  let favs = getFavorites();
  const idx = favs.findIndex(v => v.video_id === video.video_id);
  let isNowFaved;
  if (idx >= 0) {
    favs.splice(idx, 1);
    isNowFaved = false;
    showToast('Removed from saved songs', '');
  } else {
    favs.unshift({ video_id: video.video_id, title: video.title, channel: video.channel, thumbnail: video.thumbnail });
    if (favs.length > FAV_MAX) favs = favs.slice(0, FAV_MAX);
    isNowFaved = true;
    showToast('❤️ Saved!', 'fav');
  }
  localStorage.setItem(key, JSON.stringify(favs));
  renderFavorites();
  updatePlayerFavBtn();
  return isNowFaved;
}

function renderFavorites() {
  const favs = getFavorites();
  if (favs.length === 0 || resultsSection.style.display !== 'none' || playerSection.style.display === 'block') {
    favoritesSection.style.display = 'none';
    // Still refresh the heart button even when hiding the section (Firestore just loaded)
    if (currentVideo) updatePlayerFavBtn();
    return;
  }
  favHeading.innerHTML = `❤️ Saved Songs <span style="color:var(--muted);font-weight:500">(${favs.length})</span>`;
  favoritesStrip.innerHTML = favs.map(v => `
    <div class="fav-card" data-id="${escapeHtml(v.video_id)}">
      <img src="${escapeHtml(v.thumbnail)}" alt="${escapeHtml(v.title)}" loading="lazy" />
      <div class="fav-card-title">${escapeHtml(v.title)}</div>
      <button class="fav-card-heart" title="Remove from saved" type="button">❤️</button>
      <button class="strip-queue-btn" title="Add to queue" type="button">＋</button>
    </div>
  `).join('');
  favoritesStrip.querySelectorAll('.fav-card').forEach(fc => {
    const video = favs.find(v => v.video_id === fc.dataset.id);
    if (!video) return;
    fc.querySelector('.fav-card-heart').addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFavorite(video); // re-renders + calls updatePlayerFavBtn
    });
    fc.querySelector('.strip-queue-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      addToQueue(video);
    });
    fc.addEventListener('click', () => {
      favoritesSection.style.display = 'none';
      historySection.style.display = 'none';
      currentResults = [video]; currentIndex = 0; currentVideo = video;
      playerTitle.textContent   = video.title;
      playerChannel.textContent = video.channel || '';
      _setPlayerArt(video);
      playerSection.style.display = 'block';
      updateMiniInfo(video);
      if (ytReady) loadPlayer(video.video_id);
      else pendingVideoId = video.video_id;
      fetchLyrics(video.title);
      addToHistory(video);
      updatePlayerFavBtn();
      setTimeout(() => playerSection.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
    });
  });
  favoritesSection.style.display = 'block';
}

function updatePlayerFavBtn() {
  if (!playerFavBtn) return;
  const faved = currentVideo && isFavorited(currentVideo.video_id);
  playerFavBtn.textContent = faved ? '♥' : '♡';
  playerFavBtn.classList.toggle('active', !!faved);
}

favClearBtn.addEventListener('click', () => {
  const key = favKey();
  if (key) localStorage.removeItem(key);
  renderFavorites();
  showToast('Favorites cleared', '');
});

// ==========================================
// QUEUE
// ==========================================

function saveQueue() {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(songQueue));
}

function loadQueue() {
  try { songQueue = JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); } catch(e) { songQueue = []; }
  updateQueueUI();
}

function addToQueue(video) {
  if (songQueue.some(v => v.video_id === video.video_id)) {
    showToast('Already in queue', ''); return;
  }
  songQueue.push(video);
  updateQueueUI();
  saveQueue();
  showToast(`🎵 Added to queue (${songQueue.length})`, 'success');
}

function removeFromQueue(video_id) {
  songQueue = songQueue.filter(v => v.video_id !== video_id);
  updateQueueUI();
  saveQueue();
}

function clearQueue() {
  songQueue = [];
  updateQueueUI();
  saveQueue();
}

function updateQueueUI() {
  const count = songQueue.length;
  queueCount.textContent = count;
  queueCount.style.display = count > 0 ? 'flex' : 'none';
  queueToggleBtn.classList.toggle('has-items', count > 0);
  queueSub.textContent = `${count} song${count !== 1 ? 's' : ''}`;
  queuePlay.disabled = count === 0;
  renderQueueList();
}

function renderQueueList() {
  if (songQueue.length === 0) {
    queueList.innerHTML = '<p class="queue-empty-msg">Your queue is empty.<br>Click ＋ on any song card to add it.</p>';
    return;
  }
  queueList.innerHTML = songQueue.map((v, i) => {
    const isPlaying = currentVideo && v.video_id === currentVideo.video_id;
    return `
    <div class="queue-item${isPlaying ? ' queue-item--playing' : ''}" data-idx="${i}">
      <span class="queue-item-num">${isPlaying ? '▶' : i + 1}</span>
      <img class="queue-item-thumb" src="${escapeHtml(v.thumbnail)}" alt="" loading="lazy" />
      <div class="queue-item-info">
        <div class="queue-item-title">${escapeHtml(v.title)}</div>
        <div class="queue-item-channel">${escapeHtml(v.channel || '')}${isPlaying ? '<span class="queue-now-playing-tag">NOW PLAYING</span>' : ''}</div>
      </div>
      <button class="queue-item-remove" data-id="${escapeHtml(v.video_id)}" title="Remove" type="button">✕</button>
    </div>`;
  }).join('');
  queueList.querySelectorAll('.queue-item-remove').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      removeFromQueue(btn.dataset.id);
    });
  });
  queueList.querySelectorAll('.queue-item').forEach((item) => {
    item.addEventListener('click', (e) => {
      if (e.target.closest('.queue-item-remove')) return;
      const idx = parseInt(item.dataset.idx, 10);
      currentResults = [...songQueue];
      playAtIndex(idx);
      closeQueuePanel();
    });
  });
}

function openQueuePanel() {
  queuePanel.style.display = 'flex';
  renderQueueList();
}

function closeQueuePanel() {
  queuePanel.style.display = 'none';
}

queueToggleBtn.addEventListener('click', () => {
  if (queuePanel.style.display === 'none') openQueuePanel();
  else closeQueuePanel();
});
queueClose.addEventListener('click', closeQueuePanel);
queueClear.addEventListener('click', () => {
  clearQueue();
  showToast('Queue cleared', '');
});
queuePlay.addEventListener('click', () => {
  if (songQueue.length === 0) return;
  currentResults = [...songQueue];
  playAtIndex(0);
  closeQueuePanel();
});

// Close queue panel on outside click
document.addEventListener('click', (e) => {
  if (queuePanel.style.display !== 'none' &&
      !queuePanel.contains(e.target) &&
      !queueToggleBtn.contains(e.target)) {
    closeQueuePanel();
  }
});

// ==========================================
// SHARE
// ==========================================

function shareCurrentSong() {
  if (!currentVideo) return;
  const url  = `${window.location.origin}?v=${currentVideo.video_id}`;
  const text = `Sing along with me! 🎤 "${currentVideo.title}" on KaraokeLover.com`;

  if (navigator.share) {
    navigator.share({ title: currentVideo.title, text, url }).catch(() => {});
    return;
  }

  // Desktop fallback: show share modal
  shareModalThumb.src      = currentVideo.thumbnail || '';
  shareModalTitle.textContent   = currentVideo.title;
  shareModalChannel.textContent = currentVideo.channel || '';
  shareModalLink.value     = url;
  const twitterText = encodeURIComponent(`${text}\n${url}`);
  const waText      = encodeURIComponent(`${text} ${url}`);
  shareTwitter.href  = `https://twitter.com/intent/tweet?text=${twitterText}`;
  shareWhatsapp.href = `https://wa.me/?text=${waText}`;
  shareModal.style.display = 'flex';
}

shareSongBtn.addEventListener('click', shareCurrentSong);

shareModalClose.addEventListener('click', () => {
  shareModal.style.display = 'none';
});
shareModal.addEventListener('click', (e) => {
  if (e.target === shareModal) shareModal.style.display = 'none';
});

shareCopyBtn.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(shareModalLink.value);
    shareCopyBtn.textContent = 'Copied!';
    shareCopyBtn.classList.add('copied');
    setTimeout(() => {
      shareCopyBtn.textContent = 'Copy';
      shareCopyBtn.classList.remove('copied');
    }, 2000);
  } catch {
    shareModalLink.select();
    document.execCommand('copy');
  }
});

async function fetchRecommendations(videoTitle) {
  recSection.style.display = 'block';
  recChips.innerHTML = '';
  recLoading.style.display = 'flex';
  try {
    const res  = await fetch(`/api/recommendations?song=${encodeURIComponent(videoTitle)}`);
    const data = await res.json();
    recLoading.style.display = 'none';
    const recs = data.recommendations || [];
    if (recs.length === 0) { recSection.style.display = 'none'; return; }
    recs.forEach(r => {
      const q = r.artist ? `${r.artist} ${r.song}` : r.song;
      const btn = document.createElement('button');
      btn.className = 'rec-chip';
      btn.textContent = `${r.song}${r.artist ? ' — ' + r.artist : ''}`;
      btn.addEventListener('click', () => {
        searchInput.value = q;
        clearAllFilters();
        doSearch(q);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      recChips.appendChild(btn);
    });
    recSection.style.display = 'block';
  } catch {
    recLoading.style.display = 'none';
    recSection.style.display = 'none';
  }
}

