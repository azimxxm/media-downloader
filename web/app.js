/* Media Downloader — UI controller.
   Talks to the local Python core over fetch + Server-Sent Events. */

(() => {
  "use strict";

  /* ─────────────────────────── tiny helpers ─────────────────────────── */

  const $ = (id) => document.getElementById(id);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };

  // transport.js decides whether this goes over the pywebview bridge or HTTP.
  const api = (path, body) => window.transport.call(path, body);

  function detectPlatform(url) {
    if (!url) return "none";
    if (/instagram\.com\/(p|reel|reels|tv|stories)\//i.test(url)) return "instagram";
    if (/(youtube\.com|youtu\.be)/i.test(url)) return "youtube";
    return "none";
  }

  function shortenPath(path) {
    if (!path) return "";
    return path.replace(/^\/Users\/[^/]+/, "~");
  }

  function toast(message, kind = "") {
    const node = el("div", `toast ${kind}`.trim(), message);
    $("toast-stack").appendChild(node);
    setTimeout(() => {
      node.classList.add("leaving");
      setTimeout(() => node.remove(), 200);
    }, kind === "error" ? 6000 : 3200);
  }

  /* ─────────────────────────── app state ─────────────────────────── */

  const state = {
    settings: {},
    ffmpeg: { available: true },
    media: null,       // last analysed single item
    playlist: null,    // last analysed playlist
    mode: "video",
    quality: "best",
    playlistMode: "video",
    destination: "",
    jobs: new Map(),   // id -> job
    jobNodes: new Map(),
  };

  const MODE_LABELS = {
    video: "Video",
    audio: "Audio",
    photo: "Rasm",
    thumbnail: "Thumbnail",
  };

  const STATE_LABELS = {
    queued: "Navbatda",
    running: "Yuklanmoqda",
    processing: "Qayta ishlanmoqda",
    completed: "Tayyor",
    error: "Xatolik",
    cancelled: "Bekor qilindi",
  };

  /* ─────────────────────────── bootstrap ─────────────────────────── */

  async function bootstrap() {
    const data = await api("/api/bootstrap");

    $("version").textContent = `v${data.version}`;
    state.settings = data.settings;
    state.destination = data.settings.youtube_dir;
    updateDestination();
    applyFfmpeg(data.ffmpeg);

    $("setting-parallel").value = String(data.settings.max_parallel);
    renderSettings();

    (data.jobs || []).forEach(upsertJob);
    renderJobsVisibility();
  }

  function applyFfmpeg(info) {
    state.ffmpeg = info;
    const banner = $("ffmpeg-banner");
    banner.hidden = !!info.available;
    if (!info.available) $("ffmpeg-message").textContent = "Video/audio birlashtirish uchun kerak.";
    $("setting-ffmpeg").textContent = info.available
      ? (info.path || info.message)
      : "O'rnatilmagan";
  }

  function renderSettings() {
    $("setting-yt-dir").textContent = shortenPath(state.settings.youtube_dir);
    $("setting-ig-dir").textContent = shortenPath(state.settings.instagram_dir);
  }

  /* ─────────────────────────── live events ─────────────────────────── */

  function connectEvents() {
    window.transport.onEvent((payload) => {
      if (payload.type === "job") {
        const previous = state.jobs.get(payload.job.id);
        upsertJob(payload.job);
        announceJob(previous, payload.job);
        renderJobsVisibility();
      } else if (payload.type === "jobs_cleared") {
        renderJobsVisibility();
      }
    });
  }

  function announceJob(previous, job) {
    if (previous && previous.status === job.status) return;
    if (job.status === "completed") toast(`✅ ${job.title || "Fayl"} yuklandi`, "success");
    else if (job.status === "error") toast(`⚠️ ${job.error || "Yuklab olishda xatolik"}`, "error");
  }

  /* ─────────────────────────── analyse ─────────────────────────── */

  function setUrlError(message) {
    const hint = $("url-hint");
    hint.textContent = message || "YouTube video, Shorts, playlist · Instagram post, reel, story";
    hint.classList.toggle("error", !!message);
  }

  function setAnalyzing(active) {
    const button = $("analyze-btn");
    button.disabled = active;
    button.classList.toggle("loading", active);
    button.querySelector(".spinner").hidden = !active;
  }

  async function analyze() {
    const url = $("url-input").value.trim();
    if (!url) {
      setUrlError("URL kiriting");
      return;
    }

    setUrlError("");
    setAnalyzing(true);

    try {
      const data = await api("/api/analyze", { url });
      state.destination = data.suggested_dir || state.destination;

      if (data.kind === "playlist") renderPlaylist(data);
      else renderMedia(data);

      $("empty-state").hidden = true;
    } catch (error) {
      setUrlError(error.message);
      $("media-card").hidden = true;
      $("playlist-card").hidden = true;
    } finally {
      setAnalyzing(false);
    }
  }

  /* ─────────────────────────── single media ─────────────────────────── */

  function availableModes(media) {
    if (media.platform === "instagram") {
      const modes = [];
      if (media.has_video) modes.push("video", "audio");
      modes.push("photo", "thumbnail");
      return modes;
    }
    return ["video", "audio"];
  }

  function renderMedia(media) {
    state.media = media;
    state.playlist = null;
    $("playlist-card").hidden = true;

    const thumb = $("media-thumb");
    thumb.innerHTML = "";
    if (media.thumbnail) {
      const image = new Image();
      image.src = media.thumbnail;
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.onerror = () => { thumb.innerHTML = '<div class="thumb-fallback">▶</div>'; };
      thumb.appendChild(image);
    } else {
      thumb.appendChild(el("div", "thumb-fallback", "▶"));
    }

    $("media-title").textContent = media.title;
    $("media-sub").textContent = media.uploader || "";

    const chips = $("media-chips");
    chips.innerHTML = "";
    chips.appendChild(el("span", "chip chip-accent",
      media.platform === "instagram" ? "Instagram" : "YouTube"));
    if (media.duration_text) chips.appendChild(el("span", "chip", media.duration_text));
    if (media.filesize_text) chips.appendChild(el("span", "chip", `~${media.filesize_text}`));

    const modes = availableModes(media);
    state.mode = modes.includes(state.mode) ? state.mode : modes[0];
    renderSegmented($("mode-group"), modes, state.mode, (value) => {
      state.mode = value;
      refreshOptionVisibility();
    });

    const qualitySelect = $("quality-select");
    qualitySelect.innerHTML = "";
    (media.qualities || []).forEach((option) => {
      const node = el("option", null, option.label);
      node.value = option.id;
      qualitySelect.appendChild(node);
    });
    state.quality = media.qualities?.[0]?.id || "best";
    qualitySelect.value = state.quality;

    const subtitleSelect = $("subtitle-select");
    subtitleSelect.innerHTML = "";
    (media.subtitles || []).forEach((option) => {
      const node = el("option", null, option.label);
      node.value = option.code;
      subtitleSelect.appendChild(node);
    });
    if (media.subtitles?.length) {
      const preferred = media.subtitles.find((s) => s.code === state.settings.subtitle_lang);
      subtitleSelect.value = (preferred || media.subtitles[0]).code;
    }
    $("subtitle-toggle").checked = false;
    subtitleSelect.disabled = true;

    refreshOptionVisibility();
    updateDestination();
    $("media-card").hidden = false;
  }

  function refreshOptionVisibility() {
    const media = state.media;
    if (!media) return;

    const hasQualities = state.mode === "video" && (media.qualities || []).length > 0;
    $("quality-block").hidden = !hasQualities;

    const hasSubtitles = state.mode === "video"
      && media.platform === "youtube"
      && (media.subtitles || []).length > 0;
    $("subtitle-block").hidden = !hasSubtitles;
  }

  function renderSegmented(container, values, active, onSelect) {
    container.innerHTML = "";
    values.forEach((value) => {
      const button = el("button", `seg${value === active ? " active" : ""}`,
        MODE_LABELS[value] || value);
      button.type = "button";
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", String(value === active));
      button.addEventListener("click", () => {
        container.querySelectorAll(".seg").forEach((node) => {
          node.classList.remove("active");
          node.setAttribute("aria-checked", "false");
        });
        button.classList.add("active");
        button.setAttribute("aria-checked", "true");
        onSelect(value);
      });
      container.appendChild(button);
    });
  }

  function updateDestination() {
    const short = shortenPath(state.destination);

    const node = $("dest-path");
    node.textContent = short;
    node.title = state.destination;

    const chip = $("titlebar-dest");
    chip.textContent = short;
    chip.parentElement.title = state.destination;
  }

  async function startDownload() {
    if (!state.media) return;

    const payload = {
      url: state.media.url,
      mode: state.mode,
      quality: $("quality-select").value || "best",
      outdir: state.destination,
      title: state.media.title,
      thumbnail: state.media.thumbnail,
      subtitles: $("subtitle-toggle").checked && !$("subtitle-block").hidden,
      subtitle_lang: $("subtitle-select").value || "en",
    };

    const button = $("download-btn");
    button.disabled = true;
    try {
      await api("/api/download", payload);
      toast("Navbatga qo'shildi");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  /* ─────────────────────────── playlist ─────────────────────────── */

  function renderPlaylist(playlist) {
    state.playlist = playlist;
    state.media = null;
    $("media-card").hidden = true;

    $("playlist-title").textContent = playlist.title;
    $("playlist-sub").textContent =
      `${playlist.count} ta video${playlist.uploader ? ` · ${playlist.uploader}` : ""}`;

    const list = $("playlist-list");
    list.innerHTML = "";
    playlist.entries.forEach((entry) => {
      const row = el("div", "playlist-item");

      const checkbox = el("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.dataset.index = String(entry.index);
      checkbox.addEventListener("change", updatePlaylistCount);

      row.appendChild(checkbox);
      row.appendChild(el("span", "pl-index", String(entry.index + 1)));
      row.appendChild(el("span", "pl-title", entry.title));
      row.appendChild(el("span", "pl-duration", entry.duration_text || ""));
      list.appendChild(row);
    });

    renderSegmented($("playlist-mode-group"), ["video", "audio"], state.playlistMode, (value) => {
      state.playlistMode = value;
      $("playlist-quality").disabled = value === "audio";
    });
    $("playlist-quality").disabled = state.playlistMode === "audio";

    $("select-all").checked = true;
    updatePlaylistCount();
    $("playlist-card").hidden = false;
  }

  function selectedEntries() {
    if (!state.playlist) return [];
    const checked = [...$("playlist-list").querySelectorAll('input[type="checkbox"]:checked')];
    const indices = new Set(checked.map((node) => Number(node.dataset.index)));
    return state.playlist.entries.filter((entry) => indices.has(entry.index));
  }

  function updatePlaylistCount() {
    const count = selectedEntries().length;
    $("playlist-download-label").textContent =
      count ? `${count} ta videoni yuklash` : "Video tanlang";
    $("playlist-download-btn").disabled = count === 0;

    const total = state.playlist?.entries.length || 0;
    $("select-all").checked = count === total && total > 0;
    $("select-all").indeterminate = count > 0 && count < total;
  }

  async function downloadPlaylist() {
    const entries = selectedEntries();
    if (!entries.length) return;

    const button = $("playlist-download-btn");
    button.disabled = true;

    try {
      await api("/api/download/batch", {
        mode: state.playlistMode,
        quality: $("playlist-quality").value || "best",
        outdir: state.settings.youtube_dir,
        items: entries.map((entry) => ({
          url: entry.url,
          title: entry.title,
          thumbnail: entry.thumbnail,
        })),
      });
      toast(`${entries.length} ta video navbatga qo'shildi`);
    } catch (error) {
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      updatePlaylistCount();
    }
  }

  /* ─────────────────────────── jobs list ─────────────────────────── */

  function upsertJob(job) {
    state.jobs.set(job.id, job);

    let node = state.jobNodes.get(job.id);
    if (!node) {
      node = buildJobNode(job);
      state.jobNodes.set(job.id, node);
      $("jobs-list").prepend(node);
    }
    paintJob(node, job);
  }

  function buildJobNode(job) {
    const node = el("div", "job");
    node.dataset.id = job.id;

    const thumb = el("div", "job-thumb");
    if (job.thumbnail) {
      const image = new Image();
      image.src = job.thumbnail;
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.onerror = () => { thumb.innerHTML = ""; };
      thumb.appendChild(image);
    }

    const body = el("div", "job-body");
    body.appendChild(el("div", "job-title"));

    const progress = el("div", "progress");
    progress.appendChild(el("div", "progress-fill"));
    body.appendChild(progress);

    const stats = el("div", "job-stats");
    stats.appendChild(el("span", "job-state"));
    stats.appendChild(el("span", "job-percent"));
    stats.appendChild(el("span", "job-speed"));
    stats.appendChild(el("span", "job-eta"));
    body.appendChild(stats);

    const actions = el("div", "job-actions");

    const revealBtn = el("button", "icon-btn job-reveal");
    revealBtn.title = "Finder'da ko'rsatish";
    revealBtn.innerHTML =
      '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>';
    revealBtn.addEventListener("click", () => {
      const current = state.jobs.get(job.id);
      if (current?.file_path) api("/api/reveal", { path: current.file_path }).catch(() => {});
    });

    const cancelBtn = el("button", "icon-btn job-cancel");
    cancelBtn.title = "To'xtatish";
    cancelBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    cancelBtn.addEventListener("click", () => {
      api("/api/jobs/cancel", { id: job.id }).catch(() => {});
    });

    actions.appendChild(revealBtn);
    actions.appendChild(cancelBtn);

    node.appendChild(thumb);
    node.appendChild(body);
    node.appendChild(actions);
    return node;
  }

  function paintJob(node, job) {
    node.dataset.status = job.status;
    node.querySelector(".job-title").textContent = job.title || job.url;
    node.querySelector(".progress-fill").style.width = `${Math.round(job.percent * 100)}%`;

    node.querySelector(".job-state").textContent =
      job.status === "error" ? (job.error || "Xatolik") : STATE_LABELS[job.status];

    const running = job.status === "running";
    node.querySelector(".job-percent").textContent =
      running ? `${Math.round(job.percent * 100)}%` : (job.size_text || "");
    node.querySelector(".job-speed").textContent = running ? job.speed_text : "";
    node.querySelector(".job-eta").textContent =
      running && job.eta_text ? `${job.eta_text} qoldi` : "";

    const finished = ["completed", "error", "cancelled"].includes(job.status);
    node.querySelector(".job-cancel").hidden = finished;
    node.querySelector(".job-reveal").hidden = !(job.status === "completed" && job.file_path);
  }

  function renderJobsVisibility() {
    const ids = new Set(state.jobs.keys());
    state.jobNodes.forEach((node, id) => {
      if (!ids.has(id)) {
        node.remove();
        state.jobNodes.delete(id);
      }
    });

    const count = state.jobs.size;
    $("jobs-card").hidden = count === 0;
    $("jobs-counter").textContent = count ? String(count) : "";
    if (count) $("empty-state").hidden = true;
  }

  async function refreshJobs() {
    const data = await api("/api/jobs");
    state.jobs.clear();
    (data.jobs || []).forEach(upsertJob);
    renderJobsVisibility();
  }

  /* ─────────────────────────── settings ─────────────────────────── */

  function openSettings() { $("settings-modal").hidden = false; }
  function closeSettings() { $("settings-modal").hidden = true; }

  async function chooseFolder(key) {
    const { path } = await api("/api/choose-folder", { initial: state.settings[key] });
    if (!path) return;

    const { settings } = await api("/api/settings", { [key]: path });
    state.settings = settings;
    renderSettings();

    const platform = state.media?.platform;
    if ((key === "youtube_dir" && platform !== "instagram")
        || (key === "instagram_dir" && platform === "instagram")) {
      state.destination = path;
      updateDestination();
    }
    toast("Papka yangilandi");
  }

  /* ─────────────────────────── wiring ─────────────────────────── */

  function bindEvents() {
    const urlInput = $("url-input");

    urlInput.addEventListener("input", () => {
      const platform = detectPlatform(urlInput.value.trim());
      document.body.dataset.platform = platform === "none" ? "" : platform;
      $("platform-badge").dataset.platform = platform;
      setUrlError("");
    });

    urlInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") analyze();
    });

    $("analyze-btn").addEventListener("click", analyze);
    $("download-btn").addEventListener("click", startDownload);
    $("playlist-download-btn").addEventListener("click", downloadPlaylist);

    $("paste-btn").addEventListener("click", async () => {
      try {
        const { text } = await api("/api/clipboard");
        if (text) {
          urlInput.value = text;
          urlInput.dispatchEvent(new Event("input"));
          analyze();
        }
      } catch { /* clipboard is best-effort */ }
    });

    $("quality-select").addEventListener("change", (event) => {
      state.quality = event.target.value;
    });

    $("subtitle-toggle").addEventListener("change", (event) => {
      $("subtitle-select").disabled = !event.target.checked;
    });

    $("change-dir-btn").addEventListener("click", () => {
      chooseFolder(state.media?.platform === "instagram" ? "instagram_dir" : "youtube_dir")
        .catch((error) => toast(error.message, "error"));
    });

    $("select-all").addEventListener("change", (event) => {
      $("playlist-list").querySelectorAll('input[type="checkbox"]').forEach((node) => {
        node.checked = event.target.checked;
      });
      updatePlaylistCount();
    });

    $("cancel-all-btn").addEventListener("click", () => {
      api("/api/jobs/cancel-all", {}).catch(() => {});
    });

    $("clear-jobs-btn").addEventListener("click", async () => {
      try {
        await api("/api/jobs/clear", {});
        await refreshJobs();
      } catch (error) {
        toast(error.message, "error");
      }
    });

    $("open-folder-btn").addEventListener("click", () => {
      api("/api/open-folder", { path: state.destination || state.settings.youtube_dir })
        .catch(() => {});
    });

    $("ffmpeg-recheck").addEventListener("click", async () => {
      applyFfmpeg(await api("/api/ffmpeg"));
      toast(state.ffmpeg.available ? "FFmpeg topildi" : "FFmpeg hali topilmadi",
            state.ffmpeg.available ? "success" : "error");
    });

    $("settings-btn").addEventListener("click", openSettings);
    $("settings-close").addEventListener("click", closeSettings);
    $("settings-modal").addEventListener("click", (event) => {
      if (event.target === $("settings-modal")) closeSettings();
    });

    document.querySelectorAll("[data-choose]").forEach((button) => {
      button.addEventListener("click", () => {
        chooseFolder(button.dataset.choose).catch((error) => toast(error.message, "error"));
      });
    });

    $("setting-parallel").addEventListener("change", async (event) => {
      const { settings } = await api("/api/settings",
        { max_parallel: Number(event.target.value) });
      state.settings = settings;
    });

    document.addEventListener("keydown", (event) => {
      const meta = event.metaKey || event.ctrlKey;
      if (event.key === "Escape") {
        closeSettings();
      } else if (meta && event.key.toLowerCase() === "d") {
        event.preventDefault();
        if (state.media) startDownload();
        else if (state.playlist) downloadPlaylist();
      } else if (meta && event.key.toLowerCase() === "l") {
        event.preventDefault();
        urlInput.focus();
        urlInput.select();
      }
    });
  }

  /* ─────────────────────────── start ─────────────────────────── */

  bindEvents();
  connectEvents();
  bootstrap().catch((error) => toast(`Ishga tushirishda xatolik: ${error.message}`, "error"));
})();
