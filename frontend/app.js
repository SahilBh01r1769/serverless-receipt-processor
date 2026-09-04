// ── CONFIG — deployed public identifiers/endpoints ─────────────────────────
const COGNITO_DOMAIN  = 'https://ap-south-1apyebta6q.auth.ap-south-1.amazoncognito.com';
const CLIENT_ID       = 'a6a6akosqf5f64lp2eo964d8d';
const REDIRECT_URI    = 'https://d3uo3z77ak8ix1.cloudfront.net';
const API_BASE        = 'https://syx3k5tsz7.execute-api.ap-south-1.amazonaws.com/prod';
// ──────────────────────────────────────────────────────────────────────────

function b64url(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');
}

async function pkce() {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: b64url(digest) };
}

const Token = {
  set(id, access, expiry) {
    localStorage.setItem('rp_id_token', id);
    localStorage.setItem('rp_access_token', access);
    localStorage.setItem('rp_expiry', expiry);
  },
  id() { return localStorage.getItem('rp_id_token'); },
  expiry() { return Number(localStorage.getItem('rp_expiry') || 0); },
  valid() { return !!this.id() && Date.now() < this.expiry() - 30000; },
  clear() { ['rp_id_token','rp_access_token','rp_expiry'].forEach(k => localStorage.removeItem(k)); }
};

async function startLogin() {
  const { verifier, challenge } = await pkce();
  localStorage.setItem('pkce_verifier', verifier);
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: 'openid email profile',
    code_challenge: challenge,
    code_challenge_method: 'S256'
  });
  window.location.href = `${COGNITO_DOMAIN}/oauth2/authorize?${params}`;
}

async function exchangeCode(code) {
  const verifier = localStorage.getItem('pkce_verifier');
  localStorage.removeItem('pkce_verifier');
  const res = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      code,
      code_verifier: verifier
    })
  });
  if (!res.ok) throw new Error('Token exchange failed');
  const data = await res.json();
  const expiry = Date.now() + data.expires_in * 1000;
  Token.set(data.id_token, data.access_token, expiry);
  return data.id_token;
}

function parseJwt(token) {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));
  } catch {
    return {};
  }
}

function signOut() {
  Token.clear();
  const params = new URLSearchParams({ client_id: CLIENT_ID, logout_uri: REDIRECT_URI });
  window.location.href = `${COGNITO_DOMAIN}/logout?${params}`;
}

async function boot() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');

  if (code) {
    try {
      const idToken = await exchangeCode(code);
      window.history.replaceState({}, '', window.location.pathname);
      showApp(idToken);
    } catch (e) {
      console.error(e);
      startLogin();
    }
    return;
  }

  if (Token.valid()) {
    showApp(Token.id());
    return;
  }

  startLogin();
}

function showApp(idToken) {
  const claims = parseJwt(idToken);
  document.getElementById('user-email').textContent = claims.email || claims['cognito:username'] || 'User';
  document.getElementById('auth-loading').style.display = 'none';
  document.getElementById('app').style.display = 'block';
  loadExpenses();
}

async function authFetch(url, options = {}) {
  const token = Token.id();
  if (!token) {
    startLogin();
    return;
  }
  return fetch(url, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` }
  });
}

function showToast(msg, type = 'ok') {
  const stack = document.getElementById('toast-stack');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  const icon = type === 'ok' ? 'ti-circle-check' : 'ti-alert-circle';
  t.innerHTML = `<i class="ti ${icon}" aria-hidden="true"></i><span>${msg}</span>
    <button class="toast-close" aria-label="Dismiss"><i class="ti ti-x"></i></button>`;
  t.querySelector('.toast-close').onclick = () => removeToast(t);
  stack.appendChild(t);
  const timer = setTimeout(() => removeToast(t), 4000);
  t._timer = timer;
}

function removeToast(t) {
  if (!t.parentNode) return;
  clearTimeout(t._timer);
  t.classList.add('leaving');
  setTimeout(() => t.remove(), 180);
}

let selectedFile = null;

function fmtSize(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(1) + ' MB';
}

function setStatus(msg, type) {
  const el = document.getElementById('sb');
  el.className = 'status on ' + type;
  el.innerHTML = (type === 'busy' ? '<div class="spinner"></div>' : '') + '<span>' + msg + '</span>';
}

function clearStatus() {
  document.getElementById('sb').className = 'status';
}

function setProgress(pct, lbl) {
  const w = document.getElementById('pw');
  if (pct === null) {
    w.className = 'prog-wrap';
    return;
  }
  w.className = 'prog-wrap on';
  document.getElementById('pb').style.width = pct + '%';
  document.getElementById('pl').textContent = lbl || '';
}

function selectFile(f) {
  if (!f) return;
  if (f.size > 10 * 1024 * 1024) {
    showToast('File exceeds 10 MB', 'err');
    return;
  }
  selectedFile = f;
  const fp = document.getElementById('fp');
  fp.style.display = 'flex';
  document.getElementById('pn').textContent = f.name;
  document.getElementById('ps').textContent = fmtSize(f.size);
  const r = new FileReader();
  r.onload = e => document.getElementById('pt').src = e.target.result;
  r.readAsDataURL(f);
  document.getElementById('ub').disabled = false;
  clearStatus();
}

function clearFile() {
  selectedFile = null;
  document.getElementById('fp').style.display = 'none';
  document.getElementById('pt').src = '';
  document.getElementById('fi').value = '';
  document.getElementById('ub').disabled = true;
  setProgress(null);
  clearStatus();
}

document.getElementById('fi').addEventListener('change', e => selectFile(e.target.files[0]));
const dz = document.getElementById('dz');
dz.addEventListener('dragover', e => {
  e.preventDefault();
  dz.classList.add('over');
});
dz.addEventListener('dragleave', () => dz.classList.remove('over'));
dz.addEventListener('drop', e => {
  e.preventDefault();
  dz.classList.remove('over');
  selectFile(e.dataTransfer.files[0]);
});
dz.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') document.getElementById('fi').click();
});

async function uploadReceipt() {
  if (!selectedFile) return;
  const btn = document.getElementById('ub');
  btn.disabled = true;
  clearStatus();
  setProgress(10, 'Getting upload URL…');

  try {
    const pr = await authFetch(`${API_BASE}/upload-url`, { method: 'POST' });
    if (!pr.ok) throw new Error('Could not get upload URL');
    const pd = await pr.json();

    setProgress(35, 'Uploading to S3…');
    const ur = await fetch(pd.presignedUrl, {
      method: 'PUT',
      body: selectedFile,
      headers: { 'Content-Type': selectedFile.type || 'image/jpeg' }
    });
    if (!ur.ok) throw new Error('S3 upload failed (' + ur.status + ')');

    setProgress(70, 'Processing with Textract…');
    setStatus('Analysing receipt…', 'busy');
    setTimeout(() => {
      setProgress(100, 'Done');
      setTimeout(() => {
        setProgress(null);
        clearStatus();
        showToast('Receipt processed', 'ok');
        clearFile();
        loadExpenses();
      }, 500);
    }, 3500);
  } catch (err) {
    setProgress(null);
    clearStatus();
    showToast(err.message, 'err');
    btn.disabled = false;
  }
}

const CAT = {
  'Food & Dining': { cls: 'ic-food', icon: 'ti-tools-kitchen-2' },
  Groceries: { cls: 'ic-grocery', icon: 'ti-basket' },
  'Online Shopping': { cls: 'ic-shop', icon: 'ti-shopping-bag' },
  'Fuel & Transport': { cls: 'ic-fuel', icon: 'ti-gas-station' },
  'Health & Pharmacy': { cls: 'ic-health', icon: 'ti-heart-rate-monitor' },
  Utilities: { cls: 'ic-utility', icon: 'ti-bolt' },
  Fashion: { cls: 'ic-fashion', icon: 'ti-shirt' }
};

function catInfo(c) {
  return CAT[c] || { cls: 'ic-misc', icon: 'ti-tag' };
}

let currentExpenses = [];

function renderSkeleton(count = 4) {
  const el = document.getElementById('el');
  let html = '';
  for (let i = 0; i < count; i++) {
    html += `
      <div class="skel-item">
        <div class="skel skel-icon"></div>
        <div class="skel-main">
          <div class="skel skel-line w60"></div>
          <div class="skel skel-line w35"></div>
        </div>
        <div class="skel skel-amt"></div>
      </div>`;
  }
  el.innerHTML = html;
}

function parseExpenseDate(exp) {
  const raw = exp.expense_date || exp.upload_date;
  if (!raw) return null;

  let d = new Date(raw);
  if (!isNaN(d)) return d;

  const parts = raw.split(/[\/\-]/);
  if (parts.length === 3) {
    let [a, b, c] = parts.map(p => parseInt(p, 10));
    if (c < 100) c += 2000;
    d = new Date(c, a - 1, b);
    if (!isNaN(d)) return d;
  }

  return null;
}

async function loadExpenses() {
  const el = document.getElementById('el');
  renderSkeleton();

  try {
    const res = await authFetch(`${API_BASE}/expenses`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const exps = data.expenses || [];
    currentExpenses = exps;

    if (!exps.length) {
      el.innerHTML = '<div class="empty"><i class="ti ti-receipt-off"></i><p>No expenses yet</p></div>';
      document.getElementById('sr').style.display = 'none';
      return;
    }

    const total = exps.reduce((s, e) => s + Number(e.amount || 0), 0);
    const now = new Date();
    const monthTotal = exps.reduce((s, e) => {
      const d = parseExpenseDate(e);
      if (d && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) {
        return s + Number(e.amount || 0);
      }
      return s;
    }, 0);

    document.getElementById('sv').textContent = '₹' + Math.round(total).toLocaleString('en-IN');
    document.getElementById('sm').textContent = '₹' + Math.round(monthTotal).toLocaleString('en-IN');
    document.getElementById('sc').textContent = exps.length;
    document.getElementById('sr').style.display = 'grid';
    renderExpenseList();
  } catch (e) {
    el.innerHTML = '<div class="empty"><i class="ti ti-alert-circle" style="color:var(--danger)"></i><p style="color:var(--danger)">Could not load expenses</p></div>';
    showToast('Could not load expenses', 'err');
  }
}

function renderExpenseList() {
  const el = document.getElementById('el');
  if (!currentExpenses.length) {
    el.innerHTML = '<div class="empty"><i class="ti ti-receipt-off"></i><p>No expenses yet</p></div>';
    return;
  }

  const sortMode = document.getElementById('sort-select').value;
  const indexed = currentExpenses.map((exp, idx) => ({ exp, idx }));
  indexed.sort((a, b) => {
    const da = parseExpenseDate(a.exp);
    const db = parseExpenseDate(b.exp);
    const ta = da ? da.getTime() : 0;
    const tb = db ? db.getTime() : 0;
    return sortMode === 'date-asc' ? ta - tb : tb - ta;
  });

  el.innerHTML = '';
  indexed.forEach(({ exp, idx }) => {
    const cat = exp.category || 'Miscellaneous';
    const ci = catInfo(cat);
    const date = exp.expense_date || (exp.upload_date
      ? new Date(exp.upload_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
      : '—');
    const amt = Number(exp.amount || 0).toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });

    const d = document.createElement('div');
    d.className = 'exp-item';
    d.setAttribute('role', 'button');
    d.setAttribute('tabindex', '0');
    d.setAttribute('aria-label', 'Edit expense from ' + (exp.vendor || 'unknown vendor'));
    d.innerHTML = `
      <div class="exp-icon ${ci.cls}"><i class="ti ${ci.icon}" aria-hidden="true"></i></div>
      <div class="exp-main">
        <div class="exp-vendor">${exp.vendor || 'Unknown vendor'}</div>
        <div class="exp-meta">${cat} · ${date}</div>
      </div>
      <span class="exp-amt">₹${amt}</span>
      <i class="ti ti-pencil exp-edit-icon" aria-hidden="true"></i>`;
    d.addEventListener('click', () => openModal(idx));
    d.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') openModal(idx);
    });
    el.appendChild(d);
  });
}

let editingExpense = null;

function openModal(idx) {
  const exp = currentExpenses[idx];
  if (!exp) return;
  editingExpense = exp;
  document.getElementById('ef-vendor').value = exp.vendor || '';
  document.getElementById('ef-amount').value = Number(exp.amount || 0);
  document.getElementById('ef-category').value = exp.category || 'Miscellaneous';
  document.getElementById('ef-date').value = exp.expense_date || '';
  document.getElementById('ef-raw').textContent = exp.raw_text || '(no extracted text)';
  document.getElementById('modal-overlay').classList.add('on');
  loadReceiptImage(exp.expense_id);
}

function loadReceiptImage(expenseId) {
  const pane = document.getElementById('ef-image-pane');
  pane.innerHTML = '<p class="receipt-img-msg">Loading receipt…</p>';

  authFetch(`${API_BASE}/expenses/${expenseId}/image`)
    .then(res => {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(data => {
      if (!data.image_url) throw new Error('No image_url');
      const img = document.createElement('img');
      img.alt = 'Receipt';
      img.onerror = () => {
        pane.innerHTML = '<p class="receipt-img-msg err">Receipt image unavailable</p>';
      };
      img.src = data.image_url;
      pane.innerHTML = '';
      pane.appendChild(img);
    })
    .catch(() => {
      pane.innerHTML = '<p class="receipt-img-msg err">Receipt image unavailable</p>';
    });
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('on');
  document.getElementById('ef-image-pane').innerHTML = '<p class="receipt-img-msg">Loading receipt…</p>';
  editingExpense = null;
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && document.getElementById('modal-overlay').classList.contains('on')) {
    closeModal();
  }
});

async function deleteExpense() {
  if (!editingExpense) return;
  if (!confirm('Delete this expense permanently?')) return;

  const btn = document.getElementById('ef-delete');
  btn.disabled = true;
  const originalContent = btn.innerHTML;
  btn.innerHTML = '<div class="spinner"></div> Deleting…';

  try {
    const res = await authFetch(`${API_BASE}/expenses/${editingExpense.expense_id}`, {
      method: 'DELETE'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || ('HTTP ' + res.status));
    }
    showToast('Expense deleted', 'ok');
    closeModal();
    loadExpenses();
  } catch (err) {
    showToast(err.message || 'Could not delete expense', 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalContent;
  }
}

async function saveExpenseEdit() {
  if (!editingExpense) return;
  const btn = document.getElementById('ef-save');
  const vendor = document.getElementById('ef-vendor').value.trim();
  const amountRaw = document.getElementById('ef-amount').value;
  const category = document.getElementById('ef-category').value;
  const expense_date = document.getElementById('ef-date').value.trim();

  const amount = Number(amountRaw);
  if (isNaN(amount) || amount < 0) {
    showToast('Enter a valid amount', 'err');
    return;
  }
  if (!vendor) {
    showToast('Vendor cannot be empty', 'err');
    return;
  }

  btn.disabled = true;
  const originalContent = btn.innerHTML;
  btn.innerHTML = '<div class="spinner"></div> Saving…';

  try {
    const res = await authFetch(`${API_BASE}/expenses/${editingExpense.expense_id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vendor, amount, category, expense_date })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || ('HTTP ' + res.status));
    }
    showToast('Changes saved', 'ok');
    closeModal();
    loadExpenses();
  } catch (err) {
    showToast(err.message || 'Could not save changes', 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalContent;
  }
}

boot();
