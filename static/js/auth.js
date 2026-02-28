/* =================================================================
   auth.js — Firebase Auth + Firestore for karaokelover.com
   Uses Firebase v10 compat SDK (loaded via CDN in index.html)
   ================================================================= */

/* ----------------------------------------------------------------
   1. FIREBASE CONFIG — fill in your values from Firebase Console
      Project Settings → Your apps → Web app → firebaseConfig
   ---------------------------------------------------------------- */
const firebaseConfig = {
  apiKey:            "AIzaSyC-I95VdxT1IYbY8TU7BTY4eHll5DBwJeM",
  authDomain:        "karaokelover-cb880.firebaseapp.com",
  projectId:         "karaokelover-cb880",
  storageBucket:     "karaokelover-cb880.firebasestorage.app",
  messagingSenderId: "110043722349",
  appId:             "1:110043722349:web:266a1908986fbf0a1d0564",
};

/* ----------------------------------------------------------------
   2. INIT
   ---------------------------------------------------------------- */
firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db   = firebase.firestore();

/* expose so Flask templates / other scripts can access if needed */
window.karaokAuth = {
  user: null,
  signInWithGoogle,
  signInWithEmail,
  signUpWithEmail,
  doSignOut,
  saveFavorite,
  removeFavorite,
  getFavorites,
  saveHistory,
  getHistory,
};

/* ----------------------------------------------------------------
   3. AUTH STATE OBSERVER
   ---------------------------------------------------------------- */
auth.onAuthStateChanged(async (user) => {
  window.karaokAuth.user = user;

  if (user) {
    await _ensureUserDoc(user);
    _migrateLocalStorageIfNeeded(user.uid);
    _updateHeaderLoggedIn(user);
  } else {
    _updateHeaderLoggedOut();
  }

  window.dispatchEvent(new CustomEvent('authStateChanged', { detail: { user } }));
});

/* ----------------------------------------------------------------
   4. AUTH FUNCTIONS
   ---------------------------------------------------------------- */
async function signInWithGoogle() {
  const provider = new firebase.auth.GoogleAuthProvider();
  try {
    await auth.signInWithPopup(provider);
    _closeModal();
  } catch (err) {
    _showAuthError(_friendlyError(err));
  }
}

async function signInWithEmail(email, password) {
  try {
    await auth.signInWithEmailAndPassword(email, password);
    _closeModal();
  } catch (err) {
    _showAuthError(_friendlyError(err));
  }
}

async function signUpWithEmail(email, password, name) {
  try {
    const cred = await auth.createUserWithEmailAndPassword(email, password);
    await cred.user.updateProfile({ displayName: name });
    _closeModal();
  } catch (err) {
    _showAuthError(_friendlyError(err));
  }
}

async function doSignOut() {
  await auth.signOut();
}

/* ----------------------------------------------------------------
   5. FIRESTORE HELPERS
   ---------------------------------------------------------------- */
function _userRef(uid) {
  return db.collection('users').doc(uid);
}

async function _ensureUserDoc(user) {
  const ref = _userRef(user.uid);
  const snap = await ref.get();
  if (!snap.exists) {
    await ref.set({
      displayName: user.displayName || '',
      email:       user.email || '',
      photoURL:    user.photoURL || null,
      createdAt:   firebase.firestore.FieldValue.serverTimestamp(),
      favorites:   [],
      history:     [],
    });
  }
}

async function saveFavorite(video) {
  const user = window.karaokAuth.user;
  if (!user) return;
  const entry = {
    videoId:   video.video_id || video.videoId || '',
    title:     video.title     || '',
    channel:   video.channel   || '',
    thumbnail: video.thumbnail || '',
  };
  await _userRef(user.uid).update({
    favorites: firebase.firestore.FieldValue.arrayUnion(entry),
  });
}

async function removeFavorite(videoId) {
  const user = window.karaokAuth.user;
  if (!user) return;
  const snap = await _userRef(user.uid).get();
  if (!snap.exists) return;
  const current = snap.data().favorites || [];
  const updated = current.filter(f => f.videoId !== videoId);
  await _userRef(user.uid).update({ favorites: updated });
}

async function getFavorites() {
  const user = window.karaokAuth.user;
  if (!user) return [];
  try {
    const snap = await _userRef(user.uid).get();
    return snap.exists ? (snap.data().favorites || []) : [];
  } catch {
    return [];
  }
}

async function saveHistory(video) {
  const user = window.karaokAuth.user;
  if (!user) return;
  const entry = {
    videoId:   video.video_id || video.videoId || '',
    title:     video.title     || '',
    channel:   video.channel   || '',
    thumbnail: video.thumbnail || '',
    playedAt:  new Date().toISOString(),
  };
  try {
    const snap = await _userRef(user.uid).get();
    const current = snap.exists ? (snap.data().history || []) : [];
    /* keep newest at front, dedupe by videoId, max 10 */
    const deduped = [entry, ...current.filter(h => h.videoId !== entry.videoId)].slice(0, 10);
    await _userRef(user.uid).update({ history: deduped });
  } catch { /* non-critical */ }
}

async function getHistory() {
  const user = window.karaokAuth.user;
  if (!user) return [];
  try {
    const snap = await _userRef(user.uid).get();
    return snap.exists ? (snap.data().history || []) : [];
  } catch {
    return [];
  }
}

/* ----------------------------------------------------------------
   6. LOCALSTORAGE MIGRATION (runs once on first sign-in)
   ---------------------------------------------------------------- */
async function _migrateLocalStorageIfNeeded(uid) {
  const MIGRATION_KEY = 'ks_migrated_' + uid;
  if (localStorage.getItem(MIGRATION_KEY)) return;

  const raw = localStorage.getItem('ks_favorites');
  if (!raw) {
    localStorage.setItem(MIGRATION_KEY, '1');
    return;
  }

  try {
    const favs = JSON.parse(raw);
    if (!Array.isArray(favs) || favs.length === 0) {
      localStorage.setItem(MIGRATION_KEY, '1');
      return;
    }

    /* Upload each existing favourite to Firestore */
    const normalised = favs.map(v => ({
      videoId:   v.video_id || v.videoId || '',
      title:     v.title     || '',
      channel:   v.channel   || '',
      thumbnail: v.thumbnail || '',
    }));
    await _userRef(uid).update({ favorites: normalised });

    /* Clear localStorage favourites (Firestore is now the source of truth) */
    localStorage.removeItem('ks_favorites');
    localStorage.setItem(MIGRATION_KEY, '1');

    _showToast(`${favs.length} favourite${favs.length > 1 ? 's' : ''} synced to your account ☁️`, 'fav');
  } catch { /* silent — migration is best-effort */ }
}

/* ----------------------------------------------------------------
   7. HEADER UI HELPERS
   ---------------------------------------------------------------- */
function _updateHeaderLoggedIn(user) {
  const signInBtn    = document.getElementById('headerSignInBtn');
  const avatarWrap   = document.getElementById('userAvatarWrap');
  const userPhoto    = document.getElementById('userPhoto');
  const userInitials = document.getElementById('userInitials');
  const dropdownName  = document.getElementById('dropdownName');
  const dropdownEmail = document.getElementById('dropdownEmail');

  if (signInBtn)  signInBtn.style.display  = 'none';
  if (avatarWrap) avatarWrap.style.display = 'block';

  if (user.photoURL && userPhoto) {
    userPhoto.src           = user.photoURL;
    userPhoto.style.display = 'block';
    if (userInitials) userInitials.style.display = 'none';
  } else if (userInitials) {
    const name = user.displayName || user.email || '?';
    userInitials.textContent    = name.charAt(0).toUpperCase();
    userInitials.style.display  = 'block';
    if (userPhoto) userPhoto.style.display = 'none';
  }

  if (dropdownName)  dropdownName.textContent  = user.displayName || 'Karaoke Fan';
  if (dropdownEmail) dropdownEmail.textContent = user.email || '';
}

function _updateHeaderLoggedOut() {
  const signInBtn  = document.getElementById('headerSignInBtn');
  const avatarWrap = document.getElementById('userAvatarWrap');
  if (signInBtn)  signInBtn.style.display  = 'block';
  if (avatarWrap) avatarWrap.style.display = 'none';
}

/* ----------------------------------------------------------------
   8. MODAL OPEN / CLOSE
   ---------------------------------------------------------------- */
function _openModal(mode) {
  const modal = document.getElementById('authModal');
  if (!modal) return;
  modal.style.display = 'flex';
  _switchMode(mode || 'signin');
  _clearError();
}

function _closeModal() {
  const modal = document.getElementById('authModal');
  if (modal) modal.style.display = 'none';
  _clearError();
}

function _switchMode(mode) {
  const signInForm    = document.getElementById('signInForm');
  const signUpForm    = document.getElementById('signUpForm');
  const title         = document.getElementById('authModalTitle');
  const toggleText    = document.getElementById('authToggleText');
  const toggleBtn     = document.getElementById('authToggleBtn');

  if (mode === 'signup') {
    if (signInForm) signInForm.style.display = 'none';
    if (signUpForm) signUpForm.style.display = 'flex';
    if (title)      title.textContent        = 'Create Account';
    if (toggleText) toggleText.textContent   = 'Already have an account?';
    if (toggleBtn)  toggleBtn.textContent    = 'Sign In';
    toggleBtn && (toggleBtn.dataset.target   = 'signin');
  } else {
    if (signUpForm) signUpForm.style.display = 'none';
    if (signInForm) signInForm.style.display = 'flex';
    if (title)      title.textContent        = 'Welcome Back';
    if (toggleText) toggleText.textContent   = "Don't have an account?";
    if (toggleBtn)  toggleBtn.textContent    = 'Sign Up';
    toggleBtn && (toggleBtn.dataset.target   = 'signup');
  }
}

function _showAuthError(msg) {
  const el = document.getElementById('authError');
  if (el) el.textContent = msg;
}

function _clearError() {
  const el = document.getElementById('authError');
  if (el) el.textContent = '';
}

/* ----------------------------------------------------------------
   9. ERROR MESSAGES
   ---------------------------------------------------------------- */
function _friendlyError(err) {
  const code = err.code || '';
  if (code.includes('user-not-found') || code.includes('wrong-password') || code.includes('invalid-credential'))
    return 'Incorrect email or password.';
  if (code.includes('email-already-in-use'))
    return 'That email is already registered. Try signing in instead.';
  if (code.includes('weak-password'))
    return 'Password must be at least 6 characters.';
  if (code.includes('invalid-email'))
    return 'Please enter a valid email address.';
  if (code.includes('popup-closed'))
    return 'Sign-in popup was closed. Please try again.';
  return err.message || 'Something went wrong. Please try again.';
}

/* ----------------------------------------------------------------
   10. TOAST (reuse script.js showToast if available, else basic)
   ---------------------------------------------------------------- */
function _showToast(msg, type) {
  if (typeof showToast === 'function') {
    showToast(msg, type);
  }
}

/* ----------------------------------------------------------------
   11. DOM EVENT LISTENERS (wired up after DOM ready)
   ---------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {

  /* Open modal from header Sign In button */
  document.getElementById('headerSignInBtn')
    ?.addEventListener('click', () => _openModal('signin'));

  /* Close modal */
  document.getElementById('authModalClose')
    ?.addEventListener('click', _closeModal);

  /* Close on overlay click */
  document.getElementById('authModal')
    ?.addEventListener('click', (e) => {
      if (e.target === e.currentTarget) _closeModal();
    });

  /* Close on Escape */
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const modal = document.getElementById('authModal');
      if (modal && modal.style.display !== 'none') _closeModal();
    }
  });

  /* Toggle between sign-in and sign-up forms */
  document.getElementById('authToggleBtn')
    ?.addEventListener('click', (e) => {
      _clearError();
      _switchMode(e.currentTarget.dataset.target || 'signup');
    });

  /* Google sign-in */
  document.getElementById('googleSignInBtn')
    ?.addEventListener('click', signInWithGoogle);

  /* Email sign-in form */
  document.getElementById('signInForm')
    ?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email    = document.getElementById('siEmail')?.value.trim();
      const password = document.getElementById('siPassword')?.value;
      const btn      = e.currentTarget.querySelector('.auth-submit-btn');
      if (!email || !password) return _showAuthError('Please fill in all fields.');
      btn.disabled = true;
      btn.textContent = 'Signing in…';
      await signInWithEmail(email, password);
      btn.disabled = false;
      btn.textContent = 'Sign In';
    });

  /* Email sign-up form */
  document.getElementById('signUpForm')
    ?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name     = document.getElementById('suName')?.value.trim();
      const email    = document.getElementById('suEmail')?.value.trim();
      const password = document.getElementById('suPassword')?.value;
      const btn      = e.currentTarget.querySelector('.auth-submit-btn');
      if (!name || !email || !password) return _showAuthError('Please fill in all fields.');
      if (password.length < 6)          return _showAuthError('Password must be at least 6 characters.');
      btn.disabled = true;
      btn.textContent = 'Creating account…';
      await signUpWithEmail(email, password, name);
      btn.disabled = false;
      btn.textContent = 'Create Account';
    });

  /* Avatar button — toggle dropdown */
  document.getElementById('userAvatarBtn')
    ?.addEventListener('click', (e) => {
      e.stopPropagation();
      const dd = document.getElementById('userDropdown');
      if (dd) dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
    });

  /* Close dropdown on outside click */
  document.addEventListener('click', () => {
    const dd = document.getElementById('userDropdown');
    if (dd) dd.style.display = 'none';
  });

  /* Sign out */
  document.getElementById('signOutBtn')
    ?.addEventListener('click', doSignOut);
});
