// Real-time Trend Pulse Application Logic

let trendData = null;
let currentTab = 'all';
let searchQuery = '';
let remainingSeconds = 3600;
let timerInterval = null;

const timerDisplay = document.getElementById('timerDisplay');
const btnRefresh = document.getElementById('btnRefresh');
const btnRefreshText = document.getElementById('btnRefreshText');
const lastUpdatedText = document.getElementById('lastUpdatedText');
const totalPlatformsVal = document.getElementById('totalPlatformsVal');
const totalKeywordsVal = document.getElementById('totalKeywordsVal');
const tabsContainer = document.getElementById('tabsContainer');
const trendsGrid = document.getElementById('trendsGrid');
const searchInput = document.getElementById('searchInput');
const toast = document.getElementById('toast');
const toastMsg = document.getElementById('toastMsg');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  fetchTrends();
  startCountdown();
  setupEventListeners();
});

function setupEventListeners() {
  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    renderGrid();
  });

  btnRefresh.addEventListener('click', () => {
    triggerRefresh();
  });

  setupTranslation();
}

function setupTranslation() {
  const langBtn = document.getElementById('langBtn');
  const langDropdown = document.getElementById('langDropdown');
  const currentLangLabel = document.getElementById('currentLangLabel');
  const extTranslateLink = document.getElementById('extTranslateLink');
  const options = document.querySelectorAll('.lang-option');

  if (!langBtn || !langDropdown) return;

  // Toggle dropdown
  langBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    langDropdown.classList.toggle('open');
  });

  // Close on outside click
  document.addEventListener('click', (e) => {
    if (!langDropdown.contains(e.target) && e.target !== langBtn) {
      langDropdown.classList.remove('open');
    }
  });

  // Handle language option selection
  options.forEach(opt => {
    opt.addEventListener('click', () => {
      const targetLang = opt.getAttribute('data-lang');
      const langName = opt.getAttribute('data-name');
      
      options.forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
      currentLangLabel.textContent = langName;
      langDropdown.classList.remove('open');

      // Update external redirect link
      const pageUrl = encodeURIComponent(window.location.href);
      extTranslateLink.href = `https://translate.google.com/translate?sl=ko&tl=${targetLang}&u=${pageUrl}`;

      // In-page Google Translate execution
      translatePageTo(targetLang);
      showToast(`🌐 ${langName} 번역이 적용되었습니다.`);
    });
  });

  // Initial external link
  extTranslateLink.href = `https://translate.google.com/translate?sl=ko&tl=en&u=${encodeURIComponent(window.location.href)}`;

  // Auto-detect visitor's browser language
  const userLang = (navigator.language || navigator.userLanguage || 'ko').split('-')[0];
  if (userLang !== 'ko') {
    const matchedOption = Array.from(options).find(o => o.getAttribute('data-lang').startsWith(userLang));
    if (matchedOption) {
      currentLangLabel.textContent = matchedOption.getAttribute('data-name');
      extTranslateLink.href = `https://translate.google.com/translate?sl=ko&tl=${matchedOption.getAttribute('data-lang')}&u=${encodeURIComponent(window.location.href)}`;
    }
  }
}

function translatePageTo(langCode) {
  if (langCode === 'ko') {
    // Reset to Korean
    document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=.' + window.location.hostname;
    window.location.reload();
    return;
  }

  // Set Google Translate cookie
  const cookieValue = `/ko/${langCode}`;
  document.cookie = `googtrans=${cookieValue}; path=/;`;
  document.cookie = `googtrans=${cookieValue}; path=/; domain=.${window.location.hostname}`;

  // If Google select dropdown is available on page, trigger it directly
  const googleSelect = document.querySelector('.goog-te-combo');
  if (googleSelect) {
    googleSelect.value = langCode;
    googleSelect.dispatchEvent(new Event('change'));
  } else {
    // If widget not fully loaded yet, reload to apply cookie or open external
    window.location.reload();
  }
}

function startCountdown() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    if (remainingSeconds > 0) {
      remainingSeconds--;
    } else {
      // 1 hour elapsed, auto-fetch
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
  // 1. Immediately render INITIAL_TRENDS if available (prevents empty flash & supports direct file:// opening)
  if (window.INITIAL_TRENDS && !trendData) {
    applyTrendData(window.INITIAL_TRENDS);
  }

  // 2. If running via HTTP/HTTPS, fetch fresh updates from server/static json
  try {
    let res;
    try {
      res = await fetch(`/api/trends?t=${Date.now()}`);
      if (!res.ok) throw new Error('API not available, fallback to json');
    } catch {
      res = await fetch(`trends.json?t=${Date.now()}`);
    }

    if (!res.ok) throw new Error('Failed to load trends data');
    const data = await res.json();
    applyTrendData(data);
  } catch (err) {
    console.warn('Fetch fallback notice:', err);
    // If we already have INITIAL_TRENDS rendered, no need to show error banner
    if (trendData && trendData.platforms) {
      return;
    }
    trendsGrid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #ef4444; line-height: 1.8;">
        ⚠️ 데이터를 불러오는데 실패했습니다.<br>
        <span style="font-size:13px;color:var(--text-muted);">
          브라우저 보안(CORS)으로 인해 <code>file://</code> 직접 열기 대신 <strong>http://localhost:8080</strong> 으로 접속하시거나 <code>server.py</code>를 실행해 주세요.
        </span>
      </div>
    `;
  }
}

function applyTrendData(data) {
  trendData = data;

  // Calculate remaining seconds if updated_at is present
  if (data.updated_at) {
    const updatedTime = new Date(data.updated_at.replace(/-/g, '/')).getTime();
    const now = Date.now();
    const elapsed = Math.floor((now - updatedTime) / 1000);
    if (!isNaN(elapsed) && elapsed >= 0 && elapsed < 3600) {
      remainingSeconds = 3600 - elapsed;
    } else {
      remainingSeconds = 3600;
    }
  }

  renderUI();
}

async function triggerRefresh() {
  btnRefresh.classList.add('loading');
  btnRefreshText.textContent = '수집 중...';

  try {
    // Call server refresh endpoint if exists
    await fetch('/api/refresh', { method: 'POST' }).catch(() => {});
    await fetchTrends();
    showToast('🚀 최신 실시간 검색어가 갱신되었습니다!');
  } catch (e) {
    showToast('⚠️ 갱신 중 오류가 발생했습니다.');
  } finally {
    setTimeout(() => {
      btnRefresh.classList.remove('loading');
      btnRefreshText.textContent = '지금 갱신';
    }, 600);
  }
}

function renderUI() {
  if (!trendData || !trendData.platforms) return;

  // Header stats
  lastUpdatedText.textContent = `마지막 동기화: ${trendData.updated_at || '방금 전'}`;
  
  const platforms = Object.keys(trendData.platforms);
  totalPlatformsVal.textContent = platforms.filter(k => k !== 'all').length;

  let totalKeywords = 0;
  platforms.forEach(k => {
    if (k !== 'all') {
      totalKeywords += (trendData.platforms[k].items || []).length;
    }
  });
  totalKeywordsVal.textContent = `${totalKeywords}개`;

  renderGrid();
}

function renderTabs() {
  if (tabsContainer) {
    tabsContainer.style.display = 'none';
  }
}

function renderGrid() {
  if (!trendData || !trendData.platforms) return;

  const platforms = trendData.platforms;
  trendsGrid.innerHTML = '';

  // Always display all individual platform cards simultaneously
  const targets = Object.keys(platforms).filter(k => k !== 'all');

  let totalRendered = 0;

  targets.forEach(key => {
    const pInfo = platforms[key];
    if (!pInfo) return;

    // Filter items by search query
    let items = pInfo.items || [];
    if (searchQuery) {
      items = items.filter(i => (i.keyword || '').toLowerCase().includes(searchQuery));
    }

    if (items.length === 0 && searchQuery) {
      return; // Skip empty matches during search
    }

    totalRendered++;

    const card = document.createElement('div');
    card.className = 'platform-card';

    const listHtml = items.map(item => {
      const stateBadge = getStateBadge(item.change);
      const trafficPill = item.traffic ? `<span class="traffic-pill">${escapeHtml(item.traffic)}</span>` : '';
      
      return `
        <li>
          <a href="${item.url || '#'}" target="_blank" rel="noopener noreferrer" class="trend-item" title="클릭 시 포털 검색 결과로 이동">
            <div class="trend-item-left">
              <span class="rank-badge">${item.rank}</span>
              <span class="trend-keyword">${escapeHtml(item.keyword)}</span>
            </div>
            <div class="trend-item-right">
              ${trafficPill}
              ${stateBadge}
              <button class="copy-btn" onclick="copyKeyword(event, '${escapeHtml(item.keyword)}')" title="키워드 복사" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:12px;padding:2px 4px;">
                📋
              </button>
            </div>
          </a>
        </li>
      `;
    }).join('');

    card.innerHTML = `
      <div class="card-header">
        <div class="platform-title">
          <span class="platform-icon">${pInfo.icon || '📌'}</span>
          <div>
            <h3>${pInfo.name}</h3>
            ${pInfo.description ? `<p style="font-size:11px;color:var(--text-dim);">${pInfo.description}</p>` : ''}
          </div>
        </div>
        <span class="platform-tag">${items.length}개</span>
      </div>
      <ul class="trend-list">
        ${listHtml || '<li style="color:var(--text-dim);font-size:13px;padding:12px;">표시할 키워드가 없습니다.</li>'}
      </ul>
    `;

    trendsGrid.appendChild(card);
  });

  if (totalRendered === 0) {
    trendsGrid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; color: var(--text-dim);">
        🔍 "<strong>${escapeHtml(searchQuery)}</strong>" 검색어와 일치하는 실검 결과가 없습니다.
      </div>
    `;
  }
}

function getStateBadge(change) {
  if (!change) return '';
  const c = String(change).toLowerCase();

  if (c === '+' || c === 'up') {
    return `<span class="state-badge state-up">▲ 상승</span>`;
  } else if (c === '-' || c === 'down') {
    return `<span class="state-badge state-down">▼ 하강</span>`;
  } else if (c === 'new' || c === 'n') {
    return `<span class="state-badge state-new">NEW</span>`;
  } else if (c === 'hot') {
    return `<span class="state-badge state-hot">HOT</span>`;
  } else if (c === 'same' || c === 's') {
    return `<span class="state-badge state-same">-</span>`;
  }
  return `<span class="state-badge state-same">${escapeHtml(c)}</span>`;
}

function copyKeyword(e, kw) {
  e.preventDefault();
  e.stopPropagation();
  navigator.clipboard.writeText(kw).then(() => {
    showToast(`"${kw}" 키워드가 복사되었습니다!`);
  }).catch(() => {
    showToast(`복사 실패`);
  });
}

function showToast(msg) {
  toastMsg.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, 2200);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
