// ─── State ──────────────────────────────────────────────
let state = {
    fair: null,
    shiftOpen: false,
    shiftOwner: null,
    shiftOwnerName: null,
    catalog: [],
    cart: [],
    currentTab: 'all',
};

let pendingCheckouts = [];

function loadPendingCheckouts() {
    try {
        const raw = localStorage.getItem('pendingCheckouts');
        pendingCheckouts = raw ? JSON.parse(raw) : [];
        renderPendingBadge();
    } catch (e) {}
}

function savePendingCheckouts() {
    try {
        localStorage.setItem('pendingCheckouts', JSON.stringify(pendingCheckouts));
        renderPendingBadge();
    } catch (e) {}
}

function renderPendingBadge() {
    const el = document.getElementById('pendingBadge');
    if (!el) return;
    if (pendingCheckouts.length === 0) {
        el.style.display = 'none';
        return;
    }
    el.style.display = 'inline-flex';
    el.innerHTML = `⏳ ${pendingCheckouts.length}`;
    el.title = pendingCheckouts.map((p, i) =>
        `${i + 1}. ${p.payment_type} — ${p.cart.reduce((s, c) => s + c.price * c.qty, 0)} лей`
    ).join('\n');
}

const ID_ANYA = 4013760;
const ID_NINA = 141076129;

const USER_ID = parseInt(document.querySelector('meta[name="user-id"]').getAttribute('content'));
const USER_NAME = document.querySelector('meta[name="user-name"]').getAttribute('content');

// ─── Init ───────────────────────────────────────────────
async function init() {
    loadPendingCheckouts();
    await loadFair();
    await loadProducts();
}

// ─── API helpers ───────────────────────────────────────
async function api(path, options = {}) {
    const resp = await fetch(path, {
        credentials: 'same-origin',
        ...options,
        headers: { ...options.headers },
    });
    if (resp.status === 401) {
        window.location.href = '/login';
        return null;
    }
    if (!resp.ok) {
        let err = 'Ошибка запроса';
        try {
            const data = await resp.json();
            err = data.detail || JSON.stringify(data);
        } catch (e) {}
        throw new Error(err);
    }
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) return resp.json();
    return resp;
}

// ─── Fair ──────────────────────────────────────────────
async function loadFair() {
    try {
        const data = await api('/api/fair');
        state.fair = data.fair;
        state.shiftOpen = data.shift_open;
        state.shiftOwner = data.shift_owner;
        state.shiftOwnerName = data.shift_owner_name;
        updateUI();
    } catch (e) {
        console.error(e);
    }
}

async function selectFair(name) {
    try {
        // Check if this fair already has an open shift
        const status = await api(`/api/fair/status?fair_name=${name}`);
        
        if (status.shift_open) {
            // Show choice modal
            showFairChoiceModal(name, status);
            return;
        }
        
        // Proceed as normal - assign to this fair
        const form = new FormData();
        form.append('fair_name', name);
        await api('/api/fair', { method: 'POST', body: form });
        state.fair = name;
        state.shiftOpen = false;
        state.shiftOwner = null;
        state.shiftOwnerName = null;
        updateUI();
    } catch (e) {
        alert(e.message);
    }
}

function showFairChoiceModal(fairName, status) {
    const modal = document.getElementById('fairChoiceModal');
    const otherFair = fairName === 'Yardsale' ? 'Ecolocal' : 'Yardsale';
    const ownerName = status.shift_owner_name || 'кем-то';
    
    document.getElementById('fairChoiceText').innerHTML =
        `Смена на <b>${fairName}</b> уже открыта (${ownerName}).<br><br>Что хотите сделать?`;
    
    document.getElementById('btnJoinFair').textContent = `✅ Присоединиться к ${fairName}`;
    document.getElementById('btnJoinFair').onclick = () => joinFair(fairName);
    
    document.getElementById('btnOpenOther').textContent = `🔄 Открыть ${otherFair}`;
    document.getElementById('btnOpenOther').onclick = () => openOtherFair(otherFair);
    
    modal.style.display = 'flex';
}

function closeFairChoiceModal() {
    document.getElementById('fairChoiceModal').style.display = 'none';
}

async function joinFair(name) {
    closeFairChoiceModal();
    try {
        const form = new FormData();
        form.append('fair_name', name);
        await api('/api/fair', { method: 'POST', body: form });
        state.fair = name;
        state.shiftOpen = false;
        state.shiftOwner = null;
        state.shiftOwnerName = null;
        updateUI();
        // Reload to get actual shift state
        await loadFair();
    } catch (e) {
        alert(e.message);
    }
}

async function openOtherFair(name) {
    closeFairChoiceModal();
    try {
        // Assign to this fair
        const form = new FormData();
        form.append('fair_name', name);
        await api('/api/fair', { method: 'POST', body: form });
        // Open shift on it
        await api('/api/shift/open', { method: 'POST' });
        state.fair = name;
        state.shiftOpen = true;
        state.shiftOwner = USER_ID;
        state.shiftOwnerName = USER_NAME;
        updateUI();
    } catch (e) {
        alert(e.message);
    }
}

// ─── Shift ─────────────────────────────────────────────
async function openShift() {
    try {
        await api('/api/shift/open', { method: 'POST' });
        state.shiftOpen = true;
        state.shiftOwner = USER_ID;
        state.shiftOwnerName = USER_NAME;
        updateUI();
    } catch (e) {
        alert(e.message);
    }
}

function requestCloseShift() {
    const modal = document.getElementById('confirmModal');
    document.getElementById('modalText').textContent =
        `Вы уверены, что хотите закрыть ярмарку ${state.fair}?`;
    document.getElementById('modalConfirm').onclick = confirmCloseShift;
    modal.style.display = 'flex';
}

async function confirmCloseShift() {
    closeModal();
    try {
        const data = await api('/api/shift/close', { method: 'POST' });
        state.shiftOpen = false;
        state.shiftOwner = null;
        state.shiftOwnerName = null;
        updateUI();
        alert('📊 Итоги смены:\n\n' + data.report);
        setTimeout(() => loadFair(), 0);
    } catch (e) {
        alert(e.message);
    }
}

function closeModal() {
    document.getElementById('confirmModal').style.display = 'none';
}

// ─── Products ──────────────────────────────────────────
async function loadProducts() {
    try {
        const data = await api('/api/products');
        state.catalog = data.products;
        renderProducts();
    } catch (e) {
        console.error(e);
    }
}

function getImageUrl(name, ownerId) {
    const n = name.toLowerCase();
    if (n.includes('классика') && !n.includes('картошка')) return '/static/images/klassika.webp';
    if (n.includes('ас.премиум') || n.includes('ас.лайт') || n.includes('ассорти')) return '/static/images/assorti.webp';
    if (n.includes('брауни')) return '/static/images/brownie.webp';
    if (n.includes('колбаса')) return '/static/images/kolbasa.webp';
    if (n.includes('орешек') || n.includes('орешки')) return '/static/images/oreshek.webp';
    if (n.includes('грибочки')) return '/static/images/gribochki.webp';
    if (n.includes('муравейник')) return '/static/images/muraveynik.webp';
    if ((n.includes('трубочк') || n.includes('трубочка')) && ownerId === ID_NINA) return '/static/images/trubochki_nina.webp';
    if (n.includes('трубочк') || n.includes('трубочка')) return '/static/images/trubochki.webp';
    if (n.includes('ириска')) return '/static/images/iriska.webp';
    if (n.includes('овсянка')) return '/static/images/ovsyanka.webp';
    if (n.includes('картошка')) return '/static/images/kartoshka.webp';
    if (n.includes('рогалик') || n.includes('рогалики')) return '/static/images/rogaliki.webp';
    if (n.includes('птичье молоко мини')) return '/static/images/ptichye_moloko.webp';
    if (n.includes('птичье молоко')) return '/static/images/ptichye_moloko.webp';
    return '/static/images/default.webp';
}

// ─── POS (Products grid + Cart) ────────────────────────
function setProductTab(tab) {
    state.currentTab = tab;
    document.querySelectorAll('[data-prod-tab]').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-prod-tab="${tab}"]`).classList.add('active');
    renderProducts();
}

function renderProducts() {
    const grid = document.getElementById('productsGrid');
    if (!grid) return;
    grid.innerHTML = '';

    let items = state.catalog;
    if (state.currentTab === 'anya') items = items.filter(p => p.owner_id === ID_ANYA);
    else if (state.currentTab === 'nina') items = items.filter(p => p.owner_id === ID_NINA);

    items.sort((a, b) => a.name.localeCompare(b.name, 'ru'));

    if (items.length === 0) {
        grid.innerHTML = '<p style="grid-column:span 2;text-align:center;color:#999;padding:20px;">Товаров нет</p>';
        return;
    }

    items.forEach(p => {
        const card = document.createElement('button');
        card.className = 'product-card';
        card.innerHTML = `
            <img src="${getImageUrl(p.name, p.owner_id)}" alt="${p.name}" loading="lazy">
            <div class="product-info">
                <span class="product-name">${p.name}</span>
                <span class="product-price">${p.price} лей</span>
            </div>
        `;
        card.onclick = () => addToCart(p);
        grid.appendChild(card);
    });
}

function addToCart(product) {
    let item = state.cart.find(i => i.name === product.name && i.price === product.price);
    if (item) item.qty = (item.qty || 1) + 1;
    else state.cart.push({ ...product, qty: 1 });
    updateCart();
}

function changeQty(index, delta) {
    state.cart[index].qty += delta;
    if (state.cart[index].qty <= 0) state.cart.splice(index, 1);
    updateCart();
}

function removeItem(index) {
    state.cart.splice(index, 1);
    updateCart();
}

function clearCart() {
    if (state.cart.length === 0) return;
    state.cart = [];
    updateCart();
}

function updateCart() {
    const container = document.getElementById('cartItems');
    if (!container) return;
    container.innerHTML = '';
    let sum = 0;
    state.cart.forEach((item, idx) => {
        sum += item.price * item.qty;
        container.innerHTML += `
            <div class="cart-item">
                <div class="cart-item-info">
                    <b>${item.name}</b><br>
                    <small>${item.price} л. x ${item.qty} = ${item.price * item.qty} л.</small>
                </div>
                <div class="cart-controls">
                    <button class="ctrl-btn" onclick="changeQty(${idx}, -1)">➖</button>
                    <span style="width:15px;text-align:center;font-weight:bold;">${item.qty}</span>
                    <button class="ctrl-btn" onclick="changeQty(${idx}, 1)">➕</button>
                    <button class="ctrl-btn del-btn" onclick="removeItem(${idx})">🗑</button>
                </div>
            </div>
        `;
    });
    document.getElementById('totalPrice').innerText = sum;
}

async function checkout(paymentType) {
    if (state.cart.length === 0) return;
    const cart = state.cart.map(i => ({ ...i }));
    const successScreen = document.getElementById('successScreen');
    successScreen.classList.add('show');

    setTimeout(async () => {
        try {
            await postSale(cart, paymentType);
            state.cart = [];
            updateCart();
            setTimeout(() => { successScreen.classList.remove('show'); }, 500);
            loadFair();
        } catch (e) {
            successScreen.classList.remove('show');
            const save = confirm(`❌ Не удалось пробить чек: ${e.message}\n\nСохранить чек в очередь и повторить позже?`);
            if (save) {
                pendingCheckouts.push({ cart, payment_type: paymentType, created: new Date().toISOString() });
                savePendingCheckouts();
                state.cart = [];
                updateCart();
                alert('⏳ Чек сохранён в очередь. Когда интернет появится — нажмите на значок ⏳ в шапке.');
            }
        }
    }, 1200);
}

async function postSale(cart, paymentType) {
    return await api('/api/sales', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cart, payment_type: paymentType }),
    });
}

async function retryPendingCheckouts() {
    if (pendingCheckouts.length === 0) return;
    const todo = [...pendingCheckouts];
    let retried = 0;
    for (const p of todo) {
        try {
            await postSale(p.cart, p.payment_type);
            pendingCheckouts = pendingCheckouts.filter(x => x !== p);
            retried++;
        } catch (e) {
            console.error('Retry failed:', e);
        }
    }
    savePendingCheckouts();
    if (retried > 0) {
        alert(`✅ Отправлено ${retried} чек(ов) из очереди.`);
        loadFair();
    } else {
        alert('❌ Не удалось отправить ни одного чека. Проверьте подключение.');
    }
}

// ─── Stats ─────────────────────────────────────────────
let currentStatsTab = 'me';

let currentCheckId = null;

function setStatsTab(tab) {
    currentStatsTab = tab;
    document.querySelectorAll('[data-stats-tab]').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-stats-tab="${tab}"]`).classList.add('active');
    document.getElementById('checkDetail').style.display = 'none';
    if (tab === 'checks') {
        loadChecks();
    } else {
        document.getElementById('checksList').style.display = 'none';
        document.getElementById('statsContent').style.display = 'block';
        loadStats();
    }
}

async function loadStats() {
    const container = document.getElementById('statsContent');
    container.innerHTML = '<p class="hint">Загрузка...</p>';
    try {
        const ep = currentStatsTab === 'me' ? '/api/stats/me' : '/api/stats/all';
        const data = await api(ep);
        if (data.stats) {
            container.innerHTML = data.stats;
        } else {
            container.innerHTML = `<p class="hint">${data.message || 'Нет данных.'}</p>`;
        }
    } catch (e) {
        if (e.message.includes('Смена закрыта')) {
            container.innerHTML = '<p class="hint">⚠️ Смена закрыта. Статистика доступна только во время открытой смены.</p>';
        } else {
            container.innerHTML = `<p class="hint">❌ ${e.message}</p>`;
        }
    }
}

async function loadChecks() {
    const listEl = document.getElementById('checksList');
    const detailEl = document.getElementById('checkDetail');
    detailEl.style.display = 'none';
    listEl.style.display = 'block';
    document.getElementById('statsContent').style.display = 'none';
    listEl.innerHTML = '<p class="hint">Загрузка...</p>';
    try {
        const data = await api('/api/stats/checks');
        if (!data.checks || data.checks.length === 0) {
            listEl.innerHTML = '<p class="hint">Чеков пока нет.</p>';
            return;
        }
        listEl.innerHTML = data.checks.map((c, i) => {
            const num = data.checks.length - i;
            const date = new Date(c.date.replace(' ', 'T')).toLocaleString('ru-RU', {
                day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit'
            });
            const icon = c.payment_type === 'Карта' ? '💳' : '💵';
            return `
                <div class="check-card" onclick="showCheckDetail('${c.check_id}')">
                    <div class="check-card-header">
                        <span class="check-num">🧾 Чек #${num}</span>
                        <span class="check-date">${date}</span>
                    </div>
                    <div class="check-card-body">
                        <span>${icon} ${c.cashier_name}</span>
                        <span class="check-total">${c.total} лей</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        if (e.message.includes('Смена закрыта')) {
            listEl.innerHTML = '<p class="hint">⚠️ Смена закрыта. Чеки доступны только во время открытой смены.</p>';
        } else {
            listEl.innerHTML = `<p class="hint">❌ ${e.message}</p>`;
        }
    }
}

async function showCheckDetail(checkId) {
    const listEl = document.getElementById('checksList');
    const detailEl = document.getElementById('checkDetail');
    if (currentCheckId === checkId && detailEl.style.display === 'block') {
        detailEl.style.display = 'none';
        listEl.style.display = 'block';
        currentCheckId = null;
        return;
    }
    currentCheckId = checkId;
    detailEl.innerHTML = '<p class="hint">Загрузка...</p>';
    detailEl.style.display = 'block';
    listEl.style.display = 'none';
    try {
        const check = await api(`/api/stats/check/${checkId}`);
        const date = new Date(check.date.replace(' ', 'T')).toLocaleString('ru-RU', {
            day: 'numeric', month: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
        const icon = check.payment_type === 'Карта' ? '💳' : '💵';
        let itemsHtml = '';
        check.items.forEach((item, idx) => {
            itemsHtml += `
                <div class="check-item">
                    <span class="check-item-name">${idx + 1}. ${item.name}</span>
                    <span class="check-item-price">${item.price} лей</span>
                    <span class="check-item-owner">${item.owner_name}</span>
                </div>
            `;
        });
        detailEl.innerHTML = `
            <div class="check-detail-card">
                <div class="check-detail-header">
                    <button class="btn-back" onclick="backToChecks()">← Назад</button>
                    <span class="check-detail-title">🧾 Чек</span>
                </div>
                <div class="check-detail-meta">
                    <div>${date}</div>
                    <div>${icon} ${check.cashier_name}</div>
                    <div>${icon} ${check.payment_type}</div>
                </div>
                <div class="check-detail-items">
                    ${itemsHtml}
                </div>
                <div class="check-detail-total">
                    <span>Итого:</span>
                    <span><b>${check.total} лей</b></span>
                </div>
            </div>
        `;
    } catch (e) {
        detailEl.innerHTML = `<p class="hint">❌ ${e.message}</p>`;
    }
}

function backToChecks() {
    document.getElementById('checkDetail').style.display = 'none';
    document.getElementById('checksList').style.display = 'block';
    currentCheckId = null;
}

// ─── Files ─────────────────────────────────────────────
async function uploadFile(input) {
    const file = input.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
        await api('/api/files/upload', { method: 'POST', body: form });
        input.value = '';
        loadFiles();
    } catch (e) {
        alert('Ошибка загрузки: ' + e.message);
    }
}

async function loadFiles() {
    const container = document.getElementById('fileList');
    try {
        const data = await api('/api/files');
        if (!data.files || data.files.length === 0) {
            container.innerHTML = '<p class="hint">Файлов пока нет.</p>';
            return;
        }
        container.innerHTML = data.files.map(f => {
            const date = new Date(f.timestamp).toLocaleString('ru-RU', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' });
            const sizeStr = f.size > 1024 * 1024
                ? (f.size / 1024 / 1024).toFixed(1) + ' MB'
                : f.size > 1024
                    ? (f.size / 1024).toFixed(0) + ' KB'
                    : f.size + ' B';
            const icon = f.original_name.match(/\.(jpg|jpeg|png|gif|webp)$/i) ? '🖼' : '📄';
            return `
                <div class="file-item">
                    <div class="file-item-info">
                        <div class="file-item-name">${icon} ${f.original_name}</div>
                        <div class="file-item-meta">${f.uploader_name} · ${date} · ${sizeStr}</div>
                    </div>
                    <a href="/api/files/${f.id}" download class="file-download">Скачать</a>
                </div>
            `;
        }).join('');
    } catch (e) {
        container.innerHTML = `<p class="hint">❌ ${e.message}</p>`;
    }
}

// ─── UI Update ──────────────────────────────────────────
function updateUI() {
    const fairSel = document.getElementById('fairSelection');
    const main = document.getElementById('mainInterface');

    if (!state.fair) {
        fairSel.style.display = 'block';
        main.style.display = 'none';
        return;
    }

    fairSel.style.display = 'none';
    main.style.display = 'block';

    const icon = state.fair === 'Yardsale' ? '🎪' : '🌿';
    document.getElementById('fairIcon').textContent = icon;
    document.getElementById('fairName').textContent = state.fair;

    const badge = document.getElementById('shiftBadge');
    const actions = document.getElementById('shiftActions');

    if (state.shiftOpen) {
        badge.innerHTML = '<span class="dot open"></span> Смена открыта';
        const isOwner = state.shiftOwner === USER_ID;
        actions.innerHTML = isOwner
            ? '<button class="btn-shift close" onclick="requestCloseShift()">❌ Закрыть день</button>'
            : `<span style="font-size:12px;color:#666;">Открыл(а): ${state.shiftOwnerName}</span>`;
    } else {
        badge.innerHTML = '<span class="dot closed"></span> Смена закрыта';
        actions.innerHTML = '<button class="btn-shift open" onclick="openShift()">▶️ Начать смену</button>';
    }
}

// ─── Tab switching ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    init();

    // Tab switching (main tabs)
    document.querySelectorAll('.tabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tabs .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
            document.getElementById('tab-' + btn.dataset.tab).classList.add('active');

            if (btn.dataset.tab === 'stats') {
                currentStatsTab = 'me';
                document.querySelectorAll('[data-stats-tab]').forEach(b => b.classList.remove('active'));
                document.querySelector('[data-stats-tab="me"]').classList.add('active');
                document.getElementById('checksList').style.display = 'none';
                document.getElementById('checkDetail').style.display = 'none';
                document.getElementById('statsContent').style.display = 'block';
                loadStats();
            }
            if (btn.dataset.tab === 'files') loadFiles();
        });
    });

    // Product tab switching
    document.querySelectorAll('[data-prod-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            setProductTab(btn.dataset.prodTab);
        });
    });

    // Stats tab switching (event delegation)
    document.querySelector('#tab-stats .tab-bar').addEventListener('click', (e) => {
        const btn = e.target.closest('[data-stats-tab]');
        if (btn) setStatsTab(btn.dataset.statsTab);
    });
});

// ─── Logout ────────────────────────────────────────────
async function logout() {
    window.location.href = '/api/auth/logout';
}
