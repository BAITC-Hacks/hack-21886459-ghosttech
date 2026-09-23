const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../api.js'), 'utf8');

function client(fetch, port = '8080') {
  const sandbox = { window: {}, location: { protocol: 'http:', hostname: '127.0.0.1', port },
    fetch, URLSearchParams, encodeURIComponent, Error };
  vm.runInNewContext(source, sandbox);
  return sandbox.window.api;
}

test('static frontend targets FastAPI, omits blank filters and sends no credentials', async () => {
  const api = client(async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:8000/api/tasks?offset=0&limit=50');
    assert.equal(options.credentials, 'omit');
    assert.equal(options.method, 'GET');
    return { ok: true, status: 200, json: async () => [] };
  });
  assert.deepEqual(await api.getTasks({ topic: '', level: '', offset: 0, limit: 50 }), []);
});

test('same-origin client serializes bodies and encodes path IDs', async () => {
  const api = client(async (url, options) => {
    assert.equal(url, '/api/tasks/task%2F1/proposals');
    assert.equal(options.method, 'POST');
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
