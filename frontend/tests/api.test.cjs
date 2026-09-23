const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../api.js'), 'utf8');

function client(fetch, port = '8000') {
  const sandbox = { window: {}, location: { protocol: 'http:', hostname: '127.0.0.1', port },
    fetch, URLSearchParams, encodeURIComponent, Error };
  vm.runInNewContext(source, sandbox);
  return sandbox.window.api;
}

test('static frontend on 8080 targets FastAPI on 8000 with session cookies', async () => {
  const api = client(async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:8000/api/tasks?offset=0&limit=50');
    assert.equal(options.credentials, 'include');
    assert.equal(options.method, 'GET');
    return { ok: true, status: 200, json: async () => [] };
  }, '8080');
  assert.deepEqual(await api.getTasks({ topic: '', level: '', offset: 0, limit: 50 }), []);
});

test('account requests use JSON and include the session across local ports', async () => {
  const calls = [];
  const api = client(async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: url.endsWith('/logout') ? 204 : 200,
      json: async () => ({ id: 'user1', role: 'student' }) };
  }, '8080');
  assert.equal((await api.getMe()).id, 'user1');
  assert.equal((await api.login({ email: 'a@example.test', password: 'secret' })).role, 'student');
  await api.register({ email: 'b@example.test', password: 'secret', name: 'B', role: 'business' });
  assert.equal(await api.logout(), null);
  assert.deepEqual(calls.map((call) => call.url),
    ['/api/auth/me', '/api/auth/login', '/api/auth/register', '/api/auth/logout']
      .map((path) => `http://127.0.0.1:8000${path}`));
  assert.deepEqual(calls.map((call) => call.options.method), ['GET', 'POST', 'POST', 'POST']);
  assert.ok(calls.every((call) => call.options.credentials === 'include'));
  assert.deepEqual(JSON.parse(calls[2].options.body),
    { email: 'b@example.test', password: 'secret', name: 'B', role: 'business' });
  assert.deepEqual(JSON.parse(calls[3].options.body), {});
});

test('same-origin client serializes bodies and encodes path IDs', async () => {
  const api = client(async (url, options) => {
    assert.equal(url, '/api/tasks/task%2F1/proposals');
    assert.equal(options.method, 'POST');
    assert.equal(options.credentials, 'include');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), { team_id: 'team1', idea: 'Test' });
    return { ok: true, status: 201, json: async () => ({ id: 'p1' }) };
  }, '8000');
  assert.deepEqual(await api.createProposal('task/1', { team_id: 'team1', idea: 'Test' }), { id: 'p1' });
});

test('API errors retain status and validation details', async () => {
  const api = client(async () => ({ ok: false, status: 422, json: async () => ({
    detail: [{ loc: ['body', 'card', 'title'], msg: 'Required' }],
  }) }));
  await assert.rejects(api.createTask({}), (error) => error.status === 422 && error.message === 'card.title: Required');
});

test('network errors have a readable message', async () => {
  const api = client(async () => { throw new Error('ECONNREFUSED'); });
  await assert.rejects(api.getHealth(), /FastAPI/);
});

test('team workspace loads server proposals with filters and pagination', async () => {
  const api = client(async (url) => {
    assert.equal(url, '/api/proposals?team_id=team1&offset=0&limit=100');
    return { ok: true, status: 200, json: async () => [{ id: 'p1', team_id: 'team1' }] };
  }, '8000');
  assert.deepEqual(await api.getTeamProposals({ team_id: 'team1', offset: 0, limit: 100 }), [{ id: 'p1', team_id: 'team1' }]);
});

test('demo directory and catalog keep role, author and Unicode search filters', async () => {
  const urls = [];
  const api = client(async (url) => {
    urls.push(url);
    return { ok: true, status: 200, json: async () => [] };
  }, '8000');
  await api.getTopics();
  await api.getParticipants({ role: 'business', offset: 0, limit: 100 });
  await api.getTasks({ owner_id: 'demo-business-01', search: 'УЧЁТ', topic: 'образование' });
  assert.equal(urls[0], '/api/topics');
  assert.equal(urls[1], '/api/participants?role=business&offset=0&limit=100');
  const query = new URLSearchParams(urls[2].split('?')[1]);
  assert.equal(query.get('owner_id'), 'demo-business-01');
  assert.equal(query.get('search'), 'УЧЁТ');
  assert.equal(query.get('topic'), 'образование');
});


test('AI validation errors preserve the new server error message', async () => {
  const api = client(async () => ({ ok: false, status: 422, json: async () => ({
    error: { code: 'validation_error', message: 'Заполните тему задачи.' },
  }) }));
  await assert.rejects(api.analyzeTask({}), (error) => error.status === 422 && error.message === 'Заполните тему задачи.');
});

test('AI validation errors show the Russian server message', async () => {
  const api = client(async () => ({ ok: false, status: 422, json: async () => ({
    error: { code: 'validation_error', message: 'Описание должно содержать минимум 10 символов.' },
  }) }));
  await assert.rejects(api.analyzeTask({}), (error) => error.status === 422 && error.message.includes('минимум 10'));
});
