const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function setup(saved = 'ru') {
  const records = new Map([['ghosttech.language', saved]]);
  const element = { nodeType: 1, childNodes: [], matches: () => false, hasAttribute: () => false };
  const document = { documentElement: element, querySelectorAll: () => [], addEventListener() {}, dispatchEvent() {} };
  const sandbox = { window: {}, document, localStorage: { getItem: key => records.get(key), setItem: (key, value) => records.set(key, value) }, MutationObserver: class { observe() {} }, CustomEvent: class {}, console };
  for (const name of ['i18n-static.js', 'i18n-dynamic.js', 'i18n.js']) vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', name), 'utf8'), sandbox);
  return { api: sandbox.window.GhostI18n, records, element };
}
test('language switch persists language and restores Russian', () => {
  const {api, records, element} = setup();
  api.setLanguage('en');
  assert.equal(api.t('Название задачи'), 'Task title');
  assert.equal(records.get('ghosttech.language'), 'en');
  assert.equal(element.lang, 'en');
  api.setLanguage('kk');
  assert.equal(api.t('Название задачи'), 'Тапсырма атауы');
  api.setLanguage('ru');
  assert.equal(api.t('Название задачи'), 'Название задачи');
});
test('dynamic translation preserves numeric values and unknown user prose', () => {
  const {api} = setup('en');
  assert.equal(api.t('Показано 12 из 30'), 'Showing 12 of 30');
  assert.equal(api.t('Client text $& https://example.org'), 'Client text $& https://example.org');
  assert.equal(api.t('  Название задачи  '), '  Task title  ');
});
test('switching does not replace nodes and restores their original text', () => {
  const {api, element} = setup();
  const text = { nodeType: 3, nodeValue: 'Название задачи', parentElement: {closest: () => null} };
  element.childNodes.push(text);
  api.setLanguage('en'); assert.equal(text.nodeValue, 'Task title');
  api.setLanguage('kk'); assert.equal(text.nodeValue, 'Тапсырма атауы');
  api.setLanguage('ru'); assert.equal(text.nodeValue, 'Название задачи');
  assert.equal(element.childNodes[0], text);
});
test('API requests carry the current language without changing payloads', async () => {
  const sent = [];
  const sandbox = { window: { GhostI18n: { language: () => 'kk' } }, location: { port: '8000' }, URLSearchParams, encodeURIComponent, Error,
    fetch: async (url, options) => { sent.push(options); return {ok: true, status: 200, json: async () => ({})}; } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../api.js'), 'utf8'), sandbox);
  await sandbox.window.api.analyzeTask({draft_text: 'Original draft', topic: 'education'});
  assert.equal(sent[0].headers['Accept-Language'], 'kk');
  assert.equal(JSON.parse(sent[0].body).draft_text, 'Original draft');
});
