/**
 * api.js — OBS Remote API client
 *
 * All fetch/WebSocket calls live here. Every function returns the parsed
 * JSON response (or throws on HTTP or network error).
 *
 * Usage: imported globally as `window.api` via a <script> tag before app.js.
 */

(function (global) {
  'use strict';

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  /**
   * Perform a fetch request and return the parsed JSON body.
   * Throws an Error with a human-readable message on failure.
   *
   * @param {string} url
   * @param {RequestInit} [options]
   * @returns {Promise<any>}
   */
  async function request(url, options = {}) {
    const defaults = {
      headers: { 'Content-Type': 'application/json' },
    };

    const init = Object.assign({}, defaults, options);

    // Merge headers if caller also supplied some
    if (options.headers) {
      init.headers = Object.assign({}, defaults.headers, options.headers);
    }

    let response;
    try {
      response = await fetch(url, init);
    } catch (networkError) {
      throw new Error(`Network error: ${networkError.message}`);
    }

    if (!response.ok) {
      let detail = '';
      try {
        const body = await response.json();
        detail = body.detail || body.message || JSON.stringify(body);
      } catch (_) {
        detail = response.statusText;
      }
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }

    // 204 No Content — return empty object
    if (response.status === 204) return {};

    return response.json();
  }

  /**
   * Shorthand for POST requests with a JSON body.
   */
  function post(url, body) {
    return request(url, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  // -------------------------------------------------------------------------
  // Status & Connection
  // -------------------------------------------------------------------------

  /**
   * GET /api/status
   * @returns {Promise<{ version: string, obs_connected: boolean, obs_host: string, obs_port: number, update_available: boolean }>}
   */
  function getStatus() {
    return request('/api/status');
  }

  /**
   * POST /api/connect
   * @param {string} host
   * @param {number} port
   * @param {string} [password]
   * @returns {Promise<any>}
   */
  function connect(host, port, password) {
    const body = { host, port: Number(port) };
    if (password) body.password = password;
    return post('/api/connect', body);
  }

  // -------------------------------------------------------------------------
  // Scenes
  // -------------------------------------------------------------------------

  /**
   * GET /api/scenes
   * @returns {Promise<{ scenes: string[], current: string }>}
   */
  function getScenes() {
    return request('/api/scenes');
  }

  /**
   * POST /api/scenes/current
   * @param {string} sceneName
   * @returns {Promise<any>}
   */
  function setScene(sceneName) {
    return post('/api/scenes/current', { scene_name: sceneName });
  }

  /**
   * GET /api/scenes/collections
   * @returns {Promise<{ collections: string[], current: string }>}
   */
  function getCollections() {
    return request('/api/scenes/collections');
  }

  /**
   * POST /api/scenes/collections/current
   * @param {string} collectionName
   * @returns {Promise<any>}
   */
  function setCollection(collectionName) {
    return post('/api/scenes/collections/current', { collection_name: collectionName });
  }

  // -------------------------------------------------------------------------
  // Audio
  // -------------------------------------------------------------------------

  /**
   * GET /api/audio
   * @returns {Promise<{ inputs: Array<{ name: string, kind: string, volume_db: number, volume_mul: number, muted: boolean }> }>}
   */
  function getAudio() {
    return request('/api/audio');
  }

  /**
   * POST /api/audio/volume
   * @param {string} inputName
   * @param {number} volumeDb  — value in dB, e.g. -12
   * @returns {Promise<any>}
   */
  function setVolume(inputName, volumeDb) {
    return post('/api/audio/volume', { input_name: inputName, volume_db: volumeDb });
  }

  /**
   * POST /api/audio/mute
   * @param {string} inputName
   * @param {boolean} muted
   * @returns {Promise<any>}
   */
  function setMute(inputName, muted) {
    return post('/api/audio/mute', { input_name: inputName, muted });
  }

  /**
   * POST /api/audio/mute/toggle
   * @param {string} inputName
   * @returns {Promise<any>}
   */
  function toggleMute(inputName) {
    return post('/api/audio/mute/toggle', { input_name: inputName });
  }

  // -------------------------------------------------------------------------
  // Streaming / Recording
  // -------------------------------------------------------------------------

  /**
   * GET /api/streaming/status
   * @returns {Promise<{
   *   stream: { active: boolean, timecode: string, congestion: number, bytes: number, skipped_frames: number, total_frames: number },
   *   record: { active: boolean, paused: boolean, timecode: string, bytes: number }
   * }>}
   */
  function getStreamingStatus() {
    return request('/api/streaming/status');
  }

  /**
   * POST /api/streaming/stream/toggle
   */
  function toggleStream() {
    return post('/api/streaming/stream/toggle');
  }

  /**
   * POST /api/streaming/record/toggle
   */
  function toggleRecord() {
    return post('/api/streaming/record/toggle');
  }

  /**
   * POST /api/streaming/record/pause
   */
  function pauseRecord() {
    return post('/api/streaming/record/pause');
  }

  /**
   * POST /api/streaming/record/resume
   */
  function resumeRecord() {
    return post('/api/streaming/record/resume');
  }

  /**
   * POST /api/streaming/virtualcam/toggle
   */
  function toggleVirtualCam() {
    return post('/api/streaming/virtualcam/toggle');
  }

  /**
   * POST /api/streaming/replay/toggle
   */
  function toggleReplayBuffer() {
    return post('/api/streaming/replay/toggle');
  }

  /**
   * POST /api/streaming/replay/save
   */
  function saveReplay() {
    return post('/api/streaming/replay/save');
  }

  // -------------------------------------------------------------------------
  // Sources
  // -------------------------------------------------------------------------

  /**
   * GET /api/sources/{scene_name}
   * @param {string} sceneName
   * @returns {Promise<{ sources: Array<{ id: number, name: string, kind: string, enabled: boolean, locked: boolean }> }>}
   */
  function getSources(sceneName) {
    return request(`/api/sources/${encodeURIComponent(sceneName)}`);
  }

  /**
   * POST /api/sources/visibility
   * @param {string} sceneName
   * @param {number} sceneItemId
   * @param {boolean} enabled
   * @returns {Promise<any>}
   */
  function setSourceVisibility(sceneName, sceneItemId, enabled) {
    return post('/api/sources/visibility', {
      scene_name: sceneName,
      scene_item_id: sceneItemId,
      enabled,
    });
  }

  // -------------------------------------------------------------------------
  // Filters
  // -------------------------------------------------------------------------

  /**
   * GET /api/filters/{source_name}
   * @param {string} sourceName
   * @returns {Promise<{ filters: Array<{ name: string, kind: string, enabled: boolean }> }>}
   */
  function getFilters(sourceName) {
    return request(`/api/filters/${encodeURIComponent(sourceName)}`);
  }

  /**
   * POST /api/filters/enabled
   * @param {string} sourceName
   * @param {string} filterName
   * @param {boolean} enabled
   * @returns {Promise<any>}
   */
  function setFilterEnabled(sourceName, filterName, enabled) {
    return post('/api/filters/enabled', {
      source_name: sourceName,
      filter_name: filterName,
      enabled,
    });
  }

  // -------------------------------------------------------------------------
  // Studio Mode
  // -------------------------------------------------------------------------

  /**
   * GET /api/studio
   * @returns {Promise<{ enabled: boolean, preview_scene?: string }>}
   */
  function getStudio() {
    return request('/api/studio');
  }

  /**
   * POST /api/studio/toggle
   */
  function toggleStudio() {
    return post('/api/studio/toggle');
  }

  /**
   * POST /api/studio/preview
   * @param {string} sceneName
   */
  function setStudioPreview(sceneName) {
    return post('/api/studio/preview', { scene_name: sceneName });
  }

  /**
   * POST /api/studio/transition
   */
  function studioTransition() {
    return post('/api/studio/transition');
  }

  // -------------------------------------------------------------------------
  // Stats
  // -------------------------------------------------------------------------

  /**
   * GET /api/stats
   * @returns {Promise<{
   *   cpu_usage: number,
   *   memory_usage: number,
   *   active_fps: number,
   *   stream_active: boolean,
   *   stream_timecode: string,
   *   stream_congestion: number,
   *   record_active: boolean,
   *   record_timecode: string,
   *   [key: string]: any
   * }>}
   */
  function getStats() {
    return request('/api/stats');
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  global.api = {
    // Status
    getStatus,
    connect,

    // Scenes
    getScenes,
    setScene,
    getCollections,
    setCollection,

    // Audio
    getAudio,
    setVolume,
    setMute,
    toggleMute,

    // Streaming
    getStreamingStatus,
    toggleStream,
    toggleRecord,
    pauseRecord,
    resumeRecord,
    toggleVirtualCam,
    toggleReplayBuffer,
    saveReplay,

    // Sources
    getSources,
    setSourceVisibility,

    // Filters
    getFilters,
    setFilterEnabled,

    // Studio
    getStudio,
    toggleStudio,
    setStudioPreview,
    studioTransition,

    // Stats
    getStats,
  };

})(window);
