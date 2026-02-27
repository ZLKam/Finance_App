/* ============================================
   MarketMind — app.js
   ============================================ */

// ------------------------------------------
// Firebase Config & Init
// ------------------------------------------

const FIREBASE_CONFIG = {
    apiKey: "AIzaSyAHnFy-RQTrJRIu4BFF4LnGA_PP6GWSDsk",
    authDomain: "finance-app-447cc.firebaseapp.com",
    projectId: "finance-app-447cc",
    storageBucket: "finance-app-447cc.firebasestorage.app",
    messagingSenderId: "453168549752",
    appId: "1:453168549752:web:f8df55083f2aeb30c4028d",
    measurementId: "G-ZM5V2VNLZR"
};

let db;
try {
    if (!firebase.apps.length) firebase.initializeApp(FIREBASE_CONFIG);
    db = firebase.firestore();
} catch (err) {
    showErrorState();
}

// ------------------------------------------
// App State
// ------------------------------------------

const store = {
    macroEvents: [],
    newsArticles: [],
    customEvents: [],
    watchlist: [],
    activeTab: 'dashboard',
    newsFilter: 'all',
    heroCountdownTimer: null,
    sentimentChart: null
};

let earningsCountdownTimers = [];

// ------------------------------------------
// Firebase Listeners
// ------------------------------------------

function initDataListeners() {
    if (!db) return;

    const statusEl = document.getElementById('connection-status');
    const timeEl = document.getElementById('last-update-time');

    const onError = (err) => {
        if (err.code === 'not-found') showErrorState();
    };

    db.collection('market_data').doc('macro').onSnapshot(doc => {
        if (!doc.exists) return;
        const data = doc.data();
        store.macroEvents = data.events || [];
        timeEl.innerText = data.last_updated ? data.last_updated.split(' ')[1] : '--:--';
        statusEl.innerHTML = '<span class="text-green-500">●</span> 已同步';
        statusEl.className = 'flex items-center gap-1 text-[10px] text-gray-400';
        refreshAll();
    }, onError);

    db.collection('market_data').doc('news').onSnapshot(doc => {
        if (!doc.exists) return;
        store.newsArticles = doc.data().articles || [];
        refreshAll();
    }, onError);

    db.collection('market_data').doc('custom_calendar').onSnapshot(doc => {
        if (!doc.exists) return;
        store.customEvents = doc.data().events || [];
        refreshAll();
    }, onError);

    db.collection('market_data').doc('watchlist').onSnapshot(doc => {
        if (!doc.exists) return;
        store.watchlist = doc.data().tickers || [];
        refreshAll();
    }, onError);
}

// ------------------------------------------
// Render Orchestration
// ------------------------------------------

function refreshAll() {
    renderHeroCard(false);
    renderEarningsSlider();
    renderDashboardNews();
    renderCalendar();
    renderIntelligence();
    updateSentimentChart();
}

// ------------------------------------------
// Hero Card
// ------------------------------------------

function handleMacroSelection(key) {
    localStorage.setItem('selectedMacroKey', key);
    renderHeroCard(true);
}

function renderHeroCard(fromUserSelect = false) {
    if (!store.macroEvents.length) {
        document.getElementById('hero-event-title').innerText = '暂无数据';
        return;
    }

    const now = Date.now() / 1000;
    const selector = document.getElementById('macro-selector');
    const savedKey = localStorage.getItem('selectedMacroKey');

    selector.innerHTML = store.macroEvents.map(ev =>
        `<option value="${ev.timestamp}|${ev.title}">${ev.date.split(' ')[0].slice(5)} - ${ev.title}</option>`
    ).join('');

    let targetIndex = savedKey
        ? store.macroEvents.findIndex(e => `${e.timestamp}|${e.title}` === savedKey)
        : -1;

    if (targetIndex === -1) {
        const nextIdx = store.macroEvents.findIndex(e => e.timestamp > now);
        if (nextIdx === -1) {
            targetIndex = store.macroEvents.length - 1;
        } else if (nextIdx > 0 && store.macroEvents[nextIdx].timestamp - now > 3 * 86400) {
            targetIndex = nextIdx - 1;
        } else {
            targetIndex = nextIdx;
        }
    }

    const event = store.macroEvents[targetIndex];
    const eventKey = `${event.timestamp}|${event.title}`;

    if (fromUserSelect) {
        selector.value = savedKey;
    } else if (selector.value !== eventKey) {
        selector.value = eventKey;
    }

    document.getElementById('hero-event-title').innerText = event.title;
    document.getElementById('hero-event-prev').innerText = event.previous || '--';
    document.getElementById('hero-event-fore').innerText = event.forecast || '--';
    document.getElementById('hero-event-act').innerText = event.actual || '--';
    document.getElementById('hero-event-ai').innerHTML =
        `<span class="text-blue-400 font-bold">AI解读:</span> ${event.analysis || '暂无详细分析'}`;

    startHeroCountdown(event, event.timestamp <= now);
}

function startHeroCountdown(event, isPast) {
    const countdownEl = document.getElementById('hero-event-countdown');
    const typeEl = document.getElementById('hero-event-type');

    if (store.heroCountdownTimer) clearInterval(store.heroCountdownTimer);

    if (isPast) {
        typeEl.innerText = '已公布核心数据';
        countdownEl.innerText = '已公布';
        countdownEl.className = 'countdown-past';
        return;
    }

    typeEl.innerText = '即将公布核心数据';

    store.heroCountdownTimer = setInterval(() => {
        const remaining = event.timestamp - Date.now() / 1000;

        if (remaining <= 0) {
            countdownEl.innerText = '正在公布!';
            countdownEl.className = 'countdown-live';
            clearInterval(store.heroCountdownTimer);
            return;
        }

        const h = String(Math.floor(remaining / 3600)).padStart(2, '0');
        const m = String(Math.floor((remaining % 3600) / 60)).padStart(2, '0');
        const s = String(Math.floor(remaining % 60)).padStart(2, '0');
        countdownEl.innerText = `T-${h}:${m}:${s}`;
        countdownEl.className = remaining < 1800 ? 'countdown-warning' : 'countdown-default';
    }, 1000);
}

// ------------------------------------------
// Earnings Slider (Dashboard)
// ------------------------------------------

function renderEarningsSlider() {
    const wrapper = document.getElementById('dashboard-custom-events-container');
    const list = document.getElementById('dashboard-custom-events-list');
    const now = Date.now() / 1000;
    const sevenDays = now + 7 * 86400;

    earningsCountdownTimers.forEach(clearInterval);
    earningsCountdownTimers = [];

    const upcoming = store.customEvents
        .filter(ev => ev.timestamp > now && ev.timestamp <= sevenDays)
        .sort((a, b) => a.timestamp - b.timestamp);

    if (!upcoming.length) {
        wrapper.classList.add('hidden');
        return;
    }

    wrapper.classList.remove('hidden');

    list.innerHTML = upcoming.map((ev, i) => `
        <div class="min-w-[200px] max-w-[220px] bg-gradient-to-br from-blue-900/30 to-gray-850 rounded-xl p-3 border border-blue-500/30 flex-shrink-0 relative overflow-hidden shadow-lg">
            <div class="flex justify-between items-start mb-2">
                <span class="bg-blue-600 text-white text-[10px] font-bold px-2 py-0.5 rounded shadow-sm">${ev.ticker}</span>
                <a href="https://stockanalysis.com/stocks/${ev.ticker.toLowerCase()}/financials/" target="_blank" class="text-xs text-blue-400 hover:text-white transition-colors" title="直达财报数据">🔗报表</a>
            </div>
            <div class="text-sm font-bold text-white truncate mb-1">${ev.title}</div>
            <div class="text-[10px] text-gray-400 mb-2">${ev.date.split(' ')[0].slice(5)} 发布</div>
            <div id="earnings-chip-${i}" class="chip-days w-fit">计算中...</div>
        </div>
    `).join('');

    upcoming.forEach((ev, i) => {
        const chip = document.getElementById(`earnings-chip-${i}`);
        if (!chip) return;

        const tick = setInterval(() => {
            const diff = ev.timestamp - Date.now() / 1000;
            if (diff <= 0) {
                chip.innerText = '正在发布!';
                chip.className = 'chip-hours w-fit';
                clearInterval(tick);
                return;
            }
            const days = Math.floor(diff / 86400);
            const h = String(Math.floor((diff % 86400) / 3600)).padStart(2, '0');
            const m = String(Math.floor((diff % 3600) / 60)).padStart(2, '0');
            const s = String(Math.floor(diff % 60)).padStart(2, '0');

            if (days > 0) {
                chip.innerText = `剩余 ${days}天 ${h}小时`;
                chip.className = 'chip-days w-fit';
            } else {
                chip.innerText = `T-${h}:${m}:${s}`;
                chip.className = 'chip-hours w-fit';
            }
        }, 1000);

        earningsCountdownTimers.push(tick);
    });
}

// ------------------------------------------
// News Cards
// ------------------------------------------

function buildNewsCard(article) {
    const isBull = article.impact.includes('多');
    const isBear = article.impact.includes('空');
    const impactClass = isBull
        ? 'text-green-400 bg-green-400/10 border-green-400/30'
        : isBear
            ? 'text-red-400 bg-red-400/10 border-red-400/30'
            : 'text-gray-400 bg-gray-400/10 border-gray-400/30';

    const scoreClass = article.score >= 9
        ? 'bg-red-600 text-white'
        : article.score >= 7
            ? 'bg-yellow-600 text-white'
            : 'bg-gray-700 text-gray-300';

    const linkAttr = article.link
        ? `href="${article.link}" target="_blank" rel="noopener noreferrer"`
        : '';
    const hoverClass = article.link
        ? 'hover:bg-gray-750 cursor-pointer block transition-colors active:bg-gray-700'
        : 'block';

    return `
        <a ${linkAttr} class="bg-gray-800 rounded-xl p-4 border border-gray-700 relative overflow-hidden shadow-sm ${hoverClass}">
            <div class="absolute top-0 right-0 px-2 py-1 text-[10px] font-bold rounded-bl-lg ${scoreClass}">${article.score} / 10</div>
            <h4 class="text-white font-medium text-sm pr-10 leading-snug mb-3">${article.title}</h4>
            <div class="flex gap-2 items-start flex-col sm:flex-row sm:items-center">
                <span class="px-2 py-1 rounded border text-[10px] font-bold ${impactClass}">${article.impact}</span>
                <p class="text-gray-400 text-xs flex-1 line-clamp-2">
                    <span class="text-gray-300 font-bold">简评:</span> ${article.reason}
                </p>
            </div>
        </a>
    `;
}

function renderDashboardNews() {
    const container = document.getElementById('dashboard-news-list');
    if (!store.newsArticles.length) {
        container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">当前无市场情报</div>';
        return;
    }
    const top10 = [...store.newsArticles].sort((a, b) => b.score - a.score).slice(0, 10);
    container.innerHTML = top10.map(buildNewsCard).join('');
}

function renderIntelligence() {
    const container = document.getElementById('intelligence-list');
    let articles = store.newsArticles || [];

    if (store.newsFilter === 'bull') articles = articles.filter(a => a.impact.includes('多'));
    else if (store.newsFilter === 'bear') articles = articles.filter(a => a.impact.includes('空'));

    articles.sort((a, b) => b.score - a.score);

    container.innerHTML = articles.length
        ? articles.map(buildNewsCard).join('')
        : '<div class="text-center text-gray-500 text-sm py-10 border border-dashed border-gray-700 rounded-xl">无符合条件的情报</div>';
}

// ------------------------------------------
// Calendar
// ------------------------------------------

function renderCalendar() {
    const container = document.getElementById('calendar-list');
    const now = Date.now() / 1000;
    const oneMonthOut = now + 30 * 86400;

    const syncedTickers = store.customEvents.map(ev => ev.ticker);
    const pendingTickers = store.watchlist.filter(t => !syncedTickers.includes(t));

    const combined = [...store.macroEvents, ...store.customEvents]
        .filter(ev => ev.timestamp >= now && ev.timestamp <= oneMonthOut)
        .sort((a, b) => a.timestamp - b.timestamp);

    let html = '';

    pendingTickers.forEach(ticker => {
        html += `
            <div class="flex gap-3 bg-gray-800/30 p-3 rounded-xl border border-gray-700 border-dashed items-center">
                <div class="flex flex-col items-center justify-center min-w-[50px] bg-gray-900/50 rounded-lg h-[50px] border border-gray-700">
                    <span class="text-xl animate-spin">⏳</span>
                </div>
                <div class="flex-1 min-w-0 opacity-70">
                    <h4 class="text-sm font-bold text-gray-300">${ticker}
                        <span class="bg-blue-900/30 text-blue-400 border border-blue-800/50 px-1 rounded text-[8px] uppercase ml-1">排队同步中</span>
                    </h4>
                    <div class="text-[10px] text-gray-500 mt-1">等待云端引擎精准抓取发布时间...</div>
                </div>
                <button onclick="deleteSubscription('${ticker}')" class="text-gray-500 hover:text-red-400 p-2 transition-colors text-lg font-bold" title="取消订阅">×</button>
            </div>
        `;
    });

    combined.forEach(ev => {
        const isCustom = ev.type === 'custom';
        const dateParts = ev.date.split(' ');
        const dayLabel = dateParts[0] ? dateParts[0].slice(5) : '--';
        const timeLabel = dateParts[1] || '--';

        const badge = isCustom
            ? '<span class="bg-green-900/40 text-green-400 border border-green-800 px-1 rounded text-[8px] uppercase ml-2">已就绪</span>'
            : '';

        const details = isCustom
            ? '<span class="text-blue-300">系统已自动确认发布时间</span>'
            : `<span>前: ${ev.previous || '--'}</span><span class="text-blue-400">预: ${ev.forecast || '--'}</span>`;

        const titleContent = isCustom && ev.ticker
            ? `<a href="https://stockanalysis.com/stocks/${ev.ticker.toLowerCase()}/financials/" target="_blank" rel="noopener noreferrer" class="hover:text-blue-400 transition-colors underline decoration-blue-500/50 underline-offset-4">${ev.title}</a>`
            : ev.title;

        const deleteBtn = isCustom
            ? `<button onclick="deleteSubscription('${ev.ticker}')" class="text-gray-500 hover:text-red-400 p-2 transition-colors ml-2 text-lg font-bold" title="取消订阅">×</button>`
            : '';

        html += `
            <div class="flex gap-3 bg-gray-800/50 p-3 rounded-xl border border-gray-700 items-center">
                <div class="flex flex-col items-center justify-center min-w-[50px] bg-gray-900 rounded-lg h-[50px] border border-gray-700 shadow-inner">
                    <span class="text-[10px] text-gray-500">${dayLabel}</span>
                    <span class="text-xs font-bold text-gray-300">${timeLabel}</span>
                </div>
                <div class="flex-1 min-w-0">
                    <h4 class="text-sm font-bold text-gray-200 truncate">${titleContent}${badge}</h4>
                    <div class="flex gap-3 mt-1 text-[10px] text-gray-400">${details}</div>
                </div>
                ${deleteBtn}
            </div>
        `;
    });

    if (!html) {
        html = '<div class="text-center text-gray-500 text-sm py-10">未来 1 个月内无重要日程</div>';
    }

    container.innerHTML = html;
}

// ------------------------------------------
// Sentiment Chart
// ------------------------------------------

function updateSentimentChart() {
    const ctx = document.getElementById('sentimentChart').getContext('2d');
    let bull = 0.1, bear = 0.1;

    if (store.newsArticles.length) {
        bull = 0; bear = 0;
        store.newsArticles.forEach(a => {
            if (a.impact.includes('多')) bull += a.score;
            if (a.impact.includes('空')) bear += a.score;
        });
    }

    if (store.sentimentChart) {
        store.sentimentChart.data.datasets[0].data = [bull, bear];
        store.sentimentChart.update();
        return;
    }

    Chart.defaults.color = '#9CA3AF';
    Chart.defaults.font.family = "'Inter', sans-serif";

    store.sentimentChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['看多力量 (Bull)', '看空力量 (Bear)'],
            datasets: [{
                data: [bull, bear],
                backgroundColor: ['rgba(16, 185, 129, 0.8)', 'rgba(239, 68, 68, 0.8)'],
                borderColor: ['#10B981', '#EF4444'],
                borderWidth: 1,
                borderRadius: 4,
                barThickness: 20
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleColor: '#fff',
                    bodyColor: '#e5e7eb',
                    borderColor: '#374151',
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        label: ctx => ` 强度: ${ctx.parsed.x.toFixed(1)} 分`
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(55, 65, 81, 0.3)', borderDash: [5, 5] },
                    beginAtZero: true,
                    title: { display: true, text: '累计评分 (Score)', font: { size: 10 } }
                },
                y: {
                    grid: { display: false, drawBorder: false },
                    ticks: { font: { size: 12, weight: 'bold' }, color: '#D1D5DB' }
                }
            }
        }
    });
}

// ------------------------------------------
// Navigation
// ------------------------------------------

function switchTab(tabId) {
    store.activeTab = tabId;

    ['dashboard', 'calendar', 'news', 'error'].forEach(id => {
        document.getElementById(`view-${id}`).classList.add('hidden');
    });
    document.getElementById(`view-${tabId}`).classList.remove('hidden');

    ['dashboard', 'calendar', 'news'].forEach(id => {
        const btn = document.getElementById(`tab-${id}`);
        const label = btn.querySelector('.tab-label');
        if (id === tabId) {
            btn.classList.add('active');
            label.classList.replace('font-medium', 'font-bold');
        } else {
            btn.classList.remove('active');
            label.classList.replace('font-bold', 'font-medium');
        }
    });

    document.getElementById('main-scroll-area').scrollTop = 0;
}

function filterNews(type) {
    store.newsFilter = type;
    ['all', 'bull', 'bear'].forEach(id => {
        const btn = document.getElementById(`filter-${id}`);
        btn.classList.toggle('active', id === type);
    });
    renderIntelligence();
}

// ------------------------------------------
// Subscription Modal
// ------------------------------------------

function openModal() {
    document.getElementById('event-modal').classList.remove('hidden');
    document.getElementById('ev-ticker').focus();
}

function closeModal() {
    document.getElementById('event-modal').classList.add('hidden');
    document.getElementById('ev-ticker').value = '';
    document.getElementById('ticker-suggestions').classList.add('hidden');
    const saveBtn = document.getElementById('btn-save-event');
    saveBtn.classList.add('opacity-50', 'cursor-not-allowed');
    saveBtn.disabled = true;
}

function selectTicker(symbol) {
    document.getElementById('ev-ticker').value = symbol;
    document.getElementById('ticker-suggestions').classList.add('hidden');
    const saveBtn = document.getElementById('btn-save-event');
    saveBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    saveBtn.disabled = false;
}

// ------------------------------------------
// Ticker Search (with debounce)
// ------------------------------------------

let searchDebounce;

function handleTickerSearch(val) {
    const query = val.toUpperCase().trim();
    const suggestions = document.getElementById('ticker-suggestions');
    const saveBtn = document.getElementById('btn-save-event');

    // Allow manual entry to unlock button
    if (query.length > 0) {
        saveBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        saveBtn.disabled = false;
    } else {
        saveBtn.classList.add('opacity-50', 'cursor-not-allowed');
        saveBtn.disabled = true;
    }

    if (!query) {
        suggestions.classList.add('hidden');
        return;
    }

    suggestions.innerHTML = '<div class="p-3 text-xs text-blue-400 animate-pulse">验证代码中...</div>';
    suggestions.classList.remove('hidden');

    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(async () => {
        try {
            const url = `https://corsproxy.io/?https://query2.finance.yahoo.com/v1/finance/search?q=${query}&quotesCount=5`;
            const res = await fetch(url);
            const data = await res.json();
            const results = (data.quotes || []).filter(q =>
                q.isYahooFinance && (q.quoteType === 'EQUITY' || q.quoteType === 'ETF')
            );

            if (results.length) {
                suggestions.innerHTML = results.map(item => {
                    const name = item.shortname
                        ? item.shortname.replace(/'/g, "\\'")
                        : item.symbol;
                    return `
                        <div onclick="selectTicker('${item.symbol}')" class="p-3 hover:bg-gray-600 cursor-pointer text-sm border-b border-gray-600 last:border-0 transition-colors">
                            <span class="font-bold text-white">${item.symbol}</span>
                            <span class="text-gray-400 text-xs ml-1">${name}</span>
                        </div>
                    `;
                }).join('');
            } else {
                suggestions.innerHTML = '<div class="p-3 text-xs text-gray-400">未找到有效美股代码</div>';
            }
        } catch {
            suggestions.innerHTML = '<div class="p-3 text-xs text-red-400">网络受限，可直接输入代码提交</div>';
        }
    }, 500);
}

// ------------------------------------------
// Firestore Write Operations
// ------------------------------------------

async function saveCustomEvent() {
    if (!db) return alert('数据库未连接');
    const ticker = document.getElementById('ev-ticker').value.toUpperCase().trim();
    if (!ticker) return alert('请输入有效代码');

    try {
        await db.collection('market_data').doc('watchlist').set(
            { tickers: firebase.firestore.FieldValue.arrayUnion(ticker) },
            { merge: true }
        );
        closeModal();
    } catch (err) {
        alert('提交失败: ' + err.message);
    }
}

async function deleteSubscription(ticker) {
    if (!confirm(`确定要取消订阅 ${ticker} 吗？`)) return;
    if (!db) return alert('数据库未连接');

    try {
        await db.collection('market_data').doc('watchlist').set(
            { tickers: firebase.firestore.FieldValue.arrayRemove(ticker) },
            { merge: true }
        );

        const calendarRef = db.collection('market_data').doc('custom_calendar');
        const snapshot = await calendarRef.get();
        if (snapshot.exists) {
            const filtered = (snapshot.data().events || []).filter(e => e.ticker !== ticker);
            await calendarRef.set({ events: filtered }, { merge: true });
        }
    } catch (err) {
        alert('取消失败: ' + err.message);
    }
}

// ------------------------------------------
// Error State
// ------------------------------------------

function showErrorState() {
    ['dashboard', 'calendar', 'news'].forEach(id => {
        document.getElementById(`view-${id}`).classList.add('hidden');
    });
    document.getElementById('view-error').classList.remove('hidden');

    const statusEl = document.getElementById('connection-status');
    if (statusEl) {
        statusEl.innerHTML = '<span class="text-red-500">●</span> 连接失败';
    }
}

// ------------------------------------------
// Wire up macro selector and init
// ------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('macro-selector').addEventListener('change', function () {
        handleMacroSelection(this.value);
    });

    initDataListeners();
    updateSentimentChart();
});
