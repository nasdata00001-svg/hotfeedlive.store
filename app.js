// HOTFEED LIVE Application Logic

let trendData = null;
let searchQuery = '';
let remainingSeconds = 3600;
let timerInterval = null;
let isRefreshing = false;
let searchAnalyticsTimer = null;
let lastRenderedPlatforms = 0;

function sanitizeAnalyticsParams(params = {}) {
  const clean = {};
  Object.entries(params).forEach(([key, val]) => {
    if (val === undefined || val === null || val === '') return;
    if (typeof val === 'number') {
      if (Number.isFinite(val)) clean[key] = val;
    } else if (typeof val === 'boolean') {
      clean[key] = val;
    } else {
      clean[key] = String(val).slice(0, 100);
    }
  });
  return clean;
}

function trackEvent(eventName, params = {}) {
  if (!eventName) return;
  const cleanParams = sanitizeAnalyticsParams(params);
  if (typeof window.trackAnalyticsEvent === 'function') {
    window.trackAnalyticsEvent(eventName, cleanParams);
    return;
  }
  window.__pendingAnalyticsEvents = window.__pendingAnalyticsEvents || [];
  if (window.__pendingAnalyticsEvents.length < 50) {
    window.__pendingAnalyticsEvents.push({ name: eventName, params: cleanParams });
  }
}

const timerDisplay = document.getElementById('timerDisplay');
const btnRefresh = document.getElementById('btnRefresh');
const btnRefreshText = document.getElementById('btnRefreshText');
const lastUpdatedText = document.getElementById('lastUpdatedText');
const totalPlatformsVal = document.getElementById('totalPlatformsVal');
const totalKeywordsVal = document.getElementById('totalKeywordsVal');
const trendsGrid = document.getElementById('trendsGrid');
const searchInput = document.getElementById('searchInput');
const clearSearchBtn = document.getElementById('clearSearchBtn');
const toast = document.getElementById('toast');
const toastIcon = document.getElementById('toastIcon');
const toastMsg = document.getElementById('toastMsg');

const IS_LOCAL_SERVER = ['localhost', '127.0.0.1'].includes(window.location.hostname);

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  if (window.INITIAL_TRENDS) {
    applyTrendData(window.INITIAL_TRENDS);
  }
  fetchTrends();
  startCountdown();
  setupEventListeners();
});

function setupEventListeners() {
  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    updateSearchClearState();
    renderGrid();

    clearTimeout(searchAnalyticsTimer);
    if (searchQuery.length > 0) {
      const capturedQuery = searchQuery;
      searchAnalyticsTimer = setTimeout(() => {
        if (searchQuery === capturedQuery) {
          trackEvent('search', {
            search_term: capturedQuery,
            result_platforms: lastRenderedPlatforms,
          });
        }
      }, 800);
    }
  });

  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && searchInput.value) {
      clearSearch();
    }
  });

  if (clearSearchBtn) {
    clearSearchBtn.addEventListener('click', clearSearch);
  }

  btnRefresh.addEventListener('click', () => {
    triggerRefresh();
  });

  // Delegated click handler for keyword copy buttons and trend links
  trendsGrid.addEventListener('click', (e) => {
    const copyBtn = e.target.closest('.copy-btn');
    if (copyBtn) {
      e.preventDefault();
      e.stopPropagation();
      const keyword = copyBtn.dataset.keyword || '';
      const platform = copyBtn.dataset.platform || '';
      if (keyword) {
        copyKeyword(keyword, platform);
      }
      return;
    }

    const trendLink = e.target.closest('.trend-item');
    if (trendLink) {
      const keyword = trendLink.dataset.keyword || '';
      const platform = trendLink.dataset.platform || '';
      const rankNum = Number(trendLink.dataset.rank);
      trackEvent('select_content', {
        content_type: 'trend_keyword',
        item_id: keyword,
        platform,
        rank: Number.isFinite(rankNum) ? rankNum : undefined,
      });
    }
  });

  const mediaGrid = document.querySelector('.media-grid');
  if (mediaGrid) {
    mediaGrid.addEventListener('click', (e) => {
      const card = e.target.closest('.link-card');
      if (!card) return;
      const titleEl = card.querySelector('h4');
      trackEvent('select_media_hub', {
        media_name: titleEl ? titleEl.textContent.trim() : '',
        link_url: card.href,
      });
    });
  }

  setupTranslation();
}

function clearSearch() {
  searchInput.value = '';
  searchQuery = '';
  updateSearchClearState();
  renderGrid();
  searchInput.focus();
}

function updateSearchClearState() {
  if (!clearSearchBtn) return;
  if (searchInput.value.trim().length > 0) {
    clearSearchBtn.classList.add('visible');
  } else {
    clearSearchBtn.classList.remove('visible');
  }
}

function getActiveGoogTransLang() {
  const match = document.cookie.match(/(?:^|;\s*)googtrans=([^;]+)/);
  if (!match) return 'ko';
  const parts = decodeURIComponent(match[1]).split('/');
  return parts.length >= 3 && parts[2] ? parts[2] : 'ko';
}

function setupTranslation() {
  const langBtn = document.getElementById('langBtn');
  const langDropdown = document.getElementById('langDropdown');
  const currentLangLabel = document.getElementById('currentLangLabel');
  const extTranslateLink = document.getElementById('extTranslateLink');
  const options = document.querySelectorAll('.lang-option');

  if (!langBtn || !langDropdown) return;

  const setExpanded = (expanded) => {
    langBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    langDropdown.classList.toggle('open', expanded);
  };

  langBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    setExpanded(!langDropdown.classList.contains('open'));
  });

  document.addEventListener('click', (e) => {
    if (!langDropdown.contains(e.target) && !langBtn.contains(e.target)) {
      setExpanded(false);
    }
  });

  // Restore active state from cookie if already translated
  const activeLang = getActiveGoogTransLang();
  const activeOption = Array.from(options).find((o) => o.dataset.lang === activeLang);
  if (activeOption) {
    options.forEach((o) => o.classList.remove('active'));
    activeOption.classList.add('active');
    currentLangLabel.textContent = activeOption.dataset.name;
  }

  const updateExternalLink = (targetLang) => {
    const safeTarget = targetLang && targetLang !== 'ko' ? targetLang : 'en';
    const pageUrl = encodeURIComponent(window.location.href);
    extTranslateLink.href = `https://translate.google.com/translate?sl=ko&tl=${encodeURIComponent(safeTarget)}&u=${pageUrl}`;
  };

  updateExternalLink(activeLang);

  options.forEach((opt) => {
    opt.addEventListener('click', () => {
      const targetLang = opt.dataset.lang;
      const langName = opt.dataset.name;

      options.forEach((o) => o.classList.remove('active'));
      opt.classList.add('active');
      currentLangLabel.textContent = langName;
      setExpanded(false);

      updateExternalLink(targetLang);
      trackEvent('change_language', {
        language: targetLang,
        language_name: langName,
      });
      translatePageTo(targetLang);
      showToast(`🌐 ${langName} 번역이 적용되었습니다.`, '🌐');
    });
  });
}

function clearGoogTransCookies() {
  const expire = 'expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
  document.cookie = `googtrans=; ${expire}`;
  const host = window.location.hostname;
  if (host) {
    document.cookie = `googtrans=; ${expire} domain=${host};`;
    document.cookie = `googtrans=; ${expire} domain=.${host};`;
  }
}

function translatePageTo(langCode) {
  if (langCode === 'ko') {
    clearGoogTransCookies();
    window.location.reload();
    return;
  }

  const cookieValue = `/ko/${langCode}`;
  document.cookie = `googtrans=${cookieValue}; path=/;`;
  if (window.location.hostname) {
    document.cookie = `googtrans=${cookieValue}; path=/; domain=.${window.location.hostname};`;
  }

  const googleSelect = document.querySelector('.goog-te-combo');
  if (googleSelect) {
    googleSelect.value = langCode;
    googleSelect.dispatchEvent(new Event('change'));
  } else {
    window.location.reload();
  }
}

function parseUpdatedTimestamp(data) {
  if (!data) return null;
  if (data.updated_at_iso) {
    const t = Date.parse(data.updated_at_iso);
    if (!Number.isNaN(t)) return t;
  }
  if (data.updated_at) {
    // Legacy format without timezone: treat as KST (+09:00)
    const isoCandidate = String(data.updated_at).trim().replace(' ', 'T') + '+09:00';
    const t = Date.parse(isoCandidate);
    if (!Number.isNaN(t)) return t;
  }
  return null;
}

function formatKstDateTime(timestampMs, fallbackText) {
  if (!timestampMs) return fallbackText || '방금 전';
  try {
    const fmt = new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
    return `${fmt.format(new Date(timestampMs))} KST`;
  } catch {
    return `${fallbackText} (KST)`;
  }
}

function formatRelativeAge(elapsedSec) {
  if (elapsedSec < 60) return '방금 전';
  const mins = Math.floor(elapsedSec / 60);
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

function startCountdown() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    if (remainingSeconds > 0) {
      remainingSeconds--;
    } else {
      remainingSeconds = 3600;
      fetchTrends();
    }
    updateTimerDisplay();
  }, 1000);
  updateTimerDisplay();
}

function updateTimerDisplay() {
  const m = Math.floor(remainingSeconds / 60);
  const s = remainingSeconds % 60;
  timerDisplay.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

async function fetchTrends() {
  try {
    let res = null;
    if (IS_LOCAL_SERVER) {
      try {
        res = await fetch(`/api/trends?t=${Date.now()}`, { cache: 'no-store' });
        if (!res.ok) res = null;
      } catch {
        res = null;
      }
    }

    if (!res) {
      res = await fetch(`trends.json?t=${Date.now()}`, { cache: 'no-store' });
    }

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    applyTrendData(data);
    return true;
  } catch (err) {
    console.warn('Trend fetch notice:', err);
    if (trendData && trendData.platforms) {
      return false;
    }
    trendsGrid.innerHTML = `
      <div class="grid-placeholder" style="color: var(--color-up);">
        ⚠️ 데이터를 불러오는데 실패했습니다.<br>
        <span style="font-size:13px;color:var(--text-muted);display:inline-block;margin-top:6px;">
          네트워크 연결을 확인한 뒤 다시 시도해 주세요.
        </span>
      </div>
    `;
    return false;
  }
}

function applyTrendData(data) {
  trendData = data;

  const updatedTime = parseUpdatedTimestamp(data);
  if (updatedTime !== null) {
    const elapsed = Math.max(0, Math.floor((Date.now() - updatedTime) / 1000));
    const rem = 3600 - (elapsed % 3600);
    remainingSeconds = rem > 0 ? rem : 3600;
  } else {
    remainingSeconds = 3600;
  }

  updateTimerDisplay();
  renderUI();
}

async function triggerRefresh() {
  if (isRefreshing) return;
  isRefreshing = true;
  btnRefresh.disabled = true;
  btnRefresh.classList.add('loading');
  btnRefreshText.textContent = '갱신 중...';

  const prevTimestamp = trendData ? trendData.updated_at : null;

  try {
    if (IS_LOCAL_SERVER) {
      await fetch('/api/refresh', { method: 'POST' }).catch(() => {});
    }
    const ok = await fetchTrends();
    if (!ok) {
      trackEvent('refresh_trends', { status: 'error' });
      showToast('⚠️ 서버 연결 상태를 확인해 주세요.', '⚠️');
    } else if (prevTimestamp && trendData && trendData.updated_at === prevTimestamp && !IS_LOCAL_SERVER) {
      trackEvent('refresh_trends', { status: 'up_to_date' });
      showToast('✅ 현재 최신 수집 데이터로 동기화되어 있습니다.', '✅');
    } else {
      trackEvent('refresh_trends', { status: 'updated' });
      showToast('🚀 최신 실시간 검색어가 갱신되었습니다!', '🚀');
    }
  } catch {
    trackEvent('refresh_trends', { status: 'error' });
    showToast('⚠️ 갱신 중 오류가 발생했습니다.', '⚠️');
  } finally {
    setTimeout(() => {
      btnRefresh.classList.remove('loading');
      btnRefresh.disabled = false;
      btnRefreshText.textContent = '지금 갱신';
      isRefreshing = false;
    }, 500);
  }
}

function renderUI() {
  if (!trendData || !trendData.platforms) return;

  const updatedTime = parseUpdatedTimestamp(trendData);
  const kstText = formatKstDateTime(updatedTime, trendData.updated_at);
  if (updatedTime !== null) {
    const elapsed = Math.max(0, Math.floor((Date.now() - updatedTime) / 1000));
    lastUpdatedText.textContent = `마지막 동기화: ${kstText} (${formatRelativeAge(elapsed)})`;
  } else {
    lastUpdatedText.textContent = `마지막 동기화: ${kstText}`;
  }

  const platformKeys = Object.keys(trendData.platforms).filter((k) => k !== 'all');
  totalPlatformsVal.textContent = platformKeys.length;

  let totalKeywords = 0;
  platformKeys.forEach((k) => {
    totalKeywords += (trendData.platforms[k].items || []).length;
  });
  totalKeywordsVal.textContent = `${totalKeywords}개`;

  renderGrid();
}

function renderGrid() {
  if (!trendData || !trendData.platforms) return;

  const platforms = trendData.platforms;
  trendsGrid.innerHTML = '';

  const targets = Object.keys(platforms).filter((k) => k !== 'all');
  let totalRendered = 0;

  targets.forEach((key) => {
    const pInfo = platforms[key];
    if (!pInfo) return;

    let items = pInfo.items || [];
    if (searchQuery) {
      items = items.filter((item) => {
        const kw = (item.keyword || '').toLowerCase();
        const tr = (item.traffic || '').toLowerCase();
        const newsMatch = Array.isArray(item.news)
          ? item.news.some((n) => (n.title || '').toLowerCase().includes(searchQuery))
          : false;
        return kw.includes(searchQuery) || tr.includes(searchQuery) || newsMatch;
      });
    }

    if (items.length === 0 && searchQuery) {
      return;
    }

    totalRendered++;

    const card = document.createElement('section');
    card.className = 'platform-card';

    const listHtml = items
      .map((item) => {
        const stateBadge = getStateBadge(item.change);
        const trafficPill = item.traffic
          ? `<span class="traffic-pill">${escapeHtml(item.traffic)}</span>`
          : '';
        const href = escapeHtml(safeUrl(item.url));
        const kwEscaped = escapeHtml(item.keyword || '');
        const keyEscaped = escapeHtml(key);
        const rankEscaped = escapeHtml(item.rank);

        return `
          <li>
            <a href="${href}" target="_blank" rel="noopener noreferrer" class="trend-item" data-platform="${keyEscaped}" data-keyword="${kwEscaped}" data-rank="${rankEscaped}" title="${kwEscaped}">
              <div class="trend-item-left">
                <span class="rank-badge notranslate">${rankEscaped}</span>
                <span class="trend-keyword">${kwEscaped}</span>
              </div>
              <div class="trend-item-right">
                ${trafficPill}
                ${stateBadge}
                <button type="button" class="copy-btn notranslate" data-platform="${keyEscaped}" data-keyword="${kwEscaped}" title="키워드 복사" aria-label="${kwEscaped} 복사">📋</button>
              </div>
            </a>
          </li>
        `;
      })
      .join('');

    card.innerHTML = `
      <div class="card-header">
        <div class="platform-title">
          <span class="platform-icon notranslate" aria-hidden="true">${escapeHtml(pInfo.icon || '📌')}</span>
          <div>
            <h3>${escapeHtml(pInfo.name)}</h3>
            ${pInfo.description ? `<p class="platform-desc">${escapeHtml(pInfo.description)}</p>` : ''}
          </div>
        </div>
        <span class="platform-tag notranslate">${items.length}개</span>
      </div>
      <ul class="trend-list">
        ${listHtml || '<li style="color:var(--text-dim);font-size:13px;padding:12px;">표시할 키워드가 없습니다.</li>'}
      </ul>
    `;

    trendsGrid.appendChild(card);
  });

  lastRenderedPlatforms = totalRendered;

  if (totalRendered === 0) {
    trendsGrid.innerHTML = `
      <div class="grid-placeholder">
        🔍 "<strong>${escapeHtml(searchQuery)}</strong>" 검색어와 일치하는 실시간 이슈가 없습니다.
      </div>
    `;
  }
}

function getStateBadge(change) {
  if (!change) return '';
  const c = String(change).trim().toLowerCase();

  if (c === '+' || c === 'up') {
    return '<span class="state-badge state-up notranslate">▲ 상승</span>';
  }
  if (c === '-' || c === 'down') {
    return '<span class="state-badge state-down notranslate">▼ 하강</span>';
  }
  if (c === 'new' || c === 'n') {
    return '<span class="state-badge state-new notranslate">NEW</span>';
  }
  if (c === 'hot') {
    return '<span class="state-badge state-hot notranslate">HOT</span>';
  }
  if (c === 'same' || c === 's') {
    return '<span class="state-badge state-same notranslate">-</span>';
  }
  return `<span class="state-badge state-same notranslate">${escapeHtml(c)}</span>`;
}

function copyKeyword(kw, platform = '') {
  const onCopied = () => {
    trackEvent('copy_keyword', { keyword: kw, platform });
    showToast(`"${kw}" 키워드가 복사되었습니다!`, '📋');
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard
      .writeText(kw)
      .then(onCopied)
      .catch(() => fallbackCopyText(kw, platform));
  } else {
    fallbackCopyText(kw, platform);
  }
}

function fallbackCopyText(text, platform = '') {
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    if (ok) {
      trackEvent('copy_keyword', { keyword: text, platform });
    }
    showToast(ok ? `"${text}" 키워드가 복사되었습니다!` : '복사에 실패했습니다.', ok ? '📋' : '⚠️');
  } catch {
    showToast('복사에 실패했습니다.', '⚠️');
  }
}

function showToast(msg, icon = '📋') {
  if (toastIcon) toastIcon.textContent = icon;
  toastMsg.textContent = msg;
  toast.classList.add('show');
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    toast.classList.remove('show');
  }, 2400);
}

function safeUrl(url) {
  if (!url) return '#';
  const trimmed = String(url).trim();
  if (trimmed.startsWith('https://') || trimmed.startsWith('http://')) {
    return trimmed;
  }
  return '#';
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
