/* ==========================================
   Karaoke Lover v3
   Search · Player · Lyrics · History
   Auto-play · Mini Player
   Keyboard Shortcuts · Shuffle · Sing Mode
   ========================================== */

// ---- Global state ----
let ytPlayer       = null;
let ytReady        = false;
let pendingVideoId = null;
let currentResults = [];
let currentIndex   = -1;
let shuffleMode    = false;
let currentVideo   = null;
let miniVisible    = false;

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
const miniPlayer     = document.getElementById('miniPlayer');
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
const searchDropdown   = document.getElementById('searchDropdown');
const sdList           = document.getElementById('sdList');
const sdClear          = document.getElementById('sdClear');
const particles        = document.getElementById('particles');
const resumeBanner     = document.getElementById('resumeBanner');
const resumeBannerText = document.getElementById('resumeBannerText');
const resumeBannerBtn  = document.getElementById('resumeBannerBtn');
const resumeBannerDismiss = document.getElementById('resumeBannerDismiss');

// ==========================================
// INIT
// ==========================================

initParticles();
renderHistory();
fetchTrending();
initFilters();
initSearchDropdown();

// ==========================================
// SEARCH HISTORY DROPDOWN
// ==========================================

const QUERY_MAX = 4;
let _currentUid  = null;

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

function initSearchDropdown() {
  searchInput.addEventListener('focus', showDropdown);
  searchInput.addEventListener('input', () => renderDropdown(searchInput.value.trim()));
  searchInput.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideDropdown(); });
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
    } else if (user) {
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
    loadPlayer(pendingVideoId);
    pendingVideoId = null;
  }
}

function loadPlayer(videoId) {
  if (ytPlayer) {
    ytPlayer.loadVideoById(videoId);
  } else {
    ytPlayer = new YT.Player('ytPlayer', {
      videoId,
      playerVars: { autoplay: 1, rel: 0, modestbranding: 1, origin: window.location.origin },
      events: {
        onReady:       (e) => e.target.playVideo(),
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
  historySection.style.display = 'none';

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
}

function createCard(video, index) {
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.index = index;

  card.innerHTML = `
    <div class="card-thumb-wrap">
      <img class="card-thumb" src="${escapeHtml(video.thumbnail)}" alt="${escapeHtml(video.title)}" loading="lazy" />
      <div class="card-play-overlay">▶</div>
    </div>
    <div class="card-num">#${index + 1}</div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(video.title)}</div>
      <div class="card-channel">${escapeHtml(video.channel)}</div>
    </div>
  `;

  card.addEventListener('click', () => onCardClick(card, video, index));
  return card;
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
  playerSection.style.display = 'block';
  playerSection.querySelector('.section-wrap').scrollIntoView({ behavior: 'smooth', block: 'start' });

  // Update mini player
  updateMiniInfo(video);

  // Load YouTube
  if (ytReady) loadPlayer(video.video_id);
  else pendingVideoId = video.video_id;

  addToHistory(video);
  fetchLyrics(video.title);
  fetchRecommendations(video.title);
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
    // No DOM cards (e.g. playing from history/favorites) — load directly
    currentIndex  = index;
    currentVideo  = video;
    playerTitle.textContent   = video.title;
    playerChannel.textContent = video.channel || '';
    updateMiniInfo(video);
    if (ytReady) loadPlayer(video.video_id);
    else pendingVideoId = video.video_id;
    addToHistory(video);
    fetchLyrics(video.title);
  }
}

// ==========================================
// CLOSE PLAYER
// ==========================================

closePlayerBtn.addEventListener('click', () => {
  playerSection.style.display = 'none';
  lyricsSection.style.display = 'none';
  equalizer.classList.remove('playing');
  playerContainer.classList.remove('playing');
  hideMiniPlayer();
  if (ytPlayer) ytPlayer.stopVideo();
  document.querySelectorAll('.card.active').forEach(c => {
    c.classList.remove('active');
    const ov = c.querySelector('.card-play-overlay');
    if (ov) ov.innerHTML = '▶';
  });
  currentVideo = null;
  renderHistory();
});

// ==========================================
// LYRICS
// ==========================================

async function fetchLyrics(videoTitle) {
  lyricsSection.style.display  = 'block';
  lyricsText.style.display     = 'none';
  lyricsNotFound.style.display = 'none';
  lyricsLoading.style.display  = 'block';
  lyricsTitle.textContent      = 'Lyrics';
  lyricsArtist.textContent     = '';

  try {
    const res  = await fetch(`/api/lyrics?title=${encodeURIComponent(videoTitle)}`);
    const data = await res.json();
    lyricsLoading.style.display = 'none';
    if (!res.ok || data.error) { lyricsSection.style.display = 'none'; return; }
    lyricsTitle.textContent  = data.song   || 'Lyrics';
    const artistLabel = data.artist ? `by ${data.artist}` : '';
    const aiBadge = data.source === 'ai' ? ' <span class="ai-badge">✦ AI</span>' : '';
    lyricsArtist.innerHTML   = escapeHtml(artistLabel) + aiBadge;
    lyricsText.innerHTML     = formatLyrics(data.lyrics);
    lyricsText.style.display = 'block';
    lyricsBody.scrollTop     = 0;
  } catch {
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

// ---- Sing Mode ----
lyricsExpand.addEventListener('click', openSingMode);
singClose.addEventListener('click', closeSingMode);

function openSingMode() {
  if (lyricsText.style.display === 'none') return;
  singTitle.textContent  = lyricsTitle.textContent;
  singArtist.textContent = lyricsArtist.textContent;
  singBody.innerHTML     = lyricsText.innerHTML;
  singMode.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeSingMode() {
  singMode.style.display = 'none';
  document.body.style.overflow = '';
}


// ==========================================
// HISTORY
// ==========================================

// ==========================================
// RESUME BANNER
// ==========================================

function showResumeBanner() {
  if (resumeBanner.style.display === 'flex') return; // already showing
  // Try UID-keyed history first, then fall back to old global key
  let hist = getHistory();
  if (!hist.length) {
    try { hist = JSON.parse(localStorage.getItem('ks_history') || '[]'); } catch { hist = []; }
  }
  if (!hist.length) return; // no history — nothing to resume
  resumeBannerBtn.style.display = '';
  const v = hist[0]; // most recently played
  if (!v.video_id) return;

  resumeBannerText.textContent = v.title;
  resumeBanner.style.display = 'flex';

  resumeBannerBtn.onclick = () => {
    resumeBanner.style.display = 'none';
    currentResults = [v]; currentIndex = 0; currentVideo = v;
    playerTitle.textContent   = v.title;
    playerChannel.textContent = v.channel || '';
    playerSection.style.display = 'block';
    updateMiniInfo(v);
    fetchLyrics(v.title);
    waitForYtReady().then(() => {
      loadPlayer(v.video_id);
      playerSection.querySelector('.section-wrap')
        .scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
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
  if (hist.length === 0 || resultsSection.style.display !== 'none') {
    historySection.style.display = 'none'; return;
  }
  historyStrip.innerHTML = hist.map(v => `
    <div class="history-card" data-id="${escapeHtml(v.video_id)}">
      <img src="${escapeHtml(v.thumbnail)}" alt="${escapeHtml(v.title)}" loading="lazy" />
      <div class="history-card-title">${escapeHtml(v.title)}</div>
    </div>
  `).join('');
  historyStrip.querySelectorAll('.history-card').forEach(hc => {
    hc.addEventListener('click', () => {
      const video = hist.find(v => v.video_id === hc.dataset.id);
      if (!video) return;
      currentResults = [video]; currentIndex = 0; currentVideo = video;
      playerTitle.textContent   = video.title;
      playerChannel.textContent = video.channel;
      playerSection.style.display = 'block';
      updateMiniInfo(video);
      if (ytReady) loadPlayer(video.video_id);
      else pendingVideoId = video.video_id;
      fetchLyrics(video.title);
      addToHistory(video);
    });
  });
  historySection.style.display = 'block';
}

// ==========================================
// MINI PLAYER
// ==========================================

function updateMiniInfo(video) {
  miniTitle.textContent   = video.title;
  miniChannel.textContent = video.channel;
  if (video.thumbnail) miniThumb.src = video.thumbnail;
}

function showMiniPlayer() {
  if (!currentVideo) return;
  miniPlayer.style.display = 'flex';
  miniVisible = true;
}

function hideMiniPlayer() {
  miniPlayer.style.display = 'none';
  miniVisible = false;
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
  } else {
    playerObserver.unobserve(playerSection);
    hideMiniPlayer();
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
  playerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        activeTab = 'all';
        updateTabs();
        doSearch(q);
      });
      trendingChips.appendChild(btn);
    });
  } catch { /* keep default chips empty on error */ }
}

// ==========================================
// RECOMMENDATIONS
// ==========================================

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
        activeTab = 'all';
        updateTabs();
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

