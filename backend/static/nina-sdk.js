(function() {
  // ── Read config from script tag ──────────────────────────────
  const scriptTag  = document.currentScript;
  const API_KEY    = scriptTag.getAttribute("data-nina-key") || "";
  const POSITION   = scriptTag.getAttribute("data-nina-position") || "bottom-right";
  const API_BASE   = scriptTag.getAttribute("data-nina-api") || "http://localhost:8000";
  const PANEL_WIDTH = "420px";

  if (!API_KEY) {
    console.warn("[Nina] No data-nina-key found on script tag.");
  }

  // ── State ─────────────────────────────────────────────────────
  let panelOpen    = false;
  const NINA_SESSION_KEY = "nina_session_id";
  function getChatStorageKey() {
    try {
      var o = (typeof window !== "undefined" && window.location && window.location.origin) ? window.location.origin : "";
      return "nina_chat_" + (o || "default");
    } catch (e) { return "nina_chat_default"; }
  }
  let sessionId    = (function() {
    try {
      const stored = localStorage.getItem(NINA_SESSION_KEY);
      if (stored) return stored;
      const id = "sess_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem(NINA_SESSION_KEY, id);
      return id;
    } catch (e) { return "sess_" + Math.random().toString(36).slice(2, 10); }
  })();
  let chatHistory  = [];
  let isRunning    = false;
  let inputMode    = "tt"; // tt | vt | vv | tv

  function loadChatHistory() {
    try {
      var key = getChatStorageKey();
      var raw = localStorage.getItem(key);
      chatHistory = (raw ? JSON.parse(raw) : []);
      if (typeof console !== "undefined" && console.log) {
        console.log("[Nina] Chat loaded from storage: " + chatHistory.length + " messages (key: " + key + ")");
      }
      return chatHistory;
    } catch (e) { chatHistory = []; return []; }
  }
  function saveChatHistory() {
    try {
      var key = getChatStorageKey();
      var json = JSON.stringify(chatHistory);
      localStorage.setItem(key, json);
      if (typeof console !== "undefined" && console.log) {
        console.log("[Nina] Chat saved: " + chatHistory.length + " messages");
      }
    } catch (e) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn("[Nina] Could not save chat to localStorage", e);
      }
    }
  }
  // Load once at init (after key is stable)
  loadChatHistory();

  // ── Inject styles ─────────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = `
    #nina-fab {
      position: fixed;
      bottom: 28px;
      right: 28px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #07090f;
      border: 2px solid #00e5ff;
      box-shadow: 0 0 20px #00e5ff44;
      cursor: pointer;
      z-index: 999999;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
    }
    #nina-fab:hover {
      box-shadow: 0 0 32px #00e5ff88;
      transform: scale(1.08);
    }
    #nina-fab svg { pointer-events: none; }

    #nina-panel {
      position: fixed;
      top: 0;
      right: 0;
      width: ${PANEL_WIDTH};
      height: 100vh;
      background: #07090f;
      border-left: 1px solid #1c2d4a;
      z-index: 999998;
      transform: translateX(100%);
      transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      flex-direction: column;
      font-family: 'JetBrains Mono', monospace;
      overflow: hidden;
    }
    #nina-panel.open {
      transform: translateX(0);
    }

    #nina-host-shrink {
      transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    }

    #nina-panel-header {
      padding: 16px 20px;
      border-bottom: 1px solid #1c2d4a;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #0b1020;
      flex-shrink: 0;
    }
    #nina-logo {
      font-size: 18px;
      font-weight: 700;
      color: #f0f4fc;
      letter-spacing: -1px;
    }
    #nina-logo span { color: #00e5ff; }

    #nina-mode-switcher {
      display: flex;
      gap: 4px;
    }
    .nina-mode-btn {
      padding: 3px 8px;
      font-size: 9px;
      letter-spacing: 1px;
      border-radius: 4px;
      border: 1px solid #1c2d4a;
      background: transparent;
      color: #6b80a8;
      cursor: pointer;
      font-family: inherit;
      transition: all 0.15s;
    }
    .nina-mode-btn.active {
      border-color: #00e5ff;
      color: #00e5ff;
      background: #051520;
    }

    #nina-close {
      background: none;
      border: none;
      color: #6b80a8;
      cursor: pointer;
      font-size: 18px;
      line-height: 1;
      padding: 0;
      margin-left: 12px;
    }
    #nina-close:hover { color: #f0f4fc; }

    #nina-chat-area {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    #nina-chat-area::-webkit-scrollbar { width: 3px; }
    #nina-chat-area::-webkit-scrollbar-thumb { background: #1c2d4a; border-radius: 2px; }

    .nina-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 12px;
      line-height: 1.6;
    }
    .nina-msg.user {
      align-self: flex-end;
      background: #051520;
      border: 1px solid #00e5ff44;
      color: #00e5ff;
    }
    .nina-msg.nina {
      align-self: flex-start;
      background: #0b1020;
      border: 1px solid #1c2d4a;
      color: #dde8f8;
    }
    .nina-msg.nina.thinking {
      color: #6b80a8;
      font-style: italic;
    }

    .nina-steps-list {
      margin-top: 8px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .nina-step-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      padding: 5px 8px;
      border-radius: 5px;
      background: #060912;
      border: 1px solid #1c2d4a;
    }
    .nina-step-row.ok     { border-color: #00ff9444; color: #00ff94; }
    .nina-step-row.fail   { border-color: #ff3d6b44; color: #ff3d6b; }
    .nina-step-row.running { border-color: #00e5ff44; color: #00e5ff; }

    .nina-product-images {
      margin-top: 10px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }
    .nina-product-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      max-width: 110px;
      background: #060912;
      border: 1px solid #1c2d4a;
      border-radius: 8px;
      overflow: hidden;
      padding: 6px;
    }
    .nina-product-card img {
      width: 90px;
      height: 90px;
      object-fit: cover;
      border-radius: 6px;
      display: block;
    }
    .nina-product-card .nina-product-name {
      font-size: 11px;
      font-weight: 600;
      color: #dde8f8;
      margin-top: 6px;
      text-align: center;
      line-height: 1.3;
    }
    .nina-product-card .nina-product-price {
      font-size: 10px;
      color: #00e5ff;
      margin-top: 2px;
    }

    #nina-input-area {
      padding: 12px 16px;
      border-top: 1px solid #1c2d4a;
      display: flex;
      gap: 8px;
      align-items: center;
      background: #0b1020;
      flex-shrink: 0;
    }
    #nina-text-input {
      flex: 1;
      background: #060912;
      border: 1px solid #1c2d4a;
      border-radius: 8px;
      padding: 9px 12px;
      color: #f0f4fc;
      font-family: inherit;
      font-size: 12px;
      outline: none;
    }
    #nina-text-input:focus { border-color: #00e5ff; }
    #nina-text-input::placeholder { color: #2e3d5a; }

    #nina-send-btn, #nina-mic-btn {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      border: 1px solid #1c2d4a;
      background: #060912;
      color: #6b80a8;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s;
      flex-shrink: 0;
    }
    #nina-send-btn:hover { border-color: #00e5ff; color: #00e5ff; }
    #nina-mic-btn:hover  { border-color: #00e5ff; color: #00e5ff; }
    #nina-mic-btn.listening {
      border-color: #ff3d6b;
      color: #ff3d6b;
      background: #1a0010;
      animation: nina-pulse 1.2s infinite;
    }

    @keyframes nina-pulse {
      0%, 100% { box-shadow: none; }
      50% { box-shadow: 0 0 12px #ff3d6b66; }
    }
  `;
  document.head.appendChild(style);

  // ── FAB Button ────────────────────────────────────────────────
  const fab = document.createElement("div");
  fab.id = "nina-fab";
  fab.innerHTML = `<svg width="22" height="24" viewBox="0 0 22 24" fill="none" stroke="#00e5ff" stroke-width="1.8">
    <rect x="6" y="1" width="10" height="14" rx="5"/>
    <path d="M2 13c0 4.97 4.03 9 9 9s9-4.03 9-9"/>
    <line x1="11" y1="22" x2="11" y2="22"/>
  </svg>`;
  fab.addEventListener("click", togglePanel);
  document.body.appendChild(fab);

  // ── Panel ─────────────────────────────────────────────────────
  const panel = document.createElement("div");
  panel.id = "nina-panel";
  panel.innerHTML = `
    <div id="nina-panel-header">
      <div id="nina-logo">NI<span>NA</span></div>
      <div id="nina-mode-switcher">
        <button class="nina-mode-btn active" data-mode="tt">TT</button>
        <button class="nina-mode-btn" data-mode="vt">VT</button>
        <button class="nina-mode-btn" data-mode="tv">TV</button>
        <button class="nina-mode-btn" data-mode="vv">VV</button>
      </div>
      <button id="nina-close">×</button>
    </div>
    <div id="nina-chat-area"></div>
    <div id="nina-input-area">
      <input id="nina-text-input" type="text" placeholder="Type a command..."/>
      <button id="nina-mic-btn">
        <svg width="12" height="14" viewBox="0 0 12 14" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3.5" y="1" width="5" height="7" rx="2.5"/>
          <path d="M1 8c0 2.761 2.239 5 5 5s5-2.239 5-5"/>
        </svg>
      </button>
      <button id="nina-send-btn">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
          <polygon points="1,11 11,6 1,1 1,5 8,6 1,7"/>
        </svg>
      </button>
    </div>
  `;
  document.body.appendChild(panel);

  // ── Event listeners ───────────────────────────────────────────
  document.getElementById("nina-close").addEventListener("click", togglePanel);

  document.getElementById("nina-send-btn").addEventListener("click", () => {
    const input = document.getElementById("nina-text-input");
    const val = input.value.trim();
    if (val) { sendCommand(val); input.value = ""; }
  });

  document.getElementById("nina-text-input").addEventListener("keydown", e => {
    if (e.key === "Enter") {
      const input = e.target;
      const val = input.value.trim();
      if (val) { sendCommand(val); input.value = ""; }
    }
  });

  document.getElementById("nina-mic-btn").addEventListener("click", startVoice);

  document.querySelectorAll(".nina-mode-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nina-mode-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      inputMode = btn.getAttribute("data-mode");
    });
  });

  // ── Panel open/close ──────────────────────────────────────────
  function togglePanel() {
    panelOpen = !panelOpen;
    panel.classList.toggle("open", panelOpen);

    if (panelOpen) {
      document.body.style.marginRight = PANEL_WIDTH;
      document.body.style.transition  = "margin-right 0.35s cubic-bezier(0.4,0,0.2,1)";
      // Re-read from localStorage when opening so we always show latest saved history
      loadChatHistory();
      if (chatHistory.length > 0) {
        restoreChat();
      } else {
        addNinaMessage("Hey! I'm Nina. Tell me what you want to do on this page.", "nina");
      }
    } else {
      document.body.style.marginRight = "0";
    }
  }

  // ── Chat helpers ──────────────────────────────────────────────
  function createMessageEl(entry) {
    if (entry.role === "user") {
      const msg = document.createElement("div");
      msg.className = "nina-msg user";
      msg.textContent = entry.text;
      return msg;
    }
    const msg = document.createElement("div");
    msg.className = "nina-msg nina";
    msg.textContent = entry.text;
    var showProducts = entry.showProductImages === true || (entry.showProductImages !== false && entry.products && entry.products.length <= 2);
    if (showProducts && entry.products && entry.products.length > 0) {
      const productsWithImg = entry.products.filter(function(p) { return p && p.image; });
      if (productsWithImg.length > 0) {
        const wrap = document.createElement("div");
        wrap.className = "nina-product-images";
        productsWithImg.forEach(function(p) {
          const card = document.createElement("div");
          card.className = "nina-product-card";
          const img = document.createElement("img");
          img.src = p.image;
          img.alt = p.name || "Product";
          const nameEl = document.createElement("div");
          nameEl.className = "nina-product-name";
          nameEl.textContent = p.name || "Product";
          const priceEl = document.createElement("div");
          priceEl.className = "nina-product-price";
          priceEl.textContent = p.price || "";
          card.appendChild(img);
          card.appendChild(nameEl);
          if (p.price) card.appendChild(priceEl);
          wrap.appendChild(card);
        });
        msg.appendChild(wrap);
      }
    }
    return msg;
  }

  function restoreChat() {
    const chatArea = document.getElementById("nina-chat-area");
    chatArea.innerHTML = "";
    chatHistory.forEach(function(entry) {
      chatArea.appendChild(createMessageEl(entry));
    });
    chatArea.scrollTop = chatArea.scrollHeight;
  }

  function addUserMessage(text, skipPersist) {
    const chatArea = document.getElementById("nina-chat-area");
    const msg = document.createElement("div");
    msg.className = "nina-msg user";
    msg.textContent = text;
    chatArea.appendChild(msg);
    chatArea.scrollTop = chatArea.scrollHeight;
    if (!skipPersist) {
      chatHistory.push({ role: "user", text: text });
      saveChatHistory();
    }
  }

  function addNinaMessage(text, type, id, options) {
    if (typeof type !== "string") type = "nina";
    if (typeof id !== "string" && id != null) options = id, id = null;
    options = options || {};
    const chatArea = document.getElementById("nina-chat-area");
    const msg = document.createElement("div");
    msg.className = "nina-msg nina" + (type === "thinking" ? " thinking" : "");
    if (id) msg.id = id;
    msg.textContent = text;
    var showProducts = options.showProductImages && options.products && options.products.length > 0;
    if (showProducts) {
      const productsWithImg = options.products.filter(function(p) { return p && p.image; });
      if (productsWithImg.length > 0) {
        const wrap = document.createElement("div");
        wrap.className = "nina-product-images";
        productsWithImg.forEach(function(p) {
          const card = document.createElement("div");
          card.className = "nina-product-card";
          const img = document.createElement("img");
          img.src = p.image;
          img.alt = p.name || "Product";
          const nameEl = document.createElement("div");
          nameEl.className = "nina-product-name";
          nameEl.textContent = p.name || "Product";
          const priceEl = document.createElement("div");
          priceEl.className = "nina-product-price";
          priceEl.textContent = p.price || "";
          card.appendChild(img);
          card.appendChild(nameEl);
          if (p.price) card.appendChild(priceEl);
          wrap.appendChild(card);
        });
        msg.appendChild(wrap);
      }
    }
    chatArea.appendChild(msg);
    chatArea.scrollTop = chatArea.scrollHeight;
    if (!options.skipPersist && type !== "thinking") {
      chatHistory.push({ role: "nina", text: text, products: options.products || [], showProductImages: options.showProductImages });
      saveChatHistory();
    }
    return msg;
  }

  function updateMessage(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function addStepsDisplay(steps, results) {
    const chatArea = document.getElementById("nina-chat-area");
    const container = document.createElement("div");
    container.className = "nina-msg nina";
    const list = document.createElement("div");
    list.className = "nina-steps-list";
    steps.forEach((s, i) => {
      const r = (results || []).find(r => r.step === i);
      const st = r ? r.status : "pending";
      const row = document.createElement("div");
      row.className = `nina-step-row ${st === "ok" ? "ok" : st === "failed" ? "fail" : ""}`;
      row.innerHTML = `<span>${st === "ok" ? "✓" : st === "failed" ? "✕" : "○"}</span>
        <span style="color:#b06bff;min-width:42px">${s.action}</span>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.selector || s.url || ""}</span>`;
      list.appendChild(row);
    });
    container.appendChild(list);
    chatArea.appendChild(container);
    chatArea.scrollTop = chatArea.scrollHeight;
  }

  // ── In-browser executor: run steps in the real page ───────────
  async function executeStepsInBrowser(steps) {
    const results = [];

    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const { action, selector, value, url } = step;

      try {
        if (action === "navigate") {
          try {
            if (typeof sessionStorage !== "undefined") {
              // Remember to reopen panel on the next page load if it is currently open
              sessionStorage.setItem("nina_reopen_panel", panelOpen ? "1" : "0");
            }
          } catch (e) {}
          window.location.href = url;
          results.push({ step: i, action, status: "ok" });
          break; // navigation ends execution
        }

        if (action === "fill") {
          const el = await waitForElement(selector, 5000);
          el.focus();
          el.value = value;
          el.dispatchEvent(new Event("input",  { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          results.push({ step: i, action, status: "ok" });
        }

        if (action === "click") {
          const el = await waitForElement(selector, 5000);
          el.click();
          await sleep(400);
          results.push({ step: i, action, status: "ok" });
        }

        if (action === "check") {
          const el = await waitForElement(selector, 5000);
          if (!el.checked) el.click();
          results.push({ step: i, action, status: "ok" });
        }

        if (action === "scroll") {
          window.scrollBy(0, parseInt(value) || 500);
          await sleep(300);
          results.push({ step: i, action, status: "ok" });
        }

        await sleep(300);

      } catch (e) {
        results.push({ step: i, action, status: "failed", error: e.message });
        break;
      }
    }

    return results;
  }

  function waitForElement(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
      const el = document.querySelector(selector);
      if (el) return resolve(el);

      const observer = new MutationObserver(() => {
        const el = document.querySelector(selector);
        if (el) { observer.disconnect(); resolve(el); }
      });
      observer.observe(document.body, { childList: true, subtree: true });

      setTimeout(() => {
        observer.disconnect();
        reject(new Error(`Element not found: ${selector}`));
      }, timeout);
    });
  }

  function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  }

  // ── NFS / Auth helpers ─────────────────────────────────────────
  function checkAuthState(authConfig) {
    if (!authConfig || !authConfig.session_check) return false;
    const check = authConfig.session_check;
    if (check.type === "localStorage") {
      try {
        const raw = localStorage.getItem(check.key);
        if (!raw) return false;
        const obj = JSON.parse(raw);
        const val = check.field ? obj[check.field] : obj;
        return val === check.expected_value;
      } catch {
        return false;
      }
    }
    if (check.type === "cookie") {
      return document.cookie.split(";").some(c => c.trim().startsWith(check.key + "="));
    }
    return false;
  }

  function handleNeedsLogin(response, originalInput) {
    const msg = response.message || "You need to log in first. Want me to do that?";
    // Show message with Yes/No buttons in chat (rendered as text for now)
    addNinaMessage(msg + "\n\n[Yes, log me in] [No, cancel]", {
      type: "needs_login",
      onYes: () => {
        // Store queued intent so after login we auto-replay
        try {
          sessionStorage.setItem("nina_queued_intent", JSON.stringify(response.queued_intent));
        } catch {}
        // Re-send login command
        sendCommand("log me in");
      },
      onNo: () => {
        try {
          sessionStorage.removeItem("nina_queued_intent");
        } catch {}
      }
    });
  }

  async function handleApiCall(execution, params) {
    try {
      const url = execution.endpoint;
      const body = JSON.parse(
        JSON.stringify(execution.body_template || {})
          .replace(/\{(\w+)\}/g, function(_, k) { return params && params[k] != null ? params[k] : ""; })
      );
      const res = await fetch(url, {
        method: execution.method || "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (res.ok) {
        addNinaMessage("Done! The action was completed successfully.", "nina");
      } else {
        addNinaMessage("Something went wrong. The site returned an error.", "nina");
      }
    } catch (e) {
      addNinaMessage("Could not complete the action. Please try manually.", "nina");
    }
  }

  function replayQueuedIntentIfPresent() {
    let queued = null;
    try {
      queued = sessionStorage.getItem("nina_queued_intent");
    } catch {
      queued = null;
    }
    if (!queued) return;
    try {
      const intent = JSON.parse(queued);
      try {
        sessionStorage.removeItem("nina_queued_intent");
      } catch {}
      // Small delay to let page settle
      setTimeout(function() {
        if (intent && intent.user_input) {
          sendCommand(intent.user_input);
        }
      }, 800);
    } catch {
      try {
        sessionStorage.removeItem("nina_queued_intent");
      } catch {}
    }
  }

  // ── Voice input ───────────────────────────────────────────────
  function startVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { addNinaMessage("Voice input requires Chrome or Edge.", "nina"); return; }
    const btn = document.getElementById("nina-mic-btn");
    const rec = new SR();
    rec.lang = "en-US"; rec.interimResults = false;
    rec.onstart  = () => btn.classList.add("listening");
    rec.onend    = () => btn.classList.remove("listening");
    rec.onresult = e => {
      const text = e.results[0][0].transcript;
      document.getElementById("nina-text-input").value = text;
      sendCommand(text);
    };
    rec.start();
  }

  // ── Predefined replies for basic phrases (no backend/LLM call) ──
  var BASIC_PHRASES = {
    "hello": "Hi! I'm Nina. Tell me what you'd like to do on this page — go to a section, search for something, or fill a form.",
    "hi": "Hi! How can I help you on this site today?",
    "hey": "Hey! What would you like to do?",
    "thanks": "You're welcome!",
    "thank you": "You're welcome!",
    "bye": "Bye! Come back if you need anything.",
    "goodbye": "Bye! Come back if you need anything.",
    "what can you do": "I can navigate this site for you, open pages (e.g. Login, Products, Contact), answer questions about what's here, and help fill forms. Just tell me in plain language.",
    "help": "I can take you to pages, show products, or help with forms. Try: \"Go to login\", \"What products are there?\", or \"Sign me up with my@email.com\"."
  };
  function getPredefinedReply(input) {
    var t = (input || "").trim().toLowerCase();
    if (!t) return null;
    if (BASIC_PHRASES[t]) return BASIC_PHRASES[t];
    for (var key in BASIC_PHRASES) {
      if (t === key || t.startsWith(key + " ") || t === key + "!") return BASIC_PHRASES[key];
    }
    return null;
  }

  // ── Send command ──────────────────────────────────────────────
  async function sendCommand(text) {
    if (isRunning) return;
    isRunning = true;

    addUserMessage(text);
    var predefined = getPredefinedReply(text);
    if (predefined) {
      addNinaMessage(predefined, "nina");
      isRunning = false;
      return;
    }

    const thinkingId = "nina-thinking-" + Date.now();
    addNinaMessage("Thinking...", "thinking", thinkingId);

    try {
      const baseUrl = (typeof window !== "undefined" && window.location && window.location.origin) ? window.location.origin : "";
      const response = await fetch(`${API_BASE}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_input:   String(text),
          base_url:     baseUrl,
          api_key:      API_KEY != null ? String(API_KEY) : "",
          session_id:   sessionId || "default",
          extra_params: {}
        })
      });
      const data = await response.json();

      if (data.status === "needs_login") {
        removeMessage(thinkingId);
        handleNeedsLogin(data, text);
        isRunning = false;
        return;
      }

      if (data.status === "execute_api") {
        removeMessage(thinkingId);
        await handleApiCall(data.execution, data.resolved_params);
        isRunning = false;
        return;
      }

      removeMessage(thinkingId);

      if (data.status === "needs_input") {
        addNinaMessage("I need a bit more info: " + (data.missing_fields || []).join(", "), "nina");
      } else if (data.status === "error") {
        addNinaMessage("Something went wrong: " + (data.error || "Please try again."), "nina");
      } else if (data.status === "success") {
        var didAdd = false;
        if (data.query_result && data.query_result.answer) {
          var products = data.query_result.products || [];
          var askedForImage = /\b(show|image|picture|see|display)\b/i.test(String(text));
          var singleProduct = products.length === 1;
          var showProductImages = products.length > 0 && (singleProduct || askedForImage);
          addNinaMessage(data.query_result.answer, "nina", null, {
            products: products,
            showProductImages: showProductImages
          });
          didAdd = true;
        }
        var steps = data.steps || [];
        if (steps.length > 0) {
          addNinaMessage("Executing...", "thinking", "nina-exec-msg");
          const execResults = await executeStepsInBrowser(steps);
          removeMessage("nina-exec-msg");
          addNinaMessage("Done! Here is what I did:", "nina");
          addStepsDisplay(steps, execResults);
          didAdd = true;
        }
        if (!didAdd) {
          addNinaMessage("Request received. To add items to the cart, go to the product page and use the \"Add to Cart\" button there, or say e.g. \"Go to the polo shirt page\" and I can take you there.", "nina");
        }
      } else if (data.status === "partial") {
        addNinaMessage("I completed some steps but hit an issue:", "nina");
        addStepsDisplay(data.steps || [], data.results || []);
      } else {
        addNinaMessage("Something went wrong. Please try again.", "nina");
      }
    } catch (e) {
      removeMessage(thinkingId);
      addNinaMessage("Could not reach Nina backend: " + e.message, "nina");
    }

    isRunning = false;
  }

  console.log("[Nina SDK] Loaded. API:", API_BASE, "| Session:", sessionId, "| Chat key:", getChatStorageKey());
  replayQueuedIntentIfPresent();
  try {
    const reopen = typeof sessionStorage !== "undefined" && sessionStorage.getItem("nina_reopen_panel");
    if (reopen === "1") {
      sessionStorage.removeItem("nina_reopen_panel");
      if (!panelOpen) {
        togglePanel();
      }
    }
  } catch (e) {}
})();
