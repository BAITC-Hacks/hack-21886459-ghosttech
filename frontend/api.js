(() => {
  const baseUrl = window.API_BASE_URL || (location.port === '8080'
    ? `${location.protocol}//${location.hostname}:8000/api` : '/api');

  async function request(path, { method = 'GET', body } = {}) {
    let response;
    try {
      response = await fetch(`${baseUrl}${path}`, {
        method, credentials: 'omit', cache: 'no-store',
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new Error('Не удалось связаться с сервером. Проверьте, что FastAPI запущен.');
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const message = typeof payload.detail === 'string' ? payload.detail
        : Array.isArray(payload.detail) ? payload.detail.map((item) => `${item.loc.slice(1).join('.')}: ${item.msg}`).join('; ')
        : `Ошибка сервера (${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }

  const query = (params = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== '' && value !== undefined && value !== null) search.set(key, value);
    }
    return search.size ? `?${search}` : '';
  };
  const id = encodeURIComponent;
  window.api = {
    USE_MOCK: false,
    getHealth: () => request('/health'),
    analyzeTask: (body) => request('/tasks/analyze', { method: 'POST', body }),
    buildCard: (body) => request('/tasks/build-card', { method: 'POST', body }),
    scoreCard: (body) => request('/tasks/score', { method: 'POST', body }),
    createTask: (body) => request('/tasks', { method: 'POST', body }),
    updateTask: (taskId, body) => request(`/tasks/${id(taskId)}`, { method: 'PATCH', body }),
    getTasks: (params) => request(`/tasks${query(params)}`),
    getTask: (taskId) => request(`/tasks/${id(taskId)}`),
    getTeams: (params) => request(`/teams${query(params)}`),
    createTeam: (body) => request('/teams', { method: 'POST', body }),
    updateTeam: (teamId, body) => request(`/teams/${id(teamId)}`, { method: 'PATCH', body }),
    getProposals: (taskId) => request(`/tasks/${id(taskId)}/proposals`),
    createProposal: (taskId, body) => request(`/tasks/${id(taskId)}/proposals`, { method: 'POST', body }),
    decideProposal: (proposalId, body) => request(`/proposals/${id(proposalId)}/decision`, { method: 'PATCH', body }),
    updateProgress: (proposalId, body) => request(`/proposals/${id(proposalId)}/progress`, { method: 'POST', body }),
  };
})();
