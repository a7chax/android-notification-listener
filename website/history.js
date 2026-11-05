const STORAGE_KEY = 'notificationBridge.history.v1';
const SAVED_LIMIT = 2 * 1024 * 1024;
const UNSAVED_LIMIT = 1024 * 1024;
const UNSAVED_EVENTS = 1000;
const KINDS = new Set(['snapshot', 'posted', 'updated', 'removed']);

const MAX_APP_SOURCES = 16;
const MAX_APPS = 128;
const MAX_ICON_LENGTH = 90000;
const PACKAGE = /^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$/;
const RESERVED = new Set(['__proto__', 'prototype', 'constructor']);

function objectMap(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function validSource(source) {
  return typeof source === 'string' && source.length > 0 && source.length <= 256
    && !RESERVED.has(source);
}

function validPackage(value) {
  return value.length <= 255 && PACKAGE.test(value) && !RESERVED.has(value);
}

function validIcon(icon) {
  if (typeof icon !== 'string' || icon.length > MAX_ICON_LENGTH
    || !icon.startsWith('data:image/png;base64,')) return false;
  const base64 = icon.slice(22);
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(base64)) return false;
  try {
    return atob(base64.slice(0, 12)).startsWith('\x89PNG\r\n\x1a\n');
  } catch {
    return false;
  }
}

function validApps(apps) {
  return objectMap(apps) && Object.keys(apps).length <= MAX_APP_SOURCES
    && Object.entries(apps).every(([source, packages]) => validSource(source)
      && objectMap(packages) && Object.keys(packages).length <= MAX_APPS
      && Object.entries(packages).every(([packageName, app]) => validPackage(packageName)
        && objectMap(app) && typeof app.label === 'string' && app.label.length <= 256
        && (app.icon === null || validIcon(app.icon))));
}

function sameApp(first, second) {
  return Boolean(first && second && first.label === second.label && first.icon === second.icon);
}

function pendingApps(apps, saved) {
  const pending = {};
  for (const [source, packages] of Object.entries(apps)) {
    for (const [packageName, app] of Object.entries(packages)) {
      if (!sameApp(app, saved[source]?.[packageName])) {
        pending[source] ||= {};
        pending[source][packageName] = app;
      }
    }
  }
  return pending;
}

function mergeApps(saved, pending) {
  const merged = {};
  for (const source of new Set([...Object.keys(saved), ...Object.keys(pending)])) {
    merged[source] = { ...saved[source], ...pending[source] };
  }
  return merged;
}

function metadataBytes(apps) {
  return Object.keys(apps).length ? JSON.stringify(apps).length * 2 : 0;
}

function pauseIntake(store) {
  store.paused = true;
  store.error = 'History intake paused: too much unsaved data. Some incoming changes may be missing. Export history, retry saving, or clear history to resume.';
}

function validEvent(event) {
  return event && typeof event.session === 'string' && event.session.length > 0
    && Number.isSafeInteger(event.seq) && event.seq >= 0
    && Number.isFinite(event.timestamp) && event.timestamp >= 0
    && KINDS.has(event.event) && event.notification
    && typeof event.notification.key === 'string'
    && typeof event.notification.package === 'string';
}

function identity(event, source) {
  return JSON.stringify([source, event.session, event.seq,
    event.event === 'snapshot' ? 'snapshot' : 'event',
    event.event === 'snapshot' ? event.notification.key : null]);
}

function storedPayload(raw) {
  if (raw.length * 2 > SAVED_LIMIT) throw new Error('Oversized history');
  const payload = JSON.parse(raw);
  if (!payload || payload.version !== 1 || !Array.isArray(payload.events)) {
    throw new Error('Unsupported history format');
  }
  if (payload.events.some(event => !validEvent(event)
    || typeof event.source !== 'string' || !event.source
    || event.id !== identity(event, event.source))) {
    throw new Error('Invalid history record');
  }
  if (payload.incomplete !== undefined && typeof payload.incomplete !== 'boolean') {
    throw new Error('Invalid history metadata');
  }
  if (payload.generation !== undefined && typeof payload.generation !== 'string') {
    throw new Error('Invalid history generation');
  }
  if (payload.sessions !== undefined && (!payload.sessions || Array.isArray(payload.sessions)
    || typeof payload.sessions !== 'object'
    || Object.values(payload.sessions).some(value => typeof value !== 'string'))) {
    throw new Error('Invalid session metadata');
  }
  if (payload.apps !== undefined && !validApps(payload.apps)) {
    throw new Error('Invalid app metadata');
  }
  return payload;
}

function mergeEvents(first, second) {
  const unique = new Map();
  for (const event of [...first, ...second]) unique.set(event.id, event);
  return [...unique.values()].sort((a, b) => a.timestamp - b.timestamp || a.seq - b.seq);
}

export function notificationText(notification = {}) {
  const values = [notification.title, notification.text, notification.big_text,
    notification.sub_text, ...(Array.isArray(notification.lines) ? notification.lines : []),
    ...(Array.isArray(notification.view_text) ? notification.view_text : [])];
  return [...new Set(values.filter(value => typeof value === 'string')
    .map(value => value.replace(/\s+/g, ' ').trim()).filter(Boolean))].join(' · ');
}

export function groupNotifications(events) {
  const current = new Map();
  const groups = [];
  const ordered = [...events].sort((a, b) => a.timestamp - b.timestamp || a.seq - b.seq);
  for (const event of ordered) {
    const key = JSON.stringify([event.source, event.session, event.notification.key]);
    let group = current.get(key);
    if (!group || (group.latest.event === 'removed' && event.event !== 'removed')) {
      group = { id: event.id, events: [], firstSeen: event.timestamp };
      current.set(key, group);
      groups.push(group);
    }
    group.events.push(event);
    group.latest = event;
    group.notification = event.notification;
    group.package = event.notification.package;
    group.lastSeen = event.timestamp;
  }
  return groups.sort((a, b) => b.lastSeen - a.lastSeen);
}

/** Owns replay identity and browser persistence; rendering never rewrites history. */
export class HistoryStore {
  constructor({ storage, key = STORAGE_KEY } = {}) {
    this.key = key;
    this.events = [];
    this.error = null;
    this.savedCount = 0;
    this.storageBytes = 0;
    this.paused = false;
    this.blocked = false;
    this.incomplete = false;
    this.sessions = {};
    this.apps = {};
    this.savedApps = {};
    this.dirty = false;
    this.lastRaw = null;
    this.generation = '';
    this.savedIds = new Set();
    this.ids = new Set();
    try {
      this.storage = storage === undefined ? globalThis.localStorage : storage;
    } catch {
      this.storage = null;
      this.error = 'Browser storage is unavailable. New history is only kept in this tab; export it before closing.';
    }
  }

  get unsavedCount() {
    return this.events.reduce((count, event) => count + !this.savedIds.has(event.id), 0);
  }

  load() {
    let raw;
    try {
      if (!this.storage) throw new Error('Storage unavailable');
      raw = this.storage.getItem(this.key);
    } catch {
      this.error = 'Browser storage is unavailable. History in this tab is unsaved; export it before closing.';
      return false;
    }
    let payload;
    try {
      payload = raw === null ? { events: [] } : storedPayload(raw);
    } catch {
      this.blocked = true;
      this.error = 'Saved history is unreadable or uses a different version. The original is untouched. Export this tab’s history, then clear history to start again.';
      return false;
    }
    const pending = pendingApps(this.apps, this.savedApps);
    const apps = mergeApps(payload.apps || {}, pending);
    if (!validApps(apps) || metadataBytes(apps) > SAVED_LIMIT) {
      this.error = 'App metadata capacity reached while merging tabs. Saved data is safe; export this tab before clearing history.';
      return false;
    }
    this.blocked = false;
    const generation = payload.generation || '';
    if (this.lastRaw !== null && (raw === null || generation !== this.generation)) {
      // Another tab explicitly cleared shared history. Keep only local events
      // that were never saved, rather than restoring the deleted records.
      this.events = this.events.filter(event => !this.savedIds.has(event.id));
      this.incomplete = false;
      this.sessions = {};
      this.dirty = false;
    }
    this.generation = generation;
    this.apps = apps;
    this.savedApps = mergeApps(payload.apps || {}, {});
    this.dirty ||= Object.keys(pending).length > 0;
    const saved = payload.events;
    this.events = mergeEvents(saved, this.events);
    this.incomplete ||= Boolean(payload.incomplete);
    this.sessions = { ...(payload.sessions || {}), ...this.sessions };
    this.ids = new Set(this.events.map(event => event.id));
    this.savedIds = new Set(saved.map(event => event.id));
    this.savedCount = this.savedIds.size;
    this.storageBytes = raw === null ? 0 : raw.length * 2;
    this.lastRaw = raw;
    return true;
  }

  observeConnection(response) {
    const previous = this.incomplete;
    const { source, session } = response;
    let sessionChanged = false;
    if (typeof source === 'string' && source && typeof session === 'string' && session) {
      sessionChanged = this.sessions[source] !== session;
      if (this.sessions[source] && sessionChanged) this.incomplete = true;
      this.sessions = { ...this.sessions, [source]: session };
    }
    this.incomplete ||= Boolean(response.replay_gap || response.status?.history_gap);
    const changed = previous !== this.incomplete || sessionChanged;
    this.dirty ||= changed;
    return changed;
  }

  updateApps(incoming, source) {
    if (this.paused || !validSource(source) || !objectMap(incoming)) return false;
    if (!this.apps[source] && Object.keys(this.apps).length >= MAX_APP_SOURCES) return false;
    let changed = false;
    for (const [packageName, app] of Object.entries(incoming)) {
      if (!validPackage(packageName) || !objectMap(app)) continue;
      const metadata = { label: typeof app.label === 'string' ? app.label.slice(0, 256) : packageName,
        icon: validIcon(app.icon) ? app.icon : null };
      if (sameApp(this.apps[source]?.[packageName], metadata)) continue;
      if (!this.apps[source]?.[packageName]
        && Object.keys(this.apps[source] || {}).length >= MAX_APPS) continue;
      const candidate = { ...this.apps, [source]: { ...this.apps[source], [packageName]: metadata } };
      const eventBytes = this.events.filter(event => !this.savedIds.has(event.id))
        .reduce((total, event) => total + JSON.stringify(event).length * 2, 0);
      if (metadataBytes(pendingApps(candidate, this.savedApps)) + eventBytes > UNSAVED_LIMIT
        || metadataBytes(candidate) > SAVED_LIMIT) {
        pauseIntake(this);
        break;
      }
      this.apps = candidate;
      this.dirty = true;
      changed = true;
    }
    return changed;
  }

  ingest(incoming, source) {
    if (this.paused || !Array.isArray(incoming) || typeof source !== 'string' || !source) return 0;
    const unsaved = this.events.filter(event => !this.savedIds.has(event.id));
    let pendingCount = unsaved.length;
    let pendingBytes = metadataBytes(pendingApps(this.apps, this.savedApps))
      + unsaved.reduce((total, event) => total + JSON.stringify(event).length * 2, 0);
    let added = 0;
    for (const event of incoming) {
      if (!validEvent(event)) continue;
      const id = identity(event, source);
      if (this.ids.has(id)) continue;
      const record = { ...event, id, source };
      const size = JSON.stringify(record).length * 2;
      if (pendingCount >= UNSAVED_EVENTS || pendingBytes + size > UNSAVED_LIMIT) {
        pauseIntake(this);
        break;
      }
      this.events.push(record);
      this.ids.add(id);
      pendingCount++;
      pendingBytes += size;
      added++;
    }
    if (added) this.events.sort((a, b) => a.timestamp - b.timestamp || a.seq - b.seq);
    return added;
  }

  persist() {
    if (!this.load() || this.blocked) return false;
    const raw = JSON.stringify({ version: 1, events: this.events,
      incomplete: this.incomplete, sessions: this.sessions, apps: this.apps, generation: this.generation });
    if (raw.length * 2 > SAVED_LIMIT) {
      this.error = 'Saved history reached the 2 MiB limit. Earlier saved data is safe; new events are unsaved. Export history, then clear it to make room.';
      return false;
    }
    try {
      this.storage.setItem(this.key, raw);
    } catch {
      this.error = 'Could not save history: browser storage is unavailable or full. Earlier saved data is safe. Retry saving or export before closing.';
      return false;
    }
    this.savedApps = mergeApps(this.apps, {});
    this.savedIds = new Set(this.events.map(event => event.id));
    this.savedCount = this.savedIds.size;
    this.storageBytes = raw.length * 2;
    this.lastRaw = raw;
    this.error = null;
    this.paused = false;
    this.dirty = false;
    return true;
  }

  clear() {
    // Keep a small reset marker so a suspended tab cannot restore deleted
    // history after another tab has already resumed saving new observations.
    const generation = globalThis.crypto?.randomUUID?.()
      || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const raw = JSON.stringify({ version: 1, events: [], incomplete: false,
      sessions: {}, apps: {}, generation });
    try {
      if (!this.storage) throw new Error('Storage unavailable');
      this.storage.setItem(this.key, raw);
    } catch {
      this.error = 'Could not clear browser storage. History in this tab has been preserved.';
      return false;
    }
    this.events = [];
    this.ids.clear();
    this.savedIds.clear();
    this.savedCount = 0;
    this.storageBytes = raw.length * 2;
    this.error = null;
    this.blocked = false;
    this.paused = false;
    this.incomplete = false;
    this.sessions = {};
    this.apps = {};
    this.savedApps = {};
    this.dirty = false;
    this.lastRaw = raw;
    this.generation = generation;
    return true;
  }

  exportJSON() {
    return JSON.stringify({ version: 1, events: this.events,
      incomplete: this.incomplete, sessions: this.sessions, apps: this.apps, generation: this.generation }, null, 2);
  }
}
