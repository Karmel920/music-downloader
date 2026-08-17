"use strict";

// Downloads initiated by this extension; used to scope the subfolder rewrite.
const ourDownloads = new Set();

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function sanitizeSubfolder(value) {
  if (!value) return "";
  return value
    .replace(/\\/g, "/")
    .replace(/[:*?"<>|]/g, "")
    .split("/")
    .filter((p) => p && p !== "." && p !== "..")
    .join("/");
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "startDownload") {
        const data = await fetchJson(`${msg.serverUrl}/download`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(msg.body),
        });
        sendResponse({ ok: true, data });
      } else if (msg.type === "status") {
        const data = await fetchJson(
          `${msg.serverUrl}/status?id=${encodeURIComponent(msg.jobId)}`
        );
        sendResponse({ ok: true, data });
      } else if (msg.type === "health") {
        const data = await fetchJson(`${msg.serverUrl}/health`);
        sendResponse({ ok: true, data });
      } else if (msg.type === "clientDownload") {
        chrome.downloads.download({ url: msg.url }, (id) => {
          if (chrome.runtime.lastError || id === undefined) {
            sendResponse({
              ok: false,
              error: (chrome.runtime.lastError && chrome.runtime.lastError.message) || "download failed",
            });
          } else {
            ourDownloads.add(id);
            sendResponse({ ok: true, data: { id } });
          }
        });
      } else {
        sendResponse({ ok: false, error: "unknown action" });
      }
    } catch (err) {
      sendResponse({ ok: false, error: err.message });
    }
  })();
  return true; // keep the message channel open for the async response
});

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  if (!ourDownloads.has(item.id)) {
    suggest();
    return;
  }
  chrome.storage.local.get({ output: "" }, (cfg) => {
    const sub = sanitizeSubfolder(cfg.output);
    if (sub) suggest({ filename: `${sub}/${item.filename}` });
    else suggest();
  });
  return true; // async suggest
});

chrome.downloads.onChanged.addListener((delta) => {
  if (delta.state && delta.state.current !== "in_progress") {
    ourDownloads.delete(delta.id);
  }
});
