import { HistoryStore, notificationText, groupNotifications } from './history.js';

const $ = (id) => document.getElementById(id);
const storageKey = 'notificationBridge.history.v1';
let storage;
try {
  storage = window.localStorage;
} catch (error) {
  storage = {
    getItem() { throw error; },
    setItem() { throw error; },
    removeItem() { throw error; },
  };
}
const history = new HistoryStore({ storage, key: storageKey });
history.load();
let selectedId = null;
let view = 'all';
let epoch = '';
let cursor = 0;
let source = null;
let session = null;
let activeKeys = new Set();
let phoneStatus = null;
let serverConnected = false;
let attemptedConnection = false;
let saveTimer;
let pollTimer;
let inFlight = false;
let lastRenderSignature = '';
let appRevision = 0;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function setText(id, text) {
  const element = $(id);
  // An unchanged poll must not re-announce the same live-region content.
  if (element.textContent !== text) element.textContent = text;
}

function formatTime(value, full = false) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'Time unavailable';
  return full
    ? date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
    : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function eventLabel(event) {
  return ({ posted: 'Posted', updated: 'Updated', removed: 'Removed from phone', snapshot: 'Observed on phone' })[event.event] || 'Observed on phone';
}

function currentLabel(group) {
  if (group.latest.event === 'removed') return 'Removed from phone';
  if (!serverConnected || phoneStatus?.state !== 'connected') return 'Last observed · connection unavailable';
  if (group.latest.source === source && group.latest.session === session) {
    return activeKeys.has(group.notification.key) ? 'On phone' : 'Not in current snapshot';
  }
  return 'Previously observed';
}

function notificationBody(notification) {
  return notificationText({ ...notification, title: undefined }) || (notification.title ? '' : 'No readable text');
}

function appIdentity(group) {
  const metadata = history.apps?.[group.latest.source]?.[group.package];
  return { label: metadata?.label || group.package || 'Unknown app', icon: metadata?.icon };
}

function appIcon(group) {
  const app = appIdentity(group);
  const initial = (app.label === group.package ? app.label.split('.').pop() : app.label).charAt(0).toUpperCase();
  const tile = node('span', 'app-icon', initial || '?');
  tile.setAttribute('aria-hidden', 'true');
  let hash = 0;
  for (const letter of group.package) hash = (hash * 31 + letter.charCodeAt(0)) | 0;
  tile.dataset.color = Math.abs(hash) % 5;
  // Only locally supplied PNG data is allowed. Never fetch package-derived URLs.
  if (typeof app.icon === 'string' && /^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(app.icon) && app.icon.length <= 100000) {
    const img = node('img');
    img.alt = '';
    img.dataset.testid = 'app-icon';
    img.addEventListener('error', () => img.remove(), { once: true });
    img.src = app.icon;
    tile.append(img);
  }
  return tile;
}

function renderStorage() {
  const unsaved = history.unsavedCount ?? Math.max(0, history.events.length - history.savedCount);
  const error = history.error ? String(history.error.message || history.error) : '';
  document.querySelector('[data-testid="storage-status"]').classList.toggle('has-error', Boolean(error || history.paused));
  let message;
  if (history.paused) {
    message = `Collection paused. ${unsaved} unsaved events remain in memory; new changes may be missed. Export history, then retry saving or clear it.`;
  } else if (error) {
    message = `${error} ${unsaved} unsaved event${unsaved === 1 ? '' : 's'} kept in memory. Export before leaving this page.`;
  } else if (unsaved) {
    message = `Saving ${unsaved} new event${unsaved === 1 ? '' : 's'}…`;
  } else if (history.dirty) {
    message = 'Saving app details…';
  } else {
    const size = Math.round((history.storageBytes || 0) / 1024);
    message = `${history.savedCount} event${history.savedCount === 1 ? '' : 's'} saved in this browser${size ? ` · ${size} KB of 2 MB` : ''}`;
  }
  setText('storage-message', message);
  $('retry-save').hidden = !(error || unsaved || history.paused || history.dirty);
  $('export-button').disabled = history.events.length === 0;
}

function renderConnection() {
  const state = serverConnected ? phoneStatus?.state : 'disconnected';
  $('connection-dot').className = `status-dot ${state === 'connected' ? 'connected' : attemptedConnection ? 'disconnected' : ''}`;
  setText('phone-status', history.paused ? 'Collection paused'
    : !serverConnected ? (attemptedConnection ? 'Phone status unavailable' : 'Waiting for connection')
      : ({ connected: 'Phone connected', connecting: 'Connecting to phone', disconnected: 'Phone disconnected' })[state] || 'Waiting for phone');
  setText('server-status', serverConnected ? 'Local server connected' : attemptedConnection ? 'Local server unavailable' : 'Connecting to local server…');
  let message = serverConnected ? phoneStatus?.message || 'The bridge is ready to receive notifications.'
    : attemptedConnection ? 'Retrying automatically. Start the local server if needed; see Setup & history.'
      : 'Saved history is available while the bridge connects.';
  if (serverConnected && phoneStatus?.last_success) message += ` Last phone read: ${formatTime(phoneStatus.last_success)}.`;
  if (history.paused) message = 'Live intake is paused to protect unsaved history. Export your history and use the storage controls to continue.';
  setText('phone-message', message);
  $('gap-notice').hidden = !history.incomplete;
}

function renderPackageFilter(groups) {
  const select = $('package-filter');
  const previous = select.value;
  const packages = [...new Set(groups.map((group) => group.package))].sort();
  const labels = new Map();
  for (const group of groups) if (!labels.has(group.package)) labels.set(group.package, appIdentity(group).label);
  const signature = JSON.stringify(packages.map((name) => [name, labels.get(name)]));
  if (select.dataset.packages === signature) return;
  select.dataset.packages = signature;
  const all = node('option', '', 'All apps');
  all.value = '';
  select.replaceChildren(all);
  for (const name of packages) {
    const option = node('option', '', labels.get(name));
    option.value = name;
    option.title = name;
    select.append(option);
  }
  select.value = packages.includes(previous) ? previous : '';
}

function emptyList(filtered) {
  const wrap = node('div', 'empty-state');
  const symbol = node('span', 'empty-symbol');
  symbol.textContent = '▤';
  symbol.setAttribute('aria-hidden', 'true');
  wrap.append(symbol, node('h3', '', filtered ? 'No matching notifications' : 'No notifications yet'));
  wrap.append(node('p', '', filtered ? 'Try another search or app filter.' : 'New notifications and their updates will appear here when your phone connects.'));
  if (!filtered) {
    wrap.append(node('p', '', 'Connect your Android phone over USB, then enable Notification Bridge notification access.'));
    wrap.append(node('code', '', 'python3 listener.py setup'));
    wrap.append(node('p', '', 'Keep this page open to collect and save history.'));
  }
  return wrap;
}

function renderRow(group) {
  const row = node('button', `notification-row${selectedId === group.id ? ' is-selected' : ''}`);
  row.type = 'button';
  row.dataset.testid = 'notification-row';
  row.dataset.historyId = group.id;
  row.setAttribute('aria-pressed', String(selectedId === group.id));
  row.setAttribute('aria-controls', 'notification-detail');
  const top = node('div', 'row-top');
  const packageName = group.package || 'Unknown app';
  const identity = node('span', 'app-identity');
  identity.append(node('span', 'app-name', appIdentity(group).label));
  const packageLabel = node('span', 'app-package', packageName);
  packageLabel.title = packageName;
  identity.append(packageLabel);
  top.append(appIcon(group), identity, node('span', 'row-time', formatTime(group.lastSeen)));
  const bottom = node('div', 'row-bottom');
  bottom.append(node('span', `state-label${group.latest.event === 'removed' ? ' removed' : ''}`, currentLabel(group)), node('span', '', `${group.events.length} event${group.events.length === 1 ? '' : 's'}`));
  row.append(top, node('h3', 'row-title', group.notification.title || 'Untitled notification'), node('p', 'row-body', notificationBody(group.notification)), bottom);
  row.addEventListener('click', () => {
    selectedId = group.id;
    renderInbox(true);
    if (window.matchMedia('(max-width: 900px)').matches) $('notification-detail').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
  });
  return row;
}

function renderDetail(group) {
  const detail = $('notification-detail');
  if (!group) {
    const empty = node('div', 'empty-detail');
    const p = node('p', '', 'Notification details');
    p.append(node('small', '', 'Select a notification to see its update history.'));
    empty.append(p);
    detail.replaceChildren(empty);
    return;
  }
  const heading = node('div', 'timeline-heading');
  heading.append(node('h3', '', 'Update history'), node('span', '', `${group.events.length} observed event${group.events.length === 1 ? '' : 's'}`));
  const timeline = node('ol', 'timeline');
  const events = [...group.events].sort((a, b) => a.timestamp - b.timestamp || a.seq - b.seq);
  for (const event of events) {
    const item = node('li', 'timeline-event');
    const title = node('div', 'event-heading');
    const time = node('time', '', formatTime(event.timestamp, true));
    const date = new Date(event.timestamp);
    if (Number.isFinite(date.getTime())) time.dateTime = date.toISOString();
    title.append(node('strong', '', eventLabel(event)), time);
    item.append(title);
    if (event.notification.title) item.append(node('p', 'event-title', event.notification.title));
    const body = notificationBody(event.notification);
    if (body) item.append(node('p', 'event-content', body));
    const progress = event.notification.progress;
    if (progress && (progress.max > 0 || progress.indeterminate)) {
      const wrap = node('div', 'progress-wrap');
      const bar = node('progress');
      bar.setAttribute('aria-label', 'Notification progress');
      if (!progress.indeterminate) {
        bar.max = progress.max;
        bar.value = Math.min(progress.max, Math.max(0, Number(progress.value) || 0));
      }
      wrap.append(bar, node('span', '', progress.indeterminate ? 'In progress' : `Progress ${progress.value ?? 0} / ${progress.max}`));
      item.append(wrap);
    }
    if (event.notification.extraction_errors?.length) item.append(node('p', 'extraction-warning', 'Some custom-view text could not be read.'));
    if (event.event === 'removed' && event.removal_reason !== undefined) item.append(node('p', 'event-meta', `Android removal reason: ${event.removal_reason}`));
    if (event.event === 'snapshot') item.append(node('p', 'event-meta', 'Current-state observation; earlier changes may not have been captured.'));
    timeline.append(item);
  }
  const appHeader = node('div', 'detail-app');
  const identity = node('div', 'app-identity');
  identity.append(node('span', 'app-name', appIdentity(group).label), node('p', 'detail-package', group.package));
  appHeader.append(appIcon(group), identity);
  detail.replaceChildren(node('p', 'detail-eyebrow', 'NOTIFICATION DETAILS'), appHeader, node('h2', 'detail-title', group.notification.title || 'Untitled notification'), node('p', 'detail-status', currentLabel(group)), heading, timeline);
}

function renderInbox(force = false) {
  const groups = groupNotifications(history.events).sort((a, b) => b.lastSeen - a.lastSeen);
  renderPackageFilter(groups);
  const query = $('search-input').value.trim().toLocaleLowerCase();
  const packageName = $('package-filter').value;
  const filtered = groups.filter((group) => (view !== 'removed' || group.latest.event === 'removed')
    && (!packageName || group.package === packageName)
    && (!query || group.events.some((event) => `${appIdentity(group).label}\n${group.package}\n${notificationText(event.notification)}`.toLocaleLowerCase().includes(query))));
  $('all-count').textContent = groups.length;
  $('removed-count').textContent = groups.filter((group) => group.latest.event === 'removed').length;
  $('collection-title').textContent = view === 'removed' ? 'Removed from phone' : 'All notifications';
  $('result-count').textContent = `${filtered.length} notification${filtered.length === 1 ? '' : 's'} · ${history.events.length} retained event${history.events.length === 1 ? '' : 's'}`;
  if (!filtered.some((group) => group.id === selectedId)) selectedId = filtered[0]?.id ?? null;
  // Avoid replacing focused rows, resetting scroll, or disrupting selection on idle polls.
  const signature = JSON.stringify([history.events.length, appRevision, selectedId, query, packageName, view, serverConnected, phoneStatus?.state, source, session, [...activeKeys], filtered.map((group) => group.id)]);
  if (!force && signature === lastRenderSignature) return;
  lastRenderSignature = signature;
  const list = $('notification-list');
  const scroll = list.scrollTop;
  const focusedId = list.contains(document.activeElement)
    ? document.activeElement.closest('.notification-row')?.dataset.historyId : null;
  list.replaceChildren(...(filtered.length ? filtered.map(renderRow) : [emptyList(Boolean(query || packageName || view !== 'all'))]));
  list.scrollTop = scroll;
  if (focusedId) {
    const replacement = [...list.children].find(row => row.dataset.historyId === focusedId);
    (replacement || list).focus({ preventScroll: true });
  }
  renderDetail(filtered.find((group) => group.id === selectedId));
}

function render() {
  renderStorage();
  renderConnection();
  renderInbox();
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const wasPaused = history.paused;
    history.persist();
    render();
    if (wasPaused && !history.paused && !inFlight) poll();
  }, 250);
}

async function poll() {
  if (inFlight || history.paused) return;
  inFlight = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`/api/events?${new URLSearchParams({ after: String(cursor), epoch })}`, { signal: controller.signal, cache: 'no-store' });
    if (!response.ok) throw new Error('Server request failed');
    const data = await response.json();
    if (data.version !== 1 || !Array.isArray(data.events) || !Array.isArray(data.active) || !data.status || typeof data.epoch !== 'string' || !Number.isSafeInteger(data.cursor)) throw new Error('Invalid server response');
    serverConnected = true;
    phoneStatus = data.status;
    source = data.source;
    session = data.session;
    activeKeys = new Set(data.active.map((notification) => notification.key));
    const metadataChanged = history.observeConnection(data);
    const appsChanged = history.updateApps(data.apps || {}, data.source);
    if (appsChanged) appRevision++;
    const added = history.ingest(data.events, data.source);
    if (!history.paused) {
      epoch = data.epoch;
      cursor = data.cursor;
    }
    if (added || metadataChanged || appsChanged) scheduleSave();
  } catch {
    serverConnected = false;
  } finally {
    attemptedConnection = true;
    clearTimeout(timeout);
    inFlight = false;
    render();
    if (!history.paused) pollTimer = setTimeout(poll, 1000);
  }
}

$('search-input').addEventListener('input', () => renderInbox());
$('package-filter').addEventListener('change', () => renderInbox());
for (const name of ['all', 'removed']) {
  $(`${name}-view`).addEventListener('click', () => {
    view = name;
    for (const item of ['all', 'removed']) {
      $(`${item}-view`).classList.toggle('is-active', name === item);
      $(`${item}-view`).setAttribute('aria-pressed', String(name === item));
    }
    renderInbox();
  });
}
$('retry-save').addEventListener('click', () => {
  history.persist();
  render();
  clearTimeout(pollTimer);
  if (!history.paused && !inFlight) poll();
});
$('clear-history').addEventListener('click', () => {
  if (!window.confirm('Clear all notification history saved in this browser and held in this tab? Export a copy first if you want to keep it. This cannot be undone.')) return;
  clearTimeout(saveTimer);
  history.clear();
  selectedId = null;
  lastRenderSignature = '';
  render();
  $('announcement').textContent = history.error ? 'History could not be cleared. See the storage message.' : 'Browser notification history cleared.';
  clearTimeout(pollTimer);
  if (!history.paused && !inFlight) poll();
});
$('export-button').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([history.exportJSON()], { type: 'application/json' }));
  const link = node('a');
  link.href = url;
  link.download = `notification-bridge-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
window.addEventListener('storage', (event) => {
  if (event.key !== storageKey && event.key !== null) return;
  history.load();
  lastRenderSignature = '';
  render();
  if (!history.error && (history.unsavedCount || history.dirty)) scheduleSave();
});
document.addEventListener('keydown', (event) => {
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
    event.preventDefault();
    $('search-input').focus();
  }
});
window.addEventListener('pagehide', () => {
  clearTimeout(saveTimer);
  if (history.unsavedCount || history.dirty) history.persist();
});
render();
poll();
