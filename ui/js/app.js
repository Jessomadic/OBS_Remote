/**
 * app.js — OBS Remote main application
 *
 * Responsibilities:
 *  - Bootstrap on DOMContentLoaded
 *  - Check /api/status and show connection modal if needed
 *  - Maintain WebSocket connection with auto-reconnect
 *  - Tab switching and per-tab polling
 *  - All UI rendering for every tab
 */

(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  const state = {
    obsConnected: false,
    currentScene: null,
    currentCollection: null,
    activeTab: 'scenes',
    streamActive: false,
    recordActive: false,
    recordPaused: false,
    studioEnabled: false,
    studioPreviewScene: null,
    vcamActive: false,
    replayActive: false,
    // Track poll interval IDs so we can cancel them when switching tabs
    pollIntervals: {},
    ws: null,
    wsReconnectTimer: null,
    wsReconnectDelay: 2000,
  };

  // -------------------------------------------------------------------------
  // DOM helpers
  // -------------------------------------------------------------------------
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  function el(tag, attrs = {}, ...children) {
    const elem = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') elem.className = v;
      else if (k.startsWith('on')) elem.addEventListener(k.slice(2), v);
      else elem.setAttribute(k, v);
    }
    for (const child of children) {
      if (typeof child === 'string') elem.appendChild(document.createTextNode(child));
      else if (child) elem.appendChild(child);
    }
    return elem;
  }

  // -------------------------------------------------------------------------
  // Toast notifications
  // -------------------------------------------------------------------------
  const toastContainer = document.getElementById('toast-container');

  /**
   * Show a toast notification.
   * @param {string} message
   * @param {'info'|'success'|'error'} [type]
   * @param {number} [duration]  ms before auto-dismiss
   */
  function showToast(message, type = 'info', duration = 4000) {
    const icons = {
      info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
      success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
      error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `${icons[type] || ''}<span>${message}</span>`;
    toastContainer.appendChild(toast);

    const dismiss = () => {
      toast.classList.add('removing');
      toast.addEventListener('animationend', () => toast.remove(), { once: true });
    };

    const timer = setTimeout(dismiss, duration);
    toast.addEventListener('click', () => { clearTimeout(timer); dismiss(); });
  }

  // -------------------------------------------------------------------------
  // Button loading helper — disables btn, adds .loading class, re-enables after
  // -------------------------------------------------------------------------
  async function withBtnLoading(btn, fn) {
    btn.disabled = true;
    btn.classList.add('loading');
    try {
      await fn();
    } finally {
      btn.disabled = false;
      btn.classList.remove('loading');
    }
  }

  // -------------------------------------------------------------------------
  // Connection status bar
  // -------------------------------------------------------------------------
  const statusDot = document.getElementById('status-dot');
  const statusLabel = document.getElementById('status-label');
  const versionBadge = document.getElementById('version-badge');

  function setConnectionUI(connected, version) {
    state.obsConnected = connected;
    if (connected) {
      statusDot.className = 'status-dot connected';
      statusLabel.textContent = 'Connected';
    } else {
      statusDot.className = 'status-dot disconnected';
      statusLabel.textContent = 'Disconnected';
    }
    if (version) versionBadge.textContent = `v${version}`;
  }

  // -------------------------------------------------------------------------
  // Connection Modal
  // -------------------------------------------------------------------------
  const connectionModal = document.getElementById('connection-modal');
  const connectBtn = document.getElementById('connect-btn');
  const modalError = document.getElementById('modal-error');

  function showModalError(msg) {
    modalError.textContent = msg;
    modalError.classList.add('visible');
  }
  function clearModalError() {
    modalError.textContent = '';
    modalError.classList.remove('visible');
  }

  function setConnectBtnLoading(loading) {
    connectBtn.classList.toggle('loading', loading);
    connectBtn.disabled = loading;
  }

  connectBtn.addEventListener('click', async () => {
    const host = $('#obs-host').value.trim() || 'localhost';
    const port = parseInt($('#obs-port').value, 10) || 4455;
    const password = $('#obs-password').value;

    clearModalError();
    setConnectBtnLoading(true);

    try {
      await api.connect(host, port, password);
      connectionModal.classList.add('hidden');
      await initApp();
    } catch (err) {
      showModalError(err.message || 'Connection failed. Check host/port/password.');
    } finally {
      setConnectBtnLoading(false);
    }
  });

  // Allow pressing Enter in modal inputs to trigger connect
  ['obs-host', 'obs-port', 'obs-password'].forEach(id => {
    document.getElementById(id).addEventListener('keydown', e => {
      if (e.key === 'Enter') connectBtn.click();
    });
  });

  // -------------------------------------------------------------------------
  // Settings Modal
  // -------------------------------------------------------------------------
  const settingsModal = document.getElementById('settings-modal');
  const settingsBtn = document.getElementById('settings-btn');
  const settingsCloseBtn = document.getElementById('settings-close-btn');
  const settingsCancelBtn = document.getElementById('settings-cancel-btn');
  const settingsConnectBtn = document.getElementById('settings-connect-btn');
  const settingsError = document.getElementById('settings-error');

  function showSettingsError(msg) {
    settingsError.textContent = msg;
    settingsError.classList.add('visible');
  }
  function clearSettingsError() {
    settingsError.textContent = '';
    settingsError.classList.remove('visible');
  }

  settingsBtn.addEventListener('click', () => {
    settingsModal.classList.remove('hidden');
    clearSettingsError();
  });

  function closeSettings() {
    settingsModal.classList.add('hidden');
  }

  settingsCloseBtn.addEventListener('click', closeSettings);
  settingsCancelBtn.addEventListener('click', closeSettings);
  settingsModal.addEventListener('click', e => {
    if (e.target === settingsModal) closeSettings();
  });

  settingsConnectBtn.addEventListener('click', async () => {
    const host = $('#settings-host').value.trim() || 'localhost';
    const port = parseInt($('#settings-port').value, 10) || 4455;
    const password = $('#settings-password').value;

    clearSettingsError();
    settingsConnectBtn.disabled = true;
    settingsConnectBtn.textContent = 'Connecting...';

    try {
      await api.connect(host, port, password);
      closeSettings();
      showToast('Reconnected to OBS', 'success');
      await refreshStatus();
    } catch (err) {
      showSettingsError(err.message || 'Connection failed.');
    } finally {
      settingsConnectBtn.disabled = false;
      settingsConnectBtn.textContent = 'Reconnect';
    }
  });

  // -------------------------------------------------------------------------
  // Tab Navigation
  // -------------------------------------------------------------------------
  const tabButtons = $$('.tab-btn');
  const tabPanels = $$('.tab-panel');

  function switchTab(tabName) {
    if (state.activeTab === tabName) return;

    // Stop polling for the old tab
    stopTabPolling(state.activeTab);

    state.activeTab = tabName;

    tabButtons.forEach(btn => {
      const isActive = btn.dataset.tab === tabName;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', String(isActive));
    });

    tabPanels.forEach(panel => {
      const isActive = panel.id === `tab-${tabName}`;
      panel.classList.toggle('active', isActive);
      panel.hidden = !isActive;
    });

    // Start polling / refresh for the newly active tab
    startTabActivity(tabName);
  }

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  function stopTabPolling(tabName) {
    const id = state.pollIntervals[tabName];
    if (id) {
      clearInterval(id);
      delete state.pollIntervals[tabName];
    }
  }

  function stopAllPolling() {
    Object.keys(state.pollIntervals).forEach(stopTabPolling);
  }

  async function startTabActivity(tabName) {
    switch (tabName) {
      case 'scenes':   await loadScenes(); break;
      case 'audio':    await loadAudio(); startAudioPolling(); break;
      case 'stream':   await loadStreamStatus(); startStreamPolling(); break;
      case 'sources':  await loadSourcesSceneList(); break;
      case 'studio':   await loadStudio(); break;
      case 'stats':    await loadStats(); startStatsPolling(); break;
    }
  }

  function startAudioPolling() {
    state.pollIntervals.audio = setInterval(async () => {
      if (state.activeTab === 'audio' && state.obsConnected) {
        await loadAudio(true);
      }
    }, 3000);
  }

  function startStreamPolling() {
    state.pollIntervals.stream = setInterval(async () => {
      if (state.activeTab === 'stream' && state.obsConnected) {
        await loadStreamStatus();
      }
    }, 2000);
  }

  function startStatsPolling() {
    state.pollIntervals.stats = setInterval(async () => {
      if (state.activeTab === 'stats' && state.obsConnected) {
        await loadStats();
      }
    }, 2000);
  }

  // -------------------------------------------------------------------------
  // WebSocket
  // -------------------------------------------------------------------------
  function connectWebSocket() {
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const wsUrl = `ws://${location.host}/ws`;
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (err) {
      scheduleWsReconnect();
      return;
    }

    state.ws = ws;

    ws.addEventListener('open', () => {
      state.wsReconnectDelay = 2000; // Reset backoff
    });

    ws.addEventListener('message', e => {
      let msg;
      try {
        msg = JSON.parse(e.data);
      } catch (_) {
        return;
      }
      handleWsEvent(msg);
    });

    ws.addEventListener('close', () => {
      scheduleWsReconnect();
    });

    ws.addEventListener('error', () => {
      // error is always followed by close; handle there
    });
  }

  function scheduleWsReconnect() {
    if (state.wsReconnectTimer) return;
    state.wsReconnectTimer = setTimeout(() => {
      state.wsReconnectTimer = null;
      // Exponential back-off, cap at 30s
      state.wsReconnectDelay = Math.min(state.wsReconnectDelay * 1.5, 30000);
      connectWebSocket();
    }, state.wsReconnectDelay);
  }

  function handleWsEvent({ event, data }) {
    if (!event || !data) return;

    switch (event) {
      case 'connected':
        setConnectionUI(data.obs_connected);
        if (data.obs_connected && !state.obsConnected) {
          showToast('OBS connected', 'success');
          startTabActivity(state.activeTab);
        } else if (!data.obs_connected && state.obsConnected) {
          showToast('OBS disconnected', 'error');
          stopAllPolling();
        }
        break;

      case 'scene_changed':
        state.currentScene = data.scene;
        updateActiveScenesUI(data.scene);
        // Update studio program if relevant
        const progEl = document.getElementById('studio-program-scene');
        if (progEl) progEl.textContent = data.scene || '—';
        break;

      case 'stream_state':
        state.streamActive = data.active;
        updateStreamUI();
        break;

      case 'record_state':
        state.recordActive = data.active;
        if (data.state === 'paused') state.recordPaused = true;
        else state.recordPaused = false;
        updateRecordUI();
        break;

      case 'volume_changed': {
        // Update the slider and dB display for this input without full reload
        const db = data.db;
        const inputName = data.input;
        const card = document.querySelector(`[data-input-name="${CSS.escape(inputName)}"]`);
        if (card) {
          const slider = card.querySelector('.volume-slider');
          const dbDisplay = card.querySelector('.audio-db-value');
          const vuBar = card.querySelector('.vu-bar');
          if (slider) slider.value = db;
          if (dbDisplay) dbDisplay.textContent = `${db.toFixed(1)} dB`;
          if (vuBar) vuBar.style.width = dbToPercent(db) + '%';
        }
        break;
      }

      case 'mute_changed': {
        const card2 = document.querySelector(`[data-input-name="${CSS.escape(data.input)}"]`);
        if (card2) {
          const muteBtn = card2.querySelector('.mute-btn');
          if (muteBtn) setMuteBtnState(muteBtn, data.muted);
        }
        break;
      }

      case 'source_visibility': {
        const row = document.querySelector(`[data-source-item-id="${data.item_id}"]`);
        if (row) {
          const visBtn = row.querySelector('.source-vis-btn');
          if (visBtn) setVisBtnState(visBtn, data.enabled);
          row.classList.toggle('disabled', !data.enabled);
        }
        break;
      }

      case 'studio_mode':
        state.studioEnabled = data.enabled;
        if (state.activeTab === 'studio') renderStudioMode(data.enabled);
        break;

      case 'filter_changed':
        // Handled inline if filter list is visible; no full reload needed
        break;

      default:
        break;
    }
  }

  // -------------------------------------------------------------------------
  // Status refresh
  // -------------------------------------------------------------------------
  async function refreshStatus() {
    try {
      const status = await api.getStatus();
      setConnectionUI(status.obs_connected, status.version);

      if (status.update_available) {
        showUpdateBadge();
      }

      // Populate settings modal fields with current values
      const settingsHost = document.getElementById('settings-host');
      const settingsPort = document.getElementById('settings-port');
      if (settingsHost && status.obs_host) settingsHost.value = status.obs_host;
      if (settingsPort && status.obs_port) settingsPort.value = status.obs_port;

      return status;
    } catch (err) {
      setConnectionUI(false);
      return { obs_connected: false };
    }
  }

  function showUpdateBadge() {
    const versionWrap = versionBadge.parentElement;
    if (versionWrap.querySelector('.update-badge')) return;
    const badge = document.createElement('span');
    badge.className = 'update-badge';
    badge.textContent = 'Update available';
    badge.title = 'A newer version of OBS Remote is available';
    versionWrap.insertBefore(badge, versionBadge.nextSibling);
  }

  // -------------------------------------------------------------------------
  // Bootstrap
  // -------------------------------------------------------------------------
  async function boot() {
    const status = await refreshStatus();

    // Always fill the form fields with latest config just in case they open Settings
    if (status.obs_host) $('#obs-host').value = status.obs_host;
    if (status.obs_port) $('#obs-port').value = status.obs_port;
    if (status.obs_host) $('#settings-host').value = status.obs_host;
    if (status.obs_port) $('#settings-port').value = status.obs_port;

    if (!status.obs_connected) {
      // Show connect modal
      connectionModal.classList.remove('hidden');
    } else {
      connectionModal.classList.add('hidden');
      await initApp();
    }
  }

  async function initApp() {
    // Re-check status in case it changed
    await refreshStatus();

    // Start WebSocket
    connectWebSocket();

    // Load the default tab
    await startTabActivity(state.activeTab);
  }

  // -------------------------------------------------------------------------
  // ===  SCENES TAB  ===
  // -------------------------------------------------------------------------
  const scenesGrid = document.getElementById('scenes-grid');
  const collectionSelect = document.getElementById('collection-select');

  async function loadScenes() {
    if (!state.obsConnected) {
      scenesGrid.innerHTML = '<div class="empty-state"><span>Not connected to OBS</span></div>';
      return;
    }

    scenesGrid.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading scenes...</span></div>';

    try {
      const [scenesData, collectionsData] = await Promise.all([
        api.getScenes(),
        api.getCollections(),
      ]);

      state.currentScene = scenesData.current;
      state.currentCollection = collectionsData.current;

      renderScenes(scenesData.scenes, scenesData.current);
      renderCollections(collectionsData.collections, collectionsData.current);
    } catch (err) {
      scenesGrid.innerHTML = `<div class="empty-state"><span>Failed to load scenes: ${err.message}</span></div>`;
      showToast(`Failed to load scenes: ${err.message}`, 'error');
    }
  }

  function renderScenes(scenes, current) {
    if (!scenes || scenes.length === 0) {
      scenesGrid.innerHTML = '<div class="empty-state"><span>No scenes found</span></div>';
      return;
    }

    scenesGrid.innerHTML = '';
    for (const name of scenes) {
      const btn = document.createElement('button');
      btn.className = 'scene-btn' + (name === current ? ' active' : '');
      btn.textContent = name;
      btn.addEventListener('click', () => {
        if (name === state.currentScene) return;
        withBtnLoading(btn, async () => {
          try {
            await api.setScene(name);
            state.currentScene = name;
            updateActiveScenesUI(name);
          } catch (err) {
            showToast(`Failed to switch scene: ${err.message}`, 'error');
          }
        });
      });
      scenesGrid.appendChild(btn);
    }
  }

  function updateActiveScenesUI(current) {
    state.currentScene = current;
    $$('.scene-btn', scenesGrid).forEach(btn => {
      btn.classList.toggle('active', btn.textContent === current);
    });
  }

  function renderCollections(collections, current) {
    collectionSelect.innerHTML = '';
    for (const name of collections) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      opt.selected = name === current;
      collectionSelect.appendChild(opt);
    }
  }

  collectionSelect.addEventListener('change', async () => {
    const name = collectionSelect.value;
    if (!name || name === state.currentCollection) return;
    try {
      await api.setCollection(name);
      state.currentCollection = name;
      showToast(`Switched to collection: ${name}`, 'success');
      // Scenes will change; reload after brief delay for OBS to update
      setTimeout(() => loadScenes(), 800);
    } catch (err) {
      showToast(`Failed to switch collection: ${err.message}`, 'error');
    }
  });

  // -------------------------------------------------------------------------
  // ===  AUDIO TAB  ===
  // -------------------------------------------------------------------------
  const audioGrid = document.getElementById('audio-grid');
  const audioRefreshBtn = document.getElementById('audio-refresh-btn');

  // Convert dB (-60 to 0) to a 0-100 percentage for UI bars
  function dbToPercent(db) {
    const clamped = Math.max(-60, Math.min(0, db));
    return Math.round(((clamped + 60) / 60) * 100);
  }

  async function loadAudio(silent = false) {
    if (!state.obsConnected) {
      if (!silent) audioGrid.innerHTML = '<div class="empty-state"><span>Not connected to OBS</span></div>';
      return;
    }

    if (!silent) {
      audioGrid.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading audio inputs...</span></div>';
    }

    try {
      const data = await api.getAudio();
      renderAudioInputs(data.inputs || []);
    } catch (err) {
      if (!silent) {
        audioGrid.innerHTML = `<div class="empty-state"><span>Failed to load audio: ${err.message}</span></div>`;
      }
      if (!silent) showToast(`Audio error: ${err.message}`, 'error');
    }
  }

  function renderAudioInputs(inputs) {
    if (inputs.length === 0) {
      audioGrid.innerHTML = '<div class="empty-state"><span>No audio inputs found</span></div>';
      return;
    }

    // Update existing cards instead of full re-render when possible
    const existingNames = new Set(
      $$('.audio-card', audioGrid).map(c => c.dataset.inputName)
    );
    const newNames = new Set(inputs.map(i => i.name));
    const needsFullRender = [...newNames].some(n => !existingNames.has(n)) ||
                            existingNames.size !== newNames.size;

    if (needsFullRender) {
      audioGrid.innerHTML = '';
      for (const input of inputs) {
        audioGrid.appendChild(createAudioCard(input));
      }
    } else {
      // Just update values
      for (const input of inputs) {
        const card = audioGrid.querySelector(`[data-input-name="${CSS.escape(input.name)}"]`);
        if (!card) continue;
        const slider = card.querySelector('.volume-slider');
        const dbDisplay = card.querySelector('.audio-db-value');
        const vuBar = card.querySelector('.vu-bar');
        const muteBtn = card.querySelector('.mute-btn');
        if (slider) slider.value = input.volume_db;
        if (dbDisplay) dbDisplay.textContent = `${input.volume_db.toFixed(1)} dB`;
        if (vuBar) vuBar.style.width = dbToPercent(input.volume_db) + '%';
        if (muteBtn) setMuteBtnState(muteBtn, input.muted);
      }
    }
  }

  function createAudioCard(input) {
    const db = typeof input.volume_db === 'number' ? input.volume_db : -60;
    const pct = dbToPercent(db);

    const card = document.createElement('div');
    card.className = 'audio-card';
    card.dataset.inputName = input.name;

    // Header
    const header = document.createElement('div');
    header.className = 'audio-card-header';

    const info = document.createElement('div');
    const nameEl = document.createElement('div');
    nameEl.className = 'audio-input-name';
    nameEl.textContent = input.name;
    const kindEl = document.createElement('div');
    kindEl.className = 'audio-input-kind';
    kindEl.textContent = input.kind || '';
    info.appendChild(nameEl);
    info.appendChild(kindEl);

    const muteBtn = document.createElement('button');
    muteBtn.className = 'mute-btn';
    muteBtn.setAttribute('aria-label', input.muted ? 'Unmute' : 'Mute');
    setMuteBtnState(muteBtn, input.muted);
    muteBtn.addEventListener('click', () => withBtnLoading(muteBtn, async () => {
      try {
        await api.toggleMute(input.name);
        // Optimistic toggle
        const nowMuted = !muteBtn.classList.contains('muted');
        setMuteBtnState(muteBtn, nowMuted);
      } catch (err) {
        showToast(`Mute error: ${err.message}`, 'error');
      }
    }));

    header.appendChild(info);
    header.appendChild(muteBtn);

    // Slider section
    const sliderRow = document.createElement('div');
    sliderRow.className = 'audio-slider-row';

    const sliderHeader = document.createElement('div');
    sliderHeader.className = 'audio-slider-header';

    const sliderLabel = document.createElement('span');
    sliderLabel.className = 'audio-slider-label';
    sliderLabel.textContent = 'Volume';

    const dbDisplay = document.createElement('span');
    dbDisplay.className = 'audio-db-value';
    dbDisplay.textContent = `${db.toFixed(1)} dB`;

    sliderHeader.appendChild(sliderLabel);
    sliderHeader.appendChild(dbDisplay);

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.className = 'volume-slider';
    slider.min = '-60';
    slider.max = '0';
    slider.step = '0.5';
    slider.value = String(db);

    let debounceTimer = null;
    slider.addEventListener('input', () => {
      const val = parseFloat(slider.value);
      dbDisplay.textContent = `${val.toFixed(1)} dB`;
      vuBar.style.width = dbToPercent(val) + '%';
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(async () => {
        try {
          await api.setVolume(input.name, val);
        } catch (err) {
          showToast(`Volume error: ${err.message}`, 'error');
        }
      }, 200);
    });

    // VU Meter
    const vuMeter = document.createElement('div');
    vuMeter.className = 'vu-meter';
    const vuBar = document.createElement('div');
    vuBar.className = 'vu-bar';
    vuBar.style.width = pct + '%';
    vuMeter.appendChild(vuBar);

    sliderRow.appendChild(sliderHeader);
    sliderRow.appendChild(slider);
    sliderRow.appendChild(vuMeter);

    card.appendChild(header);
    card.appendChild(sliderRow);

    return card;
  }

  function setMuteBtnState(btn, muted) {
    btn.classList.toggle('muted', muted);
    btn.setAttribute('aria-label', muted ? 'Unmute' : 'Mute');
    btn.innerHTML = muted
      ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <line x1="1" y1="1" x2="23" y2="23"/>
           <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/>
           <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/>
           <line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>
         </svg>`
      : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
           <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
           <line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>
         </svg>`;
  }

  audioRefreshBtn.addEventListener('click', () => loadAudio());

  // -------------------------------------------------------------------------
  // ===  STREAM TAB  ===
  // -------------------------------------------------------------------------
  const streamToggleBtn = document.getElementById('stream-toggle-btn');
  const streamToggleLabel = document.getElementById('stream-toggle-label');
  const streamStatusBadge = document.getElementById('stream-status-badge');
  const liveIndicator = document.getElementById('live-indicator');
  const streamTimerEl = document.getElementById('stream-timer');
  const streamCongestion = document.getElementById('stream-congestion');
  const streamDropped = document.getElementById('stream-dropped');
  const streamBytes = document.getElementById('stream-bytes');

  const recordToggleBtn = document.getElementById('record-toggle-btn');
  const recordToggleLabel = document.getElementById('record-toggle-label');
  const recordPauseBtn = document.getElementById('record-pause-btn');
  const recordPauseLabel = document.getElementById('record-pause-label');
  const recordStatusBadge = document.getElementById('record-status-badge');
  const recordTimerEl = document.getElementById('record-timer');

  const vcamToggleBtn = document.getElementById('vcam-toggle-btn');
  const replayToggleBtn = document.getElementById('replay-toggle-btn');
  const replaySaveBtn = document.getElementById('replay-save-btn');

  function formatBytes(bytes) {
    if (bytes === null || bytes === undefined) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function formatPercent(val) {
    if (val === null || val === undefined) return '—';
    return `${(val * 100).toFixed(1)}%`;
  }

  async function loadStreamStatus() {
    if (!state.obsConnected) return;
    try {
      const data = await api.getStreamingStatus();
      applyStreamStatus(data);
    } catch (err) {
      // Non-critical; silently fail during poll
    }
  }

  function applyStreamStatus(data) {
    const s = data.stream || {};
    const r = data.record || {};

    state.streamActive = s.active || false;
    state.recordActive = r.active || false;
    state.recordPaused = r.paused || false;

    updateStreamUI(s);
    updateRecordUI(r);
  }

  function updateStreamUI(s = {}) {
    const active = state.streamActive;
    streamToggleBtn.classList.toggle('live', active);
    streamToggleLabel.textContent = active ? 'END STREAM' : 'GO LIVE';
    streamStatusBadge.textContent = active ? 'LIVE' : 'OFFLINE';
    streamStatusBadge.className = 'status-badge' + (active ? ' live' : '');
    liveIndicator.classList.toggle('active', active);

    if (s.timecode) streamTimerEl.textContent = s.timecode;
    else if (!active) streamTimerEl.textContent = '00:00:00';

    if (s.congestion !== undefined) streamCongestion.textContent = formatPercent(s.congestion);
    if (s.skipped_frames !== undefined && s.total_frames) {
      const dropPct = s.total_frames > 0 ? (s.skipped_frames / s.total_frames * 100).toFixed(1) : '0.0';
      streamDropped.textContent = `${dropPct}%`;
    }
    if (s.bytes !== undefined) streamBytes.textContent = formatBytes(s.bytes);
  }

  function updateRecordUI(r = {}) {
    const active = state.recordActive;
    const paused = state.recordPaused;

    recordToggleBtn.classList.toggle('active-state', active);
    recordToggleLabel.textContent = active ? 'Stop' : 'Record';

    recordPauseBtn.disabled = !active;

    if (active && paused) {
      recordPauseLabel.textContent = 'Resume';
      recordStatusBadge.textContent = 'PAUSED';
      recordStatusBadge.className = 'status-badge paused';
    } else if (active) {
      recordPauseLabel.textContent = 'Pause';
      recordStatusBadge.textContent = 'REC';
      recordStatusBadge.className = 'status-badge recording';
    } else {
      recordPauseLabel.textContent = 'Pause';
      recordStatusBadge.textContent = 'STOPPED';
      recordStatusBadge.className = 'status-badge';
    }

    if (r.timecode) recordTimerEl.textContent = r.timecode;
    else if (!active) recordTimerEl.textContent = '00:00:00';
  }

  streamToggleBtn.addEventListener('click', () => withBtnLoading(streamToggleBtn, async () => {
    try {
      await api.toggleStream();
    } catch (err) {
      showToast(`Stream error: ${err.message}`, 'error');
    }
  }));

  recordToggleBtn.addEventListener('click', () => withBtnLoading(recordToggleBtn, async () => {
    try {
      await api.toggleRecord();
    } catch (err) {
      showToast(`Record error: ${err.message}`, 'error');
    }
  }));

  recordPauseBtn.addEventListener('click', () => withBtnLoading(recordPauseBtn, async () => {
    try {
      if (state.recordPaused) {
        await api.resumeRecord();
        state.recordPaused = false;
      } else {
        await api.pauseRecord();
        state.recordPaused = true;
      }
      updateRecordUI();
    } catch (err) {
      showToast(`Record pause error: ${err.message}`, 'error');
    }
  }));

  vcamToggleBtn.addEventListener('click', () => withBtnLoading(vcamToggleBtn, async () => {
    try {
      await api.toggleVirtualCam();
      state.vcamActive = !state.vcamActive;
      vcamToggleBtn.classList.toggle('active-state', state.vcamActive);
      showToast(state.vcamActive ? 'Virtual Camera started' : 'Virtual Camera stopped', 'info');
    } catch (err) {
      showToast(`Virtual Camera error: ${err.message}`, 'error');
    }
  }));

  replayToggleBtn.addEventListener('click', () => withBtnLoading(replayToggleBtn, async () => {
    try {
      await api.toggleReplayBuffer();
      state.replayActive = !state.replayActive;
      replayToggleBtn.classList.toggle('active-state', state.replayActive);
      showToast(state.replayActive ? 'Replay Buffer started' : 'Replay Buffer stopped', 'info');
    } catch (err) {
      showToast(`Replay Buffer error: ${err.message}`, 'error');
    }
  }));

  replaySaveBtn.addEventListener('click', () => withBtnLoading(replaySaveBtn, async () => {
    try {
      await api.saveReplay();
      showToast('Replay saved', 'success');
    } catch (err) {
      showToast(`Save replay error: ${err.message}`, 'error');
    }
  }));

  // -------------------------------------------------------------------------
  // ===  SOURCES TAB  ===
  // -------------------------------------------------------------------------
  const sourcesSceneSelect = document.getElementById('sources-scene-select');
  const sourcesList = document.getElementById('sources-list');

  let sourcesCurrentScene = null;

  async function loadSourcesSceneList() {
    if (!state.obsConnected) {
      sourcesSceneSelect.innerHTML = '<option value="">Not connected</option>';
      return;
    }

    try {
      const data = await api.getScenes();
      sourcesSceneSelect.innerHTML = '<option value="">Select scene...</option>';
      for (const name of data.scenes) {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        if (name === data.current) opt.selected = true;
        sourcesSceneSelect.appendChild(opt);
      }

      // Auto-load current scene sources
      if (data.current) {
        sourcesSceneSelect.value = data.current;
        sourcesCurrentScene = data.current;
        await loadSources(data.current);
      }
    } catch (err) {
      showToast(`Failed to load scenes: ${err.message}`, 'error');
    }
  }

  sourcesSceneSelect.addEventListener('change', async () => {
    const scene = sourcesSceneSelect.value;
    if (!scene) {
      sourcesList.innerHTML = '<div class="empty-state"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg><span>Select a scene to view its sources</span></div>';
      return;
    }
    sourcesCurrentScene = scene;
    await loadSources(scene);
  });

  async function loadSources(sceneName) {
    sourcesList.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Loading sources...</span></div>';
    try {
      const data = await api.getSources(sceneName);
      renderSources(data.sources || [], sceneName);
    } catch (err) {
      sourcesList.innerHTML = `<div class="empty-state"><span>Failed to load sources: ${err.message}</span></div>`;
      showToast(`Sources error: ${err.message}`, 'error');
    }
  }

  function renderSources(sources, sceneName) {
    if (sources.length === 0) {
      sourcesList.innerHTML = '<div class="empty-state"><span>No sources in this scene</span></div>';
      return;
    }

    sourcesList.innerHTML = '';
    for (const source of sources) {
      const item = document.createElement('div');
      item.className = 'source-item' + (source.enabled ? '' : ' disabled');
      item.dataset.sourceItemId = source.id;

      // Visibility toggle button
      const visBtn = document.createElement('button');
      visBtn.className = 'source-vis-btn';
      setVisBtnState(visBtn, source.enabled);
      visBtn.addEventListener('click', () => withBtnLoading(visBtn, async () => {
        const nowEnabled = !visBtn.classList.contains('visible');
        try {
          await api.setSourceVisibility(sceneName, source.id, nowEnabled);
          setVisBtnState(visBtn, nowEnabled);
          item.classList.toggle('disabled', !nowEnabled);
        } catch (err) {
          showToast(`Visibility error: ${err.message}`, 'error');
        }
      }));

      // Info
      const info = document.createElement('div');
      info.className = 'source-info';
      const nameEl = document.createElement('div');
      nameEl.className = 'source-name';
      nameEl.textContent = source.name;
      const kindEl = document.createElement('div');
      kindEl.className = 'source-kind';
      kindEl.textContent = source.kind || '';
      info.appendChild(nameEl);
      info.appendChild(kindEl);

      item.appendChild(visBtn);
      item.appendChild(info);
      sourcesList.appendChild(item);
    }
  }

  function setVisBtnState(btn, enabled) {
    btn.classList.toggle('visible', enabled);
    btn.setAttribute('aria-label', enabled ? 'Hide source' : 'Show source');
    btn.setAttribute('title', enabled ? 'Hide source' : 'Show source');
    btn.innerHTML = enabled
      ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
           <circle cx="12" cy="12" r="3"/>
         </svg>`
      : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
           <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
           <line x1="1" y1="1" x2="23" y2="23"/>
         </svg>`;
  }

  // -------------------------------------------------------------------------
  // ===  STUDIO TAB  ===
  // -------------------------------------------------------------------------
  const studioModeToggle = document.getElementById('studio-mode-toggle');
  const studioModeLabel = document.getElementById('studio-mode-label');
  const studioContent = document.getElementById('studio-content');
  const studioActiveContent = document.getElementById('studio-active-content');
  const studioCutBtn = document.getElementById('studio-cut-btn');
  const studioPreviewSelect = document.getElementById('studio-preview-select');
  const studioPreviewScene = document.getElementById('studio-preview-scene');
  const studioProgramScene = document.getElementById('studio-program-scene');

  async function loadStudio() {
    if (!state.obsConnected) return;
    try {
      const [studioData, scenesData] = await Promise.all([
        api.getStudio(),
        api.getScenes(),
      ]);

      state.studioEnabled = studioData.enabled;
      state.studioPreviewScene = studioData.preview_scene || null;
      state.currentScene = scenesData.current;

      // Populate preview scene select
      studioPreviewSelect.innerHTML = '<option value="">Select preview scene...</option>';
      for (const name of scenesData.scenes) {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        if (name === studioData.preview_scene) opt.selected = true;
        studioPreviewSelect.appendChild(opt);
      }

      studioModeToggle.checked = studioData.enabled;
      renderStudioMode(studioData.enabled);

      if (studioProgramScene) studioProgramScene.textContent = scenesData.current || '—';
      if (studioPreviewScene) studioPreviewScene.textContent = studioData.preview_scene || '—';
    } catch (err) {
      showToast(`Studio error: ${err.message}`, 'error');
    }
  }

  function renderStudioMode(enabled) {
    studioModeToggle.checked = enabled;
    studioModeLabel.textContent = enabled ? 'Enabled' : 'Disabled';
    if (enabled) {
      studioContent.classList.add('hidden');
      studioActiveContent.classList.remove('hidden');
    } else {
      studioContent.classList.remove('hidden');
      studioActiveContent.classList.add('hidden');
    }
  }

  studioModeToggle.addEventListener('change', async () => {
    try {
      await api.toggleStudio();
      state.studioEnabled = !state.studioEnabled;
      renderStudioMode(state.studioEnabled);
    } catch (err) {
      // Revert the checkbox
      studioModeToggle.checked = state.studioEnabled;
      showToast(`Studio mode error: ${err.message}`, 'error');
    }
  });

  studioCutBtn.addEventListener('click', () => withBtnLoading(studioCutBtn, async () => {
    try {
      await api.studioTransition();
      showToast('Transition triggered', 'success');
      // After transition, program becomes what was preview
      if (studioPreviewScene) {
        studioProgramScene.textContent = studioPreviewScene.textContent;
      }
    } catch (err) {
      showToast(`Transition error: ${err.message}`, 'error');
    }
  }));

  studioPreviewSelect.addEventListener('change', async () => {
    const scene = studioPreviewSelect.value;
    if (!scene) return;
    try {
      await api.setStudioPreview(scene);
      state.studioPreviewScene = scene;
      if (studioPreviewScene) studioPreviewScene.textContent = scene;
    } catch (err) {
      showToast(`Preview error: ${err.message}`, 'error');
    }
  });

  // -------------------------------------------------------------------------
  // ===  STATS TAB  ===
  // -------------------------------------------------------------------------
  const statEls = {
    cpu:        document.getElementById('stat-cpu'),
    cpuBar:     document.getElementById('stat-cpu-bar'),
    mem:        document.getElementById('stat-mem'),
    memBar:     document.getElementById('stat-mem-bar'),
    fps:        document.getElementById('stat-fps'),
    stream:     document.getElementById('stat-stream'),
    streamTime: document.getElementById('stat-stream-time'),
    record:     document.getElementById('stat-record'),
    recordTime: document.getElementById('stat-record-time'),
    dropped:    document.getElementById('stat-dropped'),
    droppedBar: document.getElementById('stat-dropped-bar'),
    congestion: document.getElementById('stat-congestion'),
    bytes:      document.getElementById('stat-bytes'),
  };

  async function loadStats() {
    if (!state.obsConnected) return;
    try {
      const s = await api.getStats();
      renderStats(s);
    } catch (_) { /* silently fail */ }
  }

  function renderStats(s) {
    const cpu = typeof s.cpu_usage === 'number' ? s.cpu_usage : null;
    const mem = typeof s.memory_usage === 'number' ? s.memory_usage : null;
    const fps = typeof s.active_fps === 'number' ? s.active_fps : null;

    if (statEls.cpu) {
      statEls.cpu.textContent = cpu !== null ? `${cpu.toFixed(1)}%` : '—';
      if (statEls.cpuBar) statEls.cpuBar.style.width = cpu !== null ? `${Math.min(cpu, 100)}%` : '0%';
    }

    if (statEls.mem) {
      if (mem !== null) {
        const mb = mem >= 1024 ? `${(mem / 1024).toFixed(1)} GB` : `${mem.toFixed(0)} MB`;
        statEls.mem.textContent = mb;
        // Rough bar: assume 16 GB max
        const pct = Math.min((mem / (16 * 1024)) * 100, 100);
        if (statEls.memBar) statEls.memBar.style.width = `${pct}%`;
      } else {
        statEls.mem.textContent = '—';
      }
    }

    if (statEls.fps) statEls.fps.textContent = fps !== null ? fps.toFixed(2) : '—';

    if (statEls.stream) {
      statEls.stream.textContent = s.stream_active ? 'LIVE' : 'Offline';
      statEls.stream.style.color = s.stream_active ? 'var(--danger)' : '';
    }
    if (statEls.streamTime) statEls.streamTime.textContent = s.stream_timecode || '—';

    if (statEls.record) {
      statEls.record.textContent = s.record_active ? 'Recording' : 'Stopped';
      statEls.record.style.color = s.record_active ? 'var(--success)' : '';
    }
    if (statEls.recordTime) statEls.recordTime.textContent = s.record_timecode || '—';

    // Dropped frames
    if (statEls.dropped) {
      const skipped = s.skipped_frames || s.dropped_frames || 0;
      const total = s.total_frames || 1;
      const dropPct = typeof s.dropped_frames_pct === 'number'
        ? s.dropped_frames_pct
        : (skipped / total * 100);
      statEls.dropped.textContent = `${dropPct.toFixed(2)}%`;
      if (statEls.droppedBar) statEls.droppedBar.style.width = `${Math.min(dropPct * 10, 100)}%`;
    }

    // Congestion
    if (statEls.congestion) {
      const cong = typeof s.stream_congestion === 'number' ? s.stream_congestion : null;
      statEls.congestion.textContent = cong !== null ? `${(cong * 100).toFixed(1)}%` : '—';
    }

    // Data / bytes
    if (statEls.bytes) {
      const bytes = s.bytes_per_sec || s.output_bytes || s.stream_bytes;
      if (bytes !== undefined && bytes !== null) {
        statEls.bytes.textContent = formatBytes(bytes);
      } else {
        statEls.bytes.textContent = '—';
      }
    }
  }

  // -------------------------------------------------------------------------
  // Entry point
  // -------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    boot().catch(err => {
      console.error('OBS Remote boot error:', err);
      showToast('Failed to initialize app', 'error');
    });
  });

})();
