(function () {
  // Find the script tag that loaded this SDK
  var currentScript =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      return scripts[scripts.length - 1];
    })();

  if (!currentScript) return;

  // Read configuration from data-attributes
  var apiKey = currentScript.getAttribute("data-api-key") || "";
  var baseUrl = currentScript.getAttribute("data-base-url") || window.location.origin;

  // Backend URL: default to same origin as where the SDK is hosted, override via data-backend-url
  var backendUrl =
    currentScript.getAttribute("data-backend-url") ||
    (function () {
      try {
        var u = new URL(currentScript.src, window.location.href);
        return u.origin;
      } catch (e) {
        return window.location.origin;
      }
    })();

  // Create a host element and attach a shadow DOM to avoid leaking styles
  var host = document.createElement("div");
  host.id = "nina-sdk-root";
  document.body.appendChild(host);

  var shadow = host.attachShadow({ mode: "open" });

  // Styles for FAB and panel
  var style = document.createElement("style");
  style.textContent = `
    :host {
      all: initial;
    }
    .nina-fab {
      position: fixed;
      right: 24px;
      bottom: 24px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      border: none;
      background: #07090f;
      color: #00e5ff;
      box-shadow: 0 0 0 1px rgba(0,229,255,0.4), 0 10px 25px rgba(0,0,0,0.6);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-weight: 600;
      font-size: 14px;
      z-index: 2147483647;
    }
    .nina-fab:hover {
      box-shadow: 0 0 0 1px rgba(0,229,255,0.8), 0 14px 30px rgba(0,0,0,0.8);
      transform: translateY(-1px);
    }
    .nina-panel {
      position: fixed;
      right: 24px;
      bottom: 96px;
      width: 360px;
      max-width: calc(100vw - 48px);
      height: 480px;
      max-height: calc(100vh - 120px);
      background: #020308;
      border-radius: 12px;
      box-shadow: 0 18px 45px rgba(0,0,0,0.85);
      border: 1px solid rgba(0,229,255,0.4);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      pointer-events: none;
      transform: translateY(8px);
      transition: opacity 0.18s ease-out, transform 0.18s ease-out;
      z-index: 2147483647;
      color: #e5f3ff;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .nina-panel.open {
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0);
    }
    .nina-panel-header {
      padding: 10px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(0,229,255,0.25);
      background: radial-gradient(circle at top left, rgba(0,229,255,0.16), transparent 55%);
    }
    .nina-title {
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #a9c7ff;
    }
    .nina-badge {
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 999px;
      border: 1px solid rgba(0,229,255,0.6);
      color: #00e5ff;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .nina-close {
      background: transparent;
      border: none;
      color: #8b9bb8;
      cursor: pointer;
      font-size: 14px;
      padding: 2px 4px;
      margin-left: 8px;
    }
    .nina-body {
      flex: 1;
      padding: 10px 14px;
      font-size: 12px;
      line-height: 1.4;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .nina-caption {
      font-size: 11px;
      color: #7b8ba6;
    }
    .nina-input-row {
      display: flex;
      gap: 6px;
      margin-top: auto;
    }
    .nina-input {
      flex: 1;
      padding: 6px 8px;
      border-radius: 6px;
      border: 1px solid #1b2333;
      background: #050813;
      color: #e5f3ff;
      font-size: 12px;
    }
    .nina-input:focus {
      outline: none;
      border-color: #00e5ff;
      box-shadow: 0 0 0 1px rgba(0,229,255,0.45);
    }
    .nina-send {
      padding: 0 10px;
      border-radius: 6px;
      border: 1px solid rgba(0,229,255,0.7);
      background: #031016;
      color: #00e5ff;
      font-size: 12px;
      cursor: pointer;
    }
    .nina-send:disabled {
      opacity: 0.5;
      cursor: default;
    }
  `;
  shadow.appendChild(style);

  // FAB
  var fab = document.createElement("button");
  fab.className = "nina-fab";
  fab.type = "button";
  fab.textContent = "N";

  // Panel
  var panel = document.createElement("div");
  panel.className = "nina-panel";

  var header = document.createElement("div");
  header.className = "nina-panel-header";

  var title = document.createElement("div");
  title.className = "nina-title";
  title.textContent = "NINA";

  var badge = document.createElement("div");
  badge.className = "nina-badge";
  badge.textContent = "READY";

  var closeBtn = document.createElement("button");
  closeBtn.className = "nina-close";
  closeBtn.type = "button";
  closeBtn.textContent = "✕";

  header.appendChild(title);
  header.appendChild(badge);
  header.appendChild(closeBtn);

  var body = document.createElement("div");
  body.className = "nina-body";
  var caption = document.createElement("div");
  caption.className = "nina-caption";
  caption.textContent =
    "Connected to Nina backend at " +
    backendUrl +
    ". Paste integration script once; nothing else on your site changes.";
  body.appendChild(caption);

  var inputRow = document.createElement("div");
  inputRow.className = "nina-input-row";
  var input = document.createElement("input");
  input.className = "nina-input";
  input.type = "text";
  input.placeholder = "Ask Nina... (wiring to /run coming next)";
  var send = document.createElement("button");
  send.className = "nina-send";
  send.type = "button";
  send.textContent = "Send";
  send.disabled = true; // placeholder; real backend hookup can enable this

  inputRow.appendChild(input);
  inputRow.appendChild(send);
  body.appendChild(inputRow);

  panel.appendChild(header);
  panel.appendChild(body);

  shadow.appendChild(panel);
  shadow.appendChild(fab);

  var open = false;
  function togglePanel(force) {
    open = typeof force === "boolean" ? force : !open;
    if (open) {
      panel.classList.add("open");
    } else {
      panel.classList.remove("open");
    }
  }

  fab.addEventListener("click", function () {
    togglePanel();
  });
  closeBtn.addEventListener("click", function () {
    togglePanel(false);
  });
})();


