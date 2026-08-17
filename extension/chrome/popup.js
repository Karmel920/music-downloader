const DEFAULTS = {
  serverUrl: "http://127.0.0.1:8765",
  output: "",
  format: "mp3",
  quality: "320",
};

const $ = (id) => document.getElementById(id);

function setStatus(text, kind) {
  const el = $("status");
  el.textContent = text;
  el.className = "status" + (kind ? ` ${kind}` : "");
}

function load() {
  chrome.storage.local.get(DEFAULTS, (items) => {
    const cfg = { ...DEFAULTS, ...items };
    $("serverUrl").value = cfg.serverUrl;
    $("output").value = cfg.output;
    $("format").value = cfg.format;
    $("quality").value = cfg.quality;
  });
}

function save() {
  const cfg = {
    serverUrl: $("serverUrl").value.trim() || DEFAULTS.serverUrl,
    output: $("output").value.trim(),
    format: $("format").value,
    quality: $("quality").value.trim() || DEFAULTS.quality,
  };
  chrome.storage.local.set(cfg, () => setStatus("Zapisano ustawienia.", "ok"));
}

function sendMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (resp) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!resp || !resp.ok) return reject(new Error((resp && resp.error) || "błąd"));
      resolve(resp.data);
    });
  });
}

async function check() {
  const url = $("serverUrl").value.trim() || DEFAULTS.serverUrl;
  setStatus("Sprawdzam...", "");
  try {
    const data = await sendMessage({ type: "health", serverUrl: url });
    setStatus(`Serwer działa (yt-dlp ${data.yt_dlp}).`, "ok");
  } catch (err) {
    setStatus("Serwer nieosiągalny. Uruchom server.py.", "err");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  load();
  $("save").addEventListener("click", save);
  $("check").addEventListener("click", check);
});
