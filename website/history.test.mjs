import test from 'node:test';
import assert from 'node:assert/strict';

import { HistoryStore, notificationText, groupNotifications } from './history.js';
const KEY = 'notificationBridge.history.v1';

function memoryStorage(initial = null) {
  let value = initial;
  return {
    getItem: () => value,
    setItem: (_, next) => { value = next; },
    removeItem: () => { value = null; },
  };
}

function event(seq, kind = 'posted', key = 'ride', text = 'Finding your driver') {
  return {
    session: 'phone-session', seq, event: kind, timestamp: 1700000000000 + seq * 1000,
    notification: { key, package: 'dev.local.notificationbridge', title: null,
      text: null, view_text: [text], progress: { value: 10, max: 100 } },
  };
}

test('retains lifecycle events after removal and restores on refresh without replay duplicates', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  store.load();
  const events = [event(1), event(2, 'updated', 'ride', 'Driver on the way'),
    event(3, 'updated', 'ride', 'Driver arrived'), event(4, 'removed', 'ride', 'Driver arrived')];
  assert.equal(store.ingest(events, 'phone'), 4);
  assert.equal(store.persist(), true);
  const restored = new HistoryStore({ storage });
  restored.load();
  assert.equal(restored.ingest(events, 'phone'), 0);
  assert.equal(restored.events.length, 4);
  assert.equal(restored.savedCount, 4);
  const groups = groupNotifications(restored.events);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].latest.event, 'removed');
  assert.equal(groups[0].events.length, 4);
});

test('keeps every key in a snapshot but deduplicates later identical snapshot replay', () => {
  const store = new HistoryStore({ storage: memoryStorage() });
  const first = event(8, 'snapshot');
  const second = event(8, 'snapshot', 'chat', 'Message');
  assert.equal(store.ingest([first, second], 'phone'), 2);
  assert.equal(store.ingest([{ ...first, timestamp: first.timestamp + 5000 }, second], 'phone'), 0);
  assert.equal(store.events.length, 2);
});

test('separates devices and Android sessions without deleting earlier history', () => {
  const store = new HistoryStore({ storage: memoryStorage() });
  store.ingest([event(1)], 'phone-a');
  store.ingest([event(1)], 'phone-b');
  store.ingest([{ ...event(1), session: 'new-session' }], 'phone-a');
  assert.equal(store.events.length, 3);
  assert.equal(groupNotifications(store.events).length, 3);
});

test('a new post after observed removal creates a new occurrence', () => {
  const store = new HistoryStore({ storage: memoryStorage() });
  store.ingest([event(1), event(2, 'removed'), event(3, 'posted')], 'phone');
  const groups = groupNotifications(store.events);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].events.length, 1);
  assert.equal(groups[0].latest.seq, 3);
  assert.equal(groups[1].latest.event, 'removed');
});

test('text projection includes all standard and custom readable text without duplicates', () => {
  assert.equal(notificationText({ title: 'Ride', text: 'Driver arriving',
    big_text: 'Driver arriving', lines: ['Lobby'], view_text: ['Lobby', '  Gate  2  '],
    sub_text: 'Order 17' }), 'Ride · Driver arriving · Order 17 · Lobby · Gate 2');
});

test('a quota failure preserves previous saved history and tracks unsaved events', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  store.ingest([event(1)], 'phone');
  assert.equal(store.persist(), true);
  const saved = storage.getItem(KEY);
  const realSet = storage.setItem;
  storage.setItem = () => { throw new Error('QuotaExceededError'); };
  store.ingest([event(2, 'updated')], 'phone');
  assert.equal(store.persist(), false);
  assert.equal(storage.getItem(KEY), saved);
  assert.equal(store.savedCount, 1);
  assert.equal(store.unsavedCount, 1);
  assert.match(store.error, /sav|storage|space/i);
  storage.setItem = realSet;
  assert.equal(store.persist(), true);
  assert.equal(store.unsavedCount, 0);
});

test('malformed or newer storage is preserved until explicit clear', () => {
  for (const initial of ['broken json', '{"version":2,"events":[]}',
    '{"version":1,"events":[{"event":"posted"}]}']) {
    const storage = memoryStorage(initial);
    const store = new HistoryStore({ storage });
    store.load();
    store.ingest([event(1)], 'phone');
    assert.equal(store.persist(), false);
    assert.equal(storage.getItem(KEY), initial);
    assert.ok(store.error);
    assert.equal(store.clear(), true);
    assert.equal(store.persist(), true);
  }
});

test('blocked storage leaves the live history available for export', () => {
  const storage = { getItem() { throw new Error('SecurityError'); },
    setItem() { throw new Error('SecurityError'); }, removeItem() { throw new Error('SecurityError'); } };
  const store = new HistoryStore({ storage });
  assert.doesNotThrow(() => store.load());
  store.ingest([event(1)], 'phone');
  assert.equal(store.persist(), false);
  assert.equal(JSON.parse(store.exportJSON()).events.length, 1);
  assert.equal(store.clear(), false);
  assert.equal(store.events.length, 1);
});

test('two tabs merge each other before saving and keep pending local events', () => {
  const storage = memoryStorage();
  const a = new HistoryStore({ storage });
  const b = new HistoryStore({ storage });
  a.load(); b.load();
  a.ingest([event(1)], 'phone'); a.persist();
  b.ingest([event(2, 'updated')], 'phone'); b.load();
  assert.equal(b.events.length, 2);
  assert.equal(b.unsavedCount, 1);
  assert.equal(b.persist(), true);
  a.load();
  assert.equal(a.events.length, 2);
  assert.equal(a.unsavedCount, 0);
});

test('persistent capacity never evicts saved records and unsaved capacity pauses intake', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  store.ingest([event(1)], 'phone'); store.persist();
  const saved = storage.getItem(KEY);
  for (let seq = 2; seq <= 1100; seq++) {
    store.ingest([event(seq, 'updated', 'ride', 'x'.repeat(2000))], 'phone');
  }
  assert.equal(store.paused, true);
  assert.ok(store.unsavedCount <= 1000);
  assert.ok(store.events.length < 1100);
  assert.equal(store.events[0].seq, 1);
  assert.equal(storage.getItem(KEY), saved);
});

test('malformed network events are ignored without stopping valid events', () => {
  const store = new HistoryStore({ storage: memoryStorage() });
  assert.equal(store.ingest([null, {}, { ...event(1), timestamp: NaN }, event(2)], 'phone'), 1);
  assert.equal(store.events[0].seq, 2);
});

test('two MiB persistent limit leaves earlier saves intact without eviction', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  for (let batch = 0; batch < 2; batch++) {
    store.ingest(Array.from({ length: 20 }, (_, index) =>
      event(batch * 20 + index + 1, 'updated', 'ride', 'x'.repeat(24000))), 'phone');
    assert.equal(store.persist(), true);
  }
  const saved = storage.getItem(KEY);
  store.ingest(Array.from({ length: 10 }, (_, index) =>
    event(41 + index, 'updated', 'ride', 'x'.repeat(24000))), 'phone');
  assert.equal(store.persist(), false);
  assert.equal(storage.getItem(KEY), saved);
  assert.equal(store.savedCount, 40);
  assert.equal(store.unsavedCount, 10);
  assert.match(store.error, /2 MiB/);
});

test('a clear in another tab does not resurrect saved history', () => {
  const storage = memoryStorage();
  const first = new HistoryStore({ storage });
  first.ingest([event(1)], 'phone'); first.persist();
  const second = new HistoryStore({ storage });
  second.load();
  first.clear();
  second.load();
  assert.equal(second.events.length, 0);
  second.persist();
  assert.equal(JSON.parse(storage.getItem(KEY)).events.length, 0);
});

test('gap and Android-session-change warnings survive page refresh', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  const response = { source: 'phone', session: 'one', replay_gap: false,
    status: { history_gap: false } };
  store.observeConnection(response);
  store.persist();
  const restored = new HistoryStore({ storage }); restored.load();
  assert.equal(restored.incomplete, false);
  assert.equal(restored.observeConnection({ ...response, session: 'two' }), true);
  assert.equal(restored.incomplete, true);
  restored.persist();
  const refreshed = new HistoryStore({ storage }); refreshed.load();
  assert.equal(refreshed.incomplete, true);
  refreshed.clear();
  refreshed.observeConnection({ ...response, replay_gap: true });
  refreshed.persist();
  const gapRestored = new HistoryStore({ storage }); gapRestored.load();
  assert.equal(gapRestored.incomplete, true);
});

test('external clear also removes saved gap metadata without any notifications', () => {
  const storage = memoryStorage();
  const first = new HistoryStore({ storage });
  first.observeConnection({ replay_gap: true }); first.persist();
  const second = new HistoryStore({ storage }); second.load();
  first.clear(); second.load();
  assert.equal(second.incomplete, false);
});

test('a delayed tab respects clear even after the clearing tab saves connection metadata', () => {
  const storage = memoryStorage();
  const first = new HistoryStore({ storage });
  first.ingest([event(1)], 'phone'); first.persist();
  const second = new HistoryStore({ storage }); second.load();
  first.clear();
  first.observeConnection({ source: 'phone', session: 'phone-session' });
  first.persist();
  second.load(); second.persist();
  assert.equal(second.events.length, 0);
  assert.equal(JSON.parse(storage.getItem(KEY)).events.length, 0);
});

const ICON = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1sAAAAASUVORK5CYII=';
const APPS = { 'dev.local.notificationbridge': { label: 'Notification Bridge', icon: ICON } };

test('app metadata restores offline and is stored once independently of event count', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  assert.deepEqual(store.apps, {});
  assert.equal(store.updateApps(APPS, 'phone'), true);
  assert.equal(store.dirty, true);
  assert.equal(store.updateApps(APPS, 'phone'), false);
  store.ingest([event(1), event(2, 'updated'), event(3, 'removed')], 'phone');
  assert.equal(store.persist(), true);
  const raw = storage.getItem(KEY);
  assert.equal(raw.split(ICON).length - 1, 1);
  const restored = new HistoryStore({ storage });
  assert.equal(restored.load(), true);
  assert.deepEqual(restored.apps.phone, APPS);
  assert.deepEqual(JSON.parse(restored.exportJSON()).apps.phone, APPS);
  assert.equal(restored.events.length, 3);
  assert.equal(restored.clear(), true);
  assert.deepEqual(restored.apps, {});
  assert.deepEqual(JSON.parse(storage.getItem(KEY)).apps, {});
});

test('old version one history without app metadata still loads', () => {
  const storage = memoryStorage('{"version":1,"events":[]}');
  const store = new HistoryStore({ storage });
  assert.equal(store.load(), true);
  assert.deepEqual(store.apps, {});
  assert.equal(store.persist(), true);
});

test('network metadata rejects unsafe icons and packages and caps labels', () => {
  const store = new HistoryStore({ storage: memoryStorage() });
  for (const icon of ['https://example.com/icon.png', 'data:image/svg+xml;base64,AAAA',
    'data:image/png;base64,not-base64!', 'data:image/png;base64,AAAA',
    'data:image/png;base64,' + 'A'.repeat(90000)]) {
    const first = store.apps.phone === undefined;
    assert.equal(store.updateApps({ 'example.demo': { label: 'Demo', icon } }, 'phone'), first);
    assert.equal(store.apps.phone['example.demo'].icon, null);
  }
  store.updateApps({ 'bad/package': { label: 'Unsafe', icon: ICON },
    'example.long': { label: 'x'.repeat(300), icon: ICON } }, 'phone');
  assert.equal(store.apps.phone['bad/package'], undefined);
  assert.equal(store.apps.phone['example.long'].label.length, 256);
  assert.equal(store.updateApps(APPS, '__proto__'), false);
});

test('invalid stored app metadata preserves the original until clear', () => {
  for (const apps of [[], { phone: [] }, { phone: { 'bad/package': { label: 'Bad', icon: null } } },
    { phone: { 'example.demo': { label: 'Demo', icon: 'https://example.com/icon.png' } } },
    { phone: { 'example.demo': { label: 'x'.repeat(257), icon: null } } }]) {
    const original = JSON.stringify({ version: 1, events: [], apps });
    const storage = memoryStorage(original);
    const store = new HistoryStore({ storage });
    assert.equal(store.load(), false);
    assert.equal(store.blocked, true);
    store.updateApps(APPS, 'phone');
    assert.equal(store.persist(), false);
    assert.equal(storage.getItem(KEY), original);
    assert.equal(store.clear(), true);
  }
});

test('metadata merges across tabs without stale entries overwriting remote changes', () => {
  const storage = memoryStorage();
  const first = new HistoryStore({ storage });
  first.updateApps(APPS, 'phone'); first.persist();
  const second = new HistoryStore({ storage }); second.load();
  first.updateApps({ 'dev.local.notificationbridge': { label: 'Renamed Bridge', icon: ICON } }, 'phone');
  first.persist();
  second.updateApps({ 'example.chat': { label: 'Chat', icon: null } }, 'phone');
  assert.equal(second.persist(), true);
  assert.equal(second.apps.phone['dev.local.notificationbridge'].label, 'Renamed Bridge');
  assert.equal(second.apps.phone['example.chat'].label, 'Chat');
  first.load();
  assert.equal(first.apps.phone['example.chat'].label, 'Chat');
});

test('remote clear removes saved metadata but retains pending local metadata', () => {
  const storage = memoryStorage();
  const first = new HistoryStore({ storage });
  first.updateApps(APPS, 'phone'); first.persist();
  const second = new HistoryStore({ storage }); second.load();
  second.updateApps({ 'example.chat': { label: 'Chat', icon: null } }, 'phone');
  first.clear(); first.persist();
  second.load();
  assert.equal(second.apps.phone['dev.local.notificationbridge'], undefined);
  assert.equal(second.apps.phone['example.chat'].label, 'Chat');
  second.persist();
  first.load();
  assert.equal(first.apps.phone['dev.local.notificationbridge'], undefined);
});

function largeIcon() {
  return 'data:image/png;base64,' + 'iVBORw0KGgo' + 'A'.repeat(87000 - 11);
}

test('app metadata obeys the unsaved memory cap and cannot bypass it through event intake', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  const apps = Object.fromEntries(Array.from({ length: 128 }, (_, i) =>
    [`example.app${i}`, { label: `App ${i}`, icon: largeIcon() }]));
  store.updateApps(apps, 'phone');
  assert.equal(store.paused, true);
  assert.ok(JSON.stringify(store.apps).length * 2 < 1024 * 1024);
  assert.equal(store.ingest([event(1)], 'phone'), 0);
  assert.equal(store.persist(), true);
  assert.equal(store.paused, false);
  assert.equal(store.ingest([event(1, 'posted', 'ride', 'x'.repeat(490000))], 'phone'), 1);
  store.updateApps({ 'example.next': { label: 'Next', icon: largeIcon() } }, 'phone');
  assert.equal(store.paused, true);
  assert.equal(store.apps.phone['example.next'], undefined);
});

test('metadata counts toward saved capacity and a failed save preserves prior icons', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  for (let batch = 0; batch < 2; batch++) {
    store.ingest(Array.from({ length: 20 }, (_, index) =>
      event(batch * 20 + index + 1, 'updated', 'ride', 'x'.repeat(24000))), 'phone');
    assert.equal(store.persist(), true);
  }
  const previous = storage.getItem(KEY);
  store.updateApps({ 'example.demo': { label: 'Demo', icon: largeIcon() } }, 'phone');
  assert.equal(store.persist(), false);
  assert.equal(storage.getItem(KEY), previous);
  assert.equal(store.apps.phone['example.demo'].icon, largeIcon());
  assert.match(store.error, /2 MiB/);
});

test('metadata keeps at most 128 packages per source and bounded source count', () => {
  const store = new HistoryStore({ storage: memoryStorage() });
  const apps = Object.fromEntries(Array.from({ length: 140 }, (_, i) =>
    [`example.app${i}`, { label: `App ${i}`, icon: null }]));
  store.updateApps(apps, 'phone');
  assert.equal(Object.keys(store.apps.phone).length, 128);
  for (let i = 0; i < 30; i++) store.updateApps(APPS, `phone${i}`);
  assert.ok(Object.keys(store.apps).length <= 16);
});

test('pending icons consume the same unsaved budget as incoming events', () => {
  const store = new HistoryStore({ storage: memoryStorage() });
  const apps = Object.fromEntries(Array.from({ length: 5 }, (_, i) =>
    [`example.app${i}`, { label: `App ${i}`, icon: largeIcon() }]));
  assert.equal(store.updateApps(apps, 'phone'), true);
  assert.equal(store.ingest([event(1, 'posted', 'ride', 'x'.repeat(100000))], 'phone'), 0);
  assert.equal(store.paused, true);
  assert.equal(store.events.length, 0);
});

test('metadata quota failures retain saved icons and pending updated names', () => {
  const storage = memoryStorage();
  const store = new HistoryStore({ storage });
  store.updateApps(APPS, 'phone'); store.persist();
  const saved = storage.getItem(KEY);
  storage.setItem = () => { throw new Error('QuotaExceededError'); };
  store.updateApps({ 'dev.local.notificationbridge': { label: 'Renamed', icon: ICON } }, 'phone');
  assert.equal(store.persist(), false);
  assert.equal(storage.getItem(KEY), saved);
  assert.equal(store.apps.phone['dev.local.notificationbridge'].label, 'Renamed');
  assert.equal(store.dirty, true);
});
