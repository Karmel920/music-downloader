(() => {
  "use strict";

  const DEFAULTS = {
    serverUrl: "http://127.0.0.1:8765",
    output: "",
    format: "mp3",
    quality: "320",
  };

  const CONTAINER_ID = "ytmp3dl-actions";

  function getSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(DEFAULTS, (items) => resolve({ ...DEFAULTS, ...items }));
    });
  }

  function send(message) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(message, (resp) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        if (!resp || !resp.ok) {
          reject(new Error((resp && resp.error) || "błąd"));
          return;
        }
        resolve(resp.data);
      });
    });
  }

  function currentVideoId() {
    return new URLSearchParams(location.search).get("v");
  }

  function currentListId() {
    return new URLSearchParams(location.search).get("list");
  }

  function setBtnState(btn, text, state) {
    btn.textContent = text;
    btn.dataset.state = state || "";
    btn.disabled = state === "busy";
  }

  async function deliverToClient(btn, serverUrl, jobId, completed, baseLabel) {
    setBtnState(btn, "Zapisywanie...", "busy");
    try {
      await send({ type: "clientDownload", url: `${serverUrl}/file?id=${encodeURIComponent(jobId)}` });
      const n = completed || 0;
      setBtnState(btn, n > 1 ? `Pobrano (${n})` : "Pobrano", "done");
    } catch (err) {
      setBtnState(btn, "Błąd zapisu", "error");
      btn.title = err.message || "Nie udało się zapisać pliku na dysku.";
    }
    setTimeout(() => setBtnState(btn, baseLabel, ""), 4000);
  }

  async function pollStatus(btn, serverUrl, jobId, baseLabel) {
    let job;
    try {
      job = await send({ type: "status", serverUrl, jobId });
    } catch (err) {
      setBtnState(btn, "Serwer offline", "error");
      btn.title = "Nie można połączyć z serwerem. Uruchom server.py.";
      setTimeout(() => setBtnState(btn, baseLabel, ""), 6000);
      return;
    }

    if (job.status === "done") {
      deliverToClient(btn, serverUrl, jobId, job.completed, baseLabel);
      return;
    }
    if (job.status === "error") {
      setBtnState(btn, "Błąd", "error");
      btn.title = job.error || "Nieznany błąd";
      setTimeout(() => setBtnState(btn, baseLabel, ""), 6000);
      return;
    }

    let label = "Pobieranie...";
    if (job.stage === "converting") label = "Konwersja...";
    else if (job.percent) label = job.percent;
    if (job.completed && job.completed > 0) label += ` (${job.completed})`;
    setBtnState(btn, label, "busy");
    setTimeout(() => pollStatus(btn, serverUrl, jobId, baseLabel), 1000);
  }

  async function startDownload(btn, url, noplaylist, baseLabel) {
    const settings = await getSettings();
    setBtnState(btn, "Łączenie...", "busy");
    try {
      const data = await send({
        type: "startDownload",
        serverUrl: settings.serverUrl,
        body: {
          url,
          format: settings.format,
          quality: settings.quality,
          noplaylist,
        },
      });
      pollStatus(btn, settings.serverUrl, data.job_id, baseLabel);
    } catch (err) {
      setBtnState(btn, "Serwer offline", "error");
      btn.title = "Nie można połączyć z serwerem. Uruchom server.py.";
      setTimeout(() => setBtnState(btn, baseLabel, ""), 6000);
    }
  }

  function makeButton(label) {
    const btn = document.createElement("button");
    btn.className = "ytmp3dl-btn";
    setBtnState(btn, label, "");
    return btn;
  }

  function buildContainer() {
    const wrap = document.createElement("div");
    wrap.id = CONTAINER_ID;
    wrap.className = "ytmp3dl-wrap";

    const videoId = currentVideoId();
    const listId = currentListId();

    if (videoId) {
      const label = "\u2B07 Pobierz utwór";
      const btn = makeButton(label);
      btn.addEventListener("click", () => {
        startDownload(btn, `https://www.youtube.com/watch?v=${videoId}`, true, label);
      });
      wrap.appendChild(btn);
    }

    if (listId) {
      const label = "\u2B07 Pobierz playlistę";
      const btn = makeButton(label);
      btn.addEventListener("click", () => {
        startDownload(btn, `https://www.youtube.com/playlist?list=${listId}`, false, label);
      });
      wrap.appendChild(btn);
    }

    return wrap.childElementCount ? wrap : null;
  }

  function inject() {
    const path = location.pathname;
    const isWatch = path === "/watch";
    const isPlaylist = path === "/playlist";
    if (!isWatch && !isPlaylist) return;

    if (document.getElementById(CONTAINER_ID)) return;

    let anchor = null;
    if (isWatch) {
      anchor =
        document.querySelector("ytd-watch-metadata #actions #menu") ||
        document.querySelector("ytd-watch-metadata #actions") ||
        document.querySelector("ytd-watch-metadata #title");
    } else {
      anchor =
        document.querySelector("ytd-playlist-header-renderer .metadata-buttons") ||
        document.querySelector("yt-page-header-renderer") ||
        document.querySelector("ytd-playlist-header-renderer");
    }
    if (!anchor) return;

    const container = buildContainer();
    if (!container) return;
    anchor.appendChild(container);
  }

  // YouTube is a SPA: re-inject on navigation and DOM changes.
  const observer = new MutationObserver(() => inject());
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.addEventListener("yt-navigate-finish", () => {
    const existing = document.getElementById(CONTAINER_ID);
    if (existing) existing.remove();
    setTimeout(inject, 300);
  });

  inject();
})();
