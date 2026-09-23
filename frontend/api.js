window.api = {
  USE_MOCK: true,
  async getHealth() {
    return { status: 'ok', mode: 'demo' };
  },
  async analyzeTask() {
    return { questions: [], filled_fields: [], missing_fields: [], mode: 'demo' };
  },
  async buildCard() {
    return { card: {}, warnings: [] };
  },
  async scoreCard() {
    return { score: 0, level: 'draft', breakdown: [], missing: [] };
  },
  async createTask() {
    return { id: 't1', card: {}, score: 0, level: 'draft', created_at: new Date().toISOString() };
  },
  async updateTask() {
    return { id: 't1', card: {}, score: 0, level: 'draft', created_at: new Date().toISOString() };
  },
  async getTasks() {
    return [];
  },
  async getTask() {
    return { proposals: [] };
  },
  async getTeams() {
    return [];
  },
  async getProposals({ team_id = '' } = {}) {
    const query = team_id ? `?team_id=${encodeURIComponent(team_id)}` : '';
    if (this.USE_MOCK && window.mockApi?.getProposals) {
      return window.mockApi.getProposals({ team_id });
    }
    const response = await fetch(`/api/proposals${query}`);
    return response.json();
  },
  async createProposal() {
    return { id: 'p1', task_id: 't1', team_id: 'team1', status: 'pending' };
  },
  async decideProposal() {
    return { id: 'p1', status: 'accepted' };
  },
  async updateProgress() {
    return { proposal_id: 'p1', team_id: 'team1', stages_done: [], points_total: 0 };
  }
};
