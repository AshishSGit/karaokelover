/* ==========================================
   Karaoke Lover v3
   Search · Player · Lyrics · History
   Favorites · Auto-play · Mini Player
   Keyboard Shortcuts · Shuffle · Sing Mode
   ========================================== */

// ---- Global state ----
let ytPlayer       = null;
let ytReady        = false;
let pendingVideoId = null;
let currentResults = [];
let currentIndex   = -1;
let activeTab      = 'all';
let shuffleMode    = false;
let currentVideo   = null;
let miniVisible    = false;

// ---- DOM ----
const searchForm     = document.getElementById('searchForm');
const searchInput    = document.getElementById('searchInput');
const searchBtn      = searchForm.querySelector('.search-btn');
const resultsSection = document.getElementById('resultsSection');
const resultsGrid    = document.getElementById('resultsGrid');
const resultsTitle   = document.getElementById('resultsTitle');
const tabsBar        = document.getElementById('tabsBar');
const tabAll         = document.getElementById('tabAll');
const tabFavs        = document.getElementById('tabFavs');
const favCount       = document.getElementById('favCount');
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
const particles      = document.getElementById('particles');

// ==========================================
// INIT
// ==========================================

initParticles();
updateFavCount();
renderHistory();
fetchTrending();

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

// ==========================================
// SEARCH
// ==========================================

searchForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = searchInput.value.trim();
  if (!query) return;
  activeTab = 'all';
  updateTabs();
  await doSearch(query);
});

async function doSearch(query) {
  setLoading(true);
  hideAllStates();
  historySection.style.display = 'none';

  try {
    const res  = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (!res.ok || data.error) { showError(data.error || 'API error'); return; }
    const results = data.results || [];
    if (results.length === 0) { showEmpty(); return; }
    currentResults = results;
    currentIndex   = -1;
    renderResults(query, results);
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
  const favs = getFavorites();
  resultsTitle.innerHTML = `Karaoke results for <span>"${escapeHtml(query)}"</span>`;
  resultsGrid.innerHTML = '';
  results.forEach((video, i) => {
    resultsGrid.appendChild(createCard(video, i, !!favs[video.video_id]));
  });
  resultsSection.style.display = 'block';
  updateFavCount();
}

function createCard(video, index, isFav) {
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.index = index;

  // Determine overlay content
  const overlayHTML = `<span style="font-size:9px;font-weight:800;letter-spacing:1.5px">NOW SINGING</span><span>♪</span>`;

  card.innerHTML = `
    <div class="card-thumb-wrap">
      <img class="card-thumb" src="${escapeHtml(video.thumbnail)}" alt="${escapeHtml(video.title)}" loading="lazy" />
      <div class="card-play-overlay">▶</div>
    </div>
    <div class="card-num">#${index + 1}</div>
    <button class="heart-btn ${isFav ? 'active' : ''}" data-id="${escapeHtml(video.video_id)}">${isFav ? '❤️' : '🤍'}</button>
    <div class="card-body">
      <div class="card-title">${escapeHtml(video.title)}</div>
      <div class="card-channel">${escapeHtml(video.channel)}</div>
    </div>
  `;

  card.querySelector('.heart-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleFavorite(video, card.querySelector('.heart-btn'));
  });

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
    // Card might not be rendered (favorites tab). Load directly.
    currentIndex  = index;
    currentVideo  = video;
    playerTitle.textContent   = video.title;
    playerChannel.textContent = video.channel;
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
// FAVORITES
// ==========================================

const FAV_KEY = 'ks_favorites';

function getFavorites() {
  try { return JSON.parse(localStorage.getItem(FAV_KEY) || '{}'); }
  catch { return {}; }
}

function toggleFavorite(video, btn) {
  const favs  = getFavorites();
  const isFav = !!favs[video.video_id];
  if (isFav) {
    delete favs[video.video_id];
    btn.textContent = '🤍'; btn.classList.remove('active');
    showToast('Removed from favorites', 'fav');
  } else {
    favs[video.video_id] = video;
    btn.textContent = '❤️'; btn.classList.add('active');
    btn.style.animation = 'none';
    requestAnimationFrame(() => { btn.style.animation = ''; });
    showToast('Added to favorites ❤️', 'fav');
  }
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
  updateFavCount();
  if (activeTab === 'favorites') renderFavoritesTab();
}

function updateFavCount() {
  favCount.textContent = Object.keys(getFavorites()).length;
}

function renderFavoritesTab() {
  const list = Object.values(getFavorites());
  resultsTitle.innerHTML = list.length ? `Your <span>Favorites</span> (${list.length})` : '';
  resultsGrid.innerHTML  = '';
  if (list.length === 0) {
    resultsGrid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:60px 0;color:var(--muted);">
      <div style="font-size:44px;margin-bottom:14px;opacity:.4">🤍</div>
      <p>No favorites yet — click the heart on any song!</p>
    </div>`;
    return;
  }
  list.forEach((video, i) => resultsGrid.appendChild(createCard(video, i, true)));
}

tabsBar.addEventListener('click', (e) => {
  const tab = e.target.closest('.tab');
  if (!tab) return;
  activeTab = tab.dataset.tab;
  updateTabs();
  if (activeTab === 'favorites') renderFavoritesTab();
  else if (currentResults.length > 0) renderResults(searchInput.value.trim(), currentResults);
});

function updateTabs() {
  tabAll.classList.toggle('active',  activeTab === 'all');
  tabFavs.classList.toggle('active', activeTab === 'favorites');
  updateFavCount();
}

// ==========================================
// HISTORY
// ==========================================

const HIST_KEY = 'ks_history';
const HIST_MAX = 10;

function getHistory() {
  try { return JSON.parse(localStorage.getItem(HIST_KEY) || '[]'); }
  catch { return []; }
}

function addToHistory(video) {
  let hist = getHistory().filter(v => v.video_id !== video.video_id);
  hist.unshift({ video_id: video.video_id, title: video.title, channel: video.channel, thumbnail: video.thumbnail });
  if (hist.length > HIST_MAX) hist = hist.slice(0, HIST_MAX);
  localStorage.setItem(HIST_KEY, JSON.stringify(hist));
  // Don't re-render history while results are visible
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
