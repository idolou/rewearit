/* Shared JWT auth helper & modal for ReWearIt marketplace pages. */
(function () {
  const TOKEN_KEY = "rewearit_jwt";
  const USER_KEY = "rewearit_user";
  let onAuthChange = null;
  let pendingCallback = null;
  let modalMode = "login";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function getUser() {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function saveSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    renderNavSlots();
    if (typeof onAuthChange === "function") onAuthChange(user);
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    renderNavSlots();
    if (typeof onAuthChange === "function") onAuthChange(null);
  }

  function authHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;
    return headers;
  }

  function ensureModal() {
    if (document.getElementById("rw-auth-backdrop")) return;
    const div = document.createElement("div");
    div.id = "rw-auth-backdrop";
    div.style.cssText =
      "display:none;position:fixed;inset:0;background:rgba(0,0,0,0.75);backdrop-filter:blur(4px);z-index:200;align-items:center;justify-content:center;padding:1rem;";
    div.innerHTML = `
      <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;max-width:420px;width:100%;padding:1.75rem;color:#f8fafc;box-shadow:0 12px 40px rgba(0,0,0,0.5);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;">
          <h2 id="rw-auth-title" style="font-size:1.25rem;margin:0;">Sign In to ReWearIt</h2>
          <button type="button" id="rw-auth-close" style="background:none;border:none;color:#94a3b8;font-size:1.3rem;cursor:pointer;">&times;</button>
        </div>
        <div style="display:flex;gap:0.5rem;margin-bottom:1rem;">
          <button type="button" id="rw-tab-login" style="flex:1;padding:0.45rem;border-radius:6px;border:1px solid #334155;cursor:pointer;font-weight:600;">Sign In</button>
          <button type="button" id="rw-tab-register" style="flex:1;padding:0.45rem;border-radius:6px;border:1px solid #334155;cursor:pointer;font-weight:600;">Create Account</button>
        </div>
        <form id="rw-auth-form">
          <div id="rw-name-wrap" style="display:none;margin-bottom:0.85rem;">
            <label style="display:block;font-size:0.85rem;color:#94a3b8;margin-bottom:0.3rem;">Display Name</label>
            <input id="rw-auth-name" type="text" placeholder="Alex Rivera" style="width:100%;background:#0b0f19;border:1px solid #334155;border-radius:8px;padding:0.65rem;color:#f8fafc;">
          </div>
          <div style="margin-bottom:0.85rem;">
            <label style="display:block;font-size:0.85rem;color:#94a3b8;margin-bottom:0.3rem;">Email</label>
            <input id="rw-auth-email" type="email" required placeholder="you@example.com" style="width:100%;background:#0b0f19;border:1px solid #334155;border-radius:8px;padding:0.65rem;color:#f8fafc;">
          </div>
          <div style="margin-bottom:1rem;">
            <label style="display:block;font-size:0.85rem;color:#94a3b8;margin-bottom:0.3rem;">Password (min 8 chars)</label>
            <input id="rw-auth-password" type="password" required minlength="8" style="width:100%;background:#0b0f19;border:1px solid #334155;border-radius:8px;padding:0.65rem;color:#f8fafc;">
          </div>
          <div id="rw-auth-error" style="display:none;background:rgba(239,68,68,0.2);color:#fca5a5;padding:0.6rem;border-radius:6px;font-size:0.85rem;margin-bottom:0.85rem;"></div>
          <button id="rw-auth-submit" type="submit" style="width:100%;background:linear-gradient(135deg,#38bdf8,#6366f1);color:#fff;border:none;border-radius:8px;padding:0.75rem;font-weight:700;cursor:pointer;">Sign In</button>
        </form>
      </div>
    `;
    document.body.appendChild(div);

    document.getElementById("rw-auth-close").onclick = closeModal;
    document.getElementById("rw-tab-login").onclick = () => setMode("login");
    document.getElementById("rw-tab-register").onclick = () => setMode("register");
    document.getElementById("rw-auth-form").onsubmit = handleSubmit;
    setMode("login");
  }

  function setMode(mode) {
    modalMode = mode;
    const isReg = mode === "register";
    document.getElementById("rw-auth-title").textContent = isReg ? "Create ReWearIt Account" : "Sign In to ReWearIt";
    document.getElementById("rw-name-wrap").style.display = isReg ? "block" : "none";
    document.getElementById("rw-auth-name").required = isReg;
    document.getElementById("rw-auth-submit").textContent = isReg ? "Create Account" : "Sign In";
    const activeStyle = "background:#38bdf8;color:#0b1120;border-color:#38bdf8;";
    const idleStyle = "background:#0b0f19;color:#94a3b8;border-color:#334155;";
    document.getElementById("rw-tab-login").style.cssText += isReg ? idleStyle : activeStyle;
    document.getElementById("rw-tab-register").style.cssText += isReg ? activeStyle : idleStyle;
    document.getElementById("rw-auth-error").style.display = "none";
  }

  function openModal(mode, cb) {
    ensureModal();
    setMode(mode || "login");
    pendingCallback = typeof cb === "function" ? cb : null;
    document.getElementById("rw-auth-backdrop").style.display = "flex";
  }

  function closeModal() {
    const el = document.getElementById("rw-auth-backdrop");
    if (el) el.style.display = "none";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errEl = document.getElementById("rw-auth-error");
    const btn = document.getElementById("rw-auth-submit");
    errEl.style.display = "none";
    btn.disabled = true;

    const email = document.getElementById("rw-auth-email").value.trim();
    const password = document.getElementById("rw-auth-password").value;
    const payload = { email, password };
    if (modalMode === "register") {
      payload.display_name = document.getElementById("rw-auth-name").value.trim();
    }

    try {
      const endpoint = modalMode === "register" ? "/api/v1/auth/register" : "/api/v1/auth/login";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication failed");
      saveSession(data.access_token, data.user);
      closeModal();
      const cb = pendingCallback;
      pendingCallback = null;
      if (cb) cb(data.user);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = "block";
    } finally {
      btn.disabled = false;
    }
  }

  function renderNavSlots() {
    const slot = document.getElementById("rw-auth-slot");
    if (!slot) return;
    const user = getUser();
    if (user && getToken()) {
      slot.innerHTML = "";
      const nameSpan = document.createElement("span");
      nameSpan.style.cssText = "color:#e2e8f0;font-size:0.85rem;font-weight:600;";
      nameSpan.textContent = user.display_name || user.email;
      const outBtn = document.createElement("button");
      outBtn.type = "button";
      outBtn.textContent = "Sign Out";
      outBtn.style.cssText =
        "background:#334155;color:#f8fafc;border:none;padding:0.4rem 0.75rem;border-radius:6px;font-size:0.82rem;cursor:pointer;margin-left:0.5rem;";
      outBtn.onclick = logout;
      slot.appendChild(nameSpan);
      slot.appendChild(outBtn);
    } else {
      slot.innerHTML = "";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Sign In";
      btn.style.cssText =
        "background:transparent;color:#38bdf8;border:1px solid #38bdf8;padding:0.4rem 0.85rem;border-radius:6px;font-size:0.85rem;font-weight:600;cursor:pointer;";
      btn.onclick = () => openModal("login");
      slot.appendChild(btn);
    }
  }

  async function init(callback) {
    onAuthChange = callback || null;
    ensureModal();
    if (getToken()) {
      try {
        const res = await fetch("/api/v1/auth/me", { headers: authHeaders() });
        if (res.ok) {
          const user = await res.json();
          localStorage.setItem(USER_KEY, JSON.stringify(user));
        } else if (res.status === 401) {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(USER_KEY);
        }
      } catch (_) {}
    }
    renderNavSlots();
    if (typeof onAuthChange === "function") onAuthChange(getUser());
  }

  window.ReWearAuth = {
    init,
    getToken,
    getUser,
    authHeaders,
    openModal,
    logout,
    requireAuth(cb) {
      if (getToken() && getUser()) {
        cb(getUser());
      } else {
        openModal("login", cb);
      }
    },
  };
})();
