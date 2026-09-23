document.addEventListener('DOMContentLoaded', () => {
  const $ = (selector) => document.querySelector(selector);
  const api = window.api;
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
  const plural = (number, forms) => {
    const value = Math.abs(number) % 100, last = value % 10;
    return value > 10 && value < 20 ? forms[2] : last === 1 ? forms[0] : last >= 2 && last <= 4 ? forms[1] : forms[2];
  };
  const fields = [
    ['title', 'Название задачи'], ['topic', 'Тема'], ['context', 'Контекст и проблема'],
    ['need', 'Потребность'], ['users', 'Пользователи и участники'], ['data', 'Данные и материалы'],
    ['constraints', 'Ограничения'], ['expected_result', 'Ожидаемый результат'],
    ['success_criteria', 'Критерии успеха'], ['contact', 'Контакт'], ['interaction_format', 'Формат взаимодействия'],
  ];
  const levelMeta = {
    draft: { label: 'Черновик', color: '#9CA3AF' }, working: { label: 'Рабочая', color: '#3B82F6' },
    ready: { label: 'Готовая', color: '#10B981' }, priority: { label: 'Приоритетная', color: '#F59E0B' },
  };
  const statuses = { pending: 'На рассмотрении', accepted: 'Принят', rejected: 'Отклонён' };
  const stages = { prototype: ['Прототип', 10], testing: ['Проверено с бизнесом', 20], final: ['Результат принят', 30] };
  let myTeam = null, availableTeams = [], questions = [], publishedId = null;
  let card = Object.fromEntries(fields.map(([key]) => [key, '']));
  let catalogTasks = [], catalogRevision = 0, proposalRevision = 0, scoreRevision = 0, scoreTimer;
  let selectedTeamId = null, teamTasks = [], teamProposals = [], selectedTask = null, teamRevision = 0;
  let unlockedStep = 1, currentStep = 1, assistantBusy = false;
  const completedSteps = new Set();
  const readiness = {
    draft: 'Потребуются уточнения у бизнеса', working: 'Возможны уточнения',
    ready: 'Можно начинать без уточнений', priority: 'Полностью готова к работе',
  };

  function notify(message, isError = false) {
    $('#app-message').textContent = message;
    $('#app-message').hidden = !message;
    $('#app-message').classList.toggle('is-error', isError);
  }
  async function run(button, action, errorTarget) {
    if (button) button.disabled = true;
    try { await action(); }
    catch (error) {
      if (errorTarget) errorTarget.textContent = error.message;
      else notify(error.message, true);
    } finally {
      if (button) button.disabled = false;
      if (button === $('#publish-button')) updatePublish();
    }
  }
  function onClick(selector, action) {
    $(selector).addEventListener('click', (event) => run(event.currentTarget, action));
  }
  async function withAssistant(buttonId, label, action) {
    const button = $(buttonId), previous = button.textContent;
    const controls = [$('#analyze-button'), $('#build-card-button'), $('#sample-button'), $('#draft-text'), $('#task-topic'), $('#confirm-check'), $('#publish-button'), ...document.querySelectorAll('#question-list textarea, #card-form textarea, [data-tab], .wizard-step')];
    const disabled = controls.map((control) => control.disabled);
    assistantBusy = true;
    controls.forEach((control) => { control.disabled = true; });
    button.textContent = label; button.setAttribute('aria-busy', 'true'); notify('');
    try { return await action(); }
    finally {
      controls.forEach((control, index) => { control.disabled = disabled[index]; });
      button.textContent = previous; button.removeAttribute('aria-busy');
      assistantBusy = false; setStep(currentStep); updatePublish();
    }
  }
  document.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => $(`#${button.dataset.close}`).close()));
  function fillTeamForm() {
    myTeam = availableTeams.find((team) => team.id === $('#team-choice').value) || null;
    for (const key of ['name', 'interests', 'skills', 'tech']) {
      $(`#team-${key}`).value = key === 'name' ? myTeam?.name || '' : (myTeam?.[key] || []).join(', ');
    }
  }
  async function openTeam() {
    availableTeams = await allTeams();
    $('#team-choice').innerHTML = '<option value="">Новая команда</option>' + availableTeams.map((team) => `<option value="${escape(team.id)}">${escape(team.name)}</option>`).join('');
    fillTeamForm();
    $('#team-error').textContent = ''; $('#team-dialog').showModal();
  }
  onClick('#team-button', openTeam);
  $('#team-choice').addEventListener('change', fillTeamForm);
  $('#team-form').addEventListener('submit', (event) => {
    event.preventDefault(); $('#team-error').textContent = '';
    run(event.currentTarget.querySelector('[type="submit"]'), async () => {
      const payload = { name: $('#team-name').value };
      for (const key of ['interests', 'skills', 'tech']) payload[key] = $(`#team-${key}`).value.split(',').map((v) => v.trim()).filter(Boolean);
      myTeam = await (myTeam ? api.updateTeam(myTeam.id, payload) : api.createTeam(payload));
      selectedTeamId = myTeam.id;
      $('#team-dialog').close(); notify('Команда сохранена. Теперь можно отправить отклик в каталоге.');
      if (!$('#team').hidden) await renderTeam();
    }, $('#team-error'));
  });

  async function showTab(target) {
    document.querySelectorAll('[data-tab]').forEach((button) => {
      const active = button.dataset.tab === target;
      button.classList.toggle('is-active', active); button.setAttribute('aria-selected', String(active));
    });
    document.querySelectorAll('.tab-panel').forEach((panel) => {
      panel.hidden = panel.id !== target; panel.classList.toggle('is-active', panel.id === target);
    });
    if (target === 'catalog') await renderCatalog();
    if (target === 'business-proposals') await loadProposals();
    if (target === 'team') await renderTeam();
  }
  document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => run(null, () => showTab(button.dataset.tab))));
  function setStep(step) {
    currentStep = step;
    document.querySelectorAll('.wizard-step').forEach((button) => {
      const number = Number(button.dataset.step), complete = completedSteps.has(number) && number !== step;
      button.dataset.label ||= button.textContent;
      button.disabled = assistantBusy || number > unlockedStep;
      button.textContent = `${complete ? '✓ ' : ''}${button.dataset.label}`;
      button.classList.toggle('is-complete', complete);
      button.classList.toggle('is-active', number === step);
      if (Number(button.dataset.step) === step) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
    document.querySelectorAll('.wizard-panel').forEach((panel) => { panel.hidden = Number(panel.dataset.panel) !== step; });
  }
  document.querySelectorAll('.wizard-step').forEach((button) => button.addEventListener('click', () => setStep(Number(button.dataset.step))));
  function updatePublish() {
    $('#publish-button').disabled = assistantBusy || !($('#confirm-check').checked && card.title.trim() && card.topic.trim());
  }
  function renderFields() {
    $('#card-form').innerHTML = fields.map(([key, label]) => `<div class="field-block ${['contact', 'interaction_format'].includes(key) ? '' : 'full'}"><label for="field-${key}" id="label-${key}">${label}</label><textarea id="field-${key}" data-field="${key}" maxlength="${key === 'title' ? 200 : key === 'topic' ? 100 : key === 'contact' ? 500 : 5000}">${escape(card[key])}</textarea></div>`).join('');
  }
  async function refreshScore() {
    const version = ++scoreRevision;
    const result = await api.scoreCard({ card: { ...card } });
    if (version !== scoreRevision) return;
    const meta = levelMeta[result.level];
    $('#score-level').textContent = meta.label; $('#score-level').className = `level-badge level-${result.level}`;
    $('#score-value').textContent = result.score;
    $('#score-progress').style.width = `${result.score}%`; $('#score-progress').style.background = meta.color;
    $('#breakdown-list').innerHTML = result.breakdown.map((row) => `<li class="breakdown-item"><div class="breakdown-line"><strong>${escape(row.label)} · ${row.earned}/${row.max}${row.earned === row.max ? ' ✓' : ''}</strong><span>${escape(row.reason)}</span></div><span class="field-progress"><span style="width: ${row.max ? Math.round(row.earned / row.max * 100) : 0}%"></span></span></li>`).join('');
    $('#tips-list').innerHTML = result.missing.length ? result.missing.slice(0, 4).map((row) => `<li><strong>+${row.potential_points} ${plural(row.potential_points, ['балл', 'балла', 'баллов'])} · ${escape(result.breakdown.find((item) => item.field === row.field)?.label || row.field)}</strong><span>${escape(row.hint)}</span></li>`).join('') : '<li>Задача полностью готова 🎉</li>';
    for (const [key, label] of fields) {
      const row = result.breakdown.find((row) => row.field === key);
      $(`#label-${key}`).textContent = `${label} · ${row ? `${row.earned}/${row.max}${row.earned === row.max ? ' ✓' : ''}` : 'обязательно'}`;
    }
  }
  $('#card-form').addEventListener('input', (event) => {
    if (!event.target.dataset.field) return;
    card[event.target.dataset.field] = event.target.value;
    completedSteps.delete(4);
    $('#confirm-check').checked = false; updatePublish();
    ++scoreRevision; clearTimeout(scoreTimer);
    scoreTimer = setTimeout(() => run(null, refreshScore), 250);
  });
  onClick('#sample-button', async () => {
    $('#draft-text').value = 'Нужно вести учёт посещаемости кружков. Сейчас всё в бумажном журнале и листках. Хочется, чтобы родители видели, кто приходил, а руководитель видел статистику по группам.';
    $('#task-topic').value = 'образование'; publishedId = null; questions = [];
    completedSteps.clear(); unlockedStep = 1; setStep(1);
    card = Object.fromEntries(fields.map(([key]) => [key, ''])); renderFields();
    $('#confirm-check').checked = false; $('#publish-message').textContent = ''; updatePublish();
    $('#question-list').replaceChildren(); $('#questions-counter').textContent = '0 вопросов';
    await refreshScore();
  });
  onClick('#analyze-button', () => withAssistant('#analyze-button', 'Анализируем…', async () => {
    const result = await api.analyzeTask({ draft_text: $('#draft-text').value, topic: $('#task-topic').value });
    questions = result.questions;
    $('#question-list').innerHTML = questions.map((q) => `<div class="question-item"><small>${escape(q.field)}</small><label for="answer-${escape(q.id)}">${escape(q.question)}</label><textarea id="answer-${escape(q.id)}" maxlength="5000" placeholder="Напишите ответ..."></textarea></div>`).join('');
    $('#questions-counter').textContent = `${questions.length} ${plural(questions.length, ['вопрос', 'вопроса', 'вопросов'])}`;
    completedSteps.clear(); completedSteps.add(1); unlockedStep = 2;
    $('#confirm-check').checked = false; updatePublish();
    setStep(2); notify('');
  }));
  onClick('#build-card-button', () => withAssistant('#build-card-button', 'Собираем карточку…', async () => {
    const result = await api.buildCard({ draft_text: $('#draft-text').value, topic: $('#task-topic').value,
      answers: questions.map((q) => ({ question_id: q.id, field: q.field, answer: document.getElementById(`answer-${q.id}`).value })) });
    card = result.card; publishedId = null; $('#confirm-check').checked = false;
    completedSteps.add(2); unlockedStep = 4;
    renderFields(); updatePublish(); await refreshScore(); setStep(3);
    if (result.warnings.length) notify(result.warnings.join(' '));
  }));
  $('#confirm-check').addEventListener('change', updatePublish);
  onClick('#publish-button', async () => {
    if (!$('#confirm-check').checked || !card.title.trim() || !card.topic.trim()) return;
    const payload = { card: { ...card }, confirmed: $('#confirm-check').checked };
    const task = await (publishedId ? api.updateTask(publishedId, payload) : api.createTask(payload));
    publishedId = task.id;
    completedSteps.add(4); setStep(4);
    $('#publish-message').textContent = 'Задача сохранена и опубликована в каталоге.';
  });

  async function renderCatalog(append = false) {
    const version = ++catalogRevision;
    const tasks = await api.getTasks({ topic: $('#catalog-topic').value, level: $('#catalog-level').value,
      offset: append ? catalogTasks.length : 0, limit: 50 });
    if (version !== catalogRevision) return;
    catalogTasks = append ? [...catalogTasks, ...tasks] : tasks;
    $('#catalog-counter').textContent = `${catalogTasks.length} ${plural(catalogTasks.length, ['задача', 'задачи', 'задач'])}`;
    $('#catalog-more').hidden = tasks.length < 50;
    $('#catalog-list').innerHTML = catalogTasks.length ? catalogTasks.map((task) => {
      return `<article class="task-card level-card level-${task.level}"><div class="task-card-header"><div class="task-level-meta"><span class="level-badge level-${task.level}">${levelMeta[task.level].label}</span>${task.level === 'draft' ? '<span class="task-refinement">Требует уточнения</span>' : ''}</div><strong>${task.score}/100</strong></div><h3>${escape(task.title)}</h3><p class="task-topic">${escape(task.topic)}</p><p>${escape(task.need || 'Потребность пока не описана.')}</p><p class="task-readiness">${readiness[task.level]}</p><div class="task-card-footer"><span>${task.proposals_count} ${plural(task.proposals_count, ['отклик', 'отклика', 'откликов'])}</span><div class="task-actions"><button class="primary-button" type="button" data-action="apply" data-task-id="${escape(task.id)}">Откликнуться</button><button class="secondary-button" type="button" data-action="proposals" data-task-id="${escape(task.id)}">Смотреть отклики</button></div></div></article>`;
    }).join('') : '<p class="placeholder-text">По выбранным фильтрам задач пока нет.</p>';
  }
  for (const selector of ['#catalog-topic', '#catalog-level']) $(selector).addEventListener('change', () => run(null, () => renderCatalog()));
  onClick('#catalog-more', () => renderCatalog(true));
  $('#catalog-list').addEventListener('click', (event) => {
    const button = event.target.closest('[data-task-id]');
    if (!button) return;
    run(button, async () => {
      if (button.dataset.action === 'proposals') {
        await showTab('business-proposals'); $('#proposal-task').value = button.dataset.taskId; await renderProposals(); return;
      }
      await showTab('team');
      if (!availableTeams.length) { await openTeam(); notify('Сначала создайте команду.'); return; }
      const task = teamTasks.find((item) => item.id === button.dataset.taskId);
      if (task) showTaskDetails(task, true);
      else notify('Задача больше не опубликована. Обновите каталог.', true);
    });
  });
  async function loadProposals() {
    const tasks = [];
    let page;
    do { page = await api.getTasks({ include_drafts: true, offset: tasks.length, limit: 100 }); tasks.push(...page); } while (page.length === 100);
    const previous = $('#proposal-task').value;
    $('#proposal-task').innerHTML = tasks.map((task) => `<option value="${escape(task.id)}">${escape(task.title || 'Без названия')}${task.confirmed ? '' : ' (не опубликована)'}</option>`).join('');
    if (tasks.some((task) => task.id === previous)) $('#proposal-task').value = previous;
    $('#edit-task-button').disabled = !tasks.length;
    await renderProposals();
  }
  onClick('#edit-task-button', async () => {
    const taskId = $('#proposal-task').value;
    if (!taskId) return;
    const task = await api.getTask(taskId);
    card = task.card; publishedId = task.id; $('#confirm-check').checked = false;
    unlockedStep = 4; completedSteps.clear();
    $('#draft-text').value = card.context; $('#task-topic').value = card.topic;
    renderFields(); updatePublish(); await refreshScore(); await showTab('business-task'); setStep(3);
  });
  async function allTeams() {
    const result = [];
    let page;
    do { page = await api.getTeams({ offset: result.length, limit: 100 }); result.push(...page); } while (page.length === 100);
    return result;
  }
  async function renderProposals() {
    const version = ++proposalRevision;
    const taskId = $('#proposal-task').value;
    if (!taskId) { $('#proposal-list').innerHTML = '<p class="placeholder-text">Сначала опубликуйте задачу.</p>'; return; }
    const [proposals, teams] = await Promise.all([api.getProposals(taskId), allTeams()]);
    if (version !== proposalRevision) return;
    $('#proposal-list').innerHTML = proposals.length ? proposals.map((proposal) => {
      const team = teams.find((team) => team.id === proposal.team_id);
      const pending = proposal.status === 'pending';
      const progress = proposal.status === 'accepted' ? `<div class="action-row progress-actions">${Object.entries(stages).map(([stage, [label, points]]) => proposal.stages_done.includes(stage) ? `<span class="status-badge status-accepted">${label} ✓</span>` : `<button class="secondary-button" type="button" data-proposal-id="${escape(proposal.id)}" data-stage="${stage}">${label} +${points}</button>`).join('')}</div>` : '';
      return `<article class="proposal-card"><div class="proposal-header"><div><h3>${escape(team?.name || proposal.team_id)}</h3><span class="muted">${team?.points || 0} баллов команды</span></div><span class="status-badge status-${proposal.status}">${statuses[proposal.status]}</span></div><p><strong>Идея:</strong> ${escape(proposal.idea)}</p><p><strong>План:</strong> ${escape(proposal.plan)}</p>${proposal.prototype_url ? `<p><a href="${escape(proposal.prototype_url)}" target="_blank" rel="noopener noreferrer">Прототип ↗</a></p>` : ''}<div class="proposal-footer"><span>Срок: ${escape(proposal.deadline)}</span>${pending ? `<div class="action-row"><button class="primary-button" data-proposal-id="${escape(proposal.id)}" data-decision="accepted" type="button">Принять</button><button class="secondary-button" data-proposal-id="${escape(proposal.id)}" data-decision="rejected" type="button">Отклонить</button></div>` : ''}</div>${progress}</article>`;
    }).join('') : '<p class="placeholder-text">Откликов пока нет.</p>';
  }
  $('#proposal-task').addEventListener('change', () => run(null, renderProposals));
  $('#proposal-list').addEventListener('click', (event) => {
    const button = event.target.closest('[data-proposal-id]');
    if (!button) return;
    run(button, async () => {
      if (button.dataset.decision) await api.decideProposal(button.dataset.proposalId, { decision: button.dataset.decision });
      else await api.updateProgress(button.dataset.proposalId, { stage: button.dataset.stage });
      await renderProposals(); notify('Изменения сохранены.');
    });
  });

  function recommendTasks(team, tasks) {
    const interests = (team?.interests || []).map((item) => item.toLowerCase());
    const skills = [...(team?.skills || []), ...(team?.tech || [])].map((item) => item.toLowerCase());
    return tasks.filter((task) => task.score >= 40 && ['working', 'ready', 'priority'].includes(task.level)).map((task) => {
      const haystack = `${task.title} ${task.topic} ${task.need}`.toLowerCase();
      const matched = [...new Set([...interests.filter((item) => haystack.includes(item)), ...skills.filter((item) => haystack.includes(item))])];
      const score = Math.min(100, (interests.includes(task.topic.toLowerCase()) ? 70 : 0) + Math.min(matched.length * 10, 30));
      return { task, score, matched };
    }).sort((left, right) => right.score - left.score || right.task.score - left.task.score);
  }
  window.recommendTasks = recommendTasks;

  async function allPages(fetchPage, params = {}) {
    const items = [];
    let page;
    do { page = await fetchPage({ ...params, offset: items.length, limit: 100 }); items.push(...page); } while (page.length === 100);
    return items;
  }

  async function renderTeam() {
    const version = ++teamRevision;
    const [teams, tasks] = await Promise.all([allTeams(), allPages(api.getTasks)]);
    if (version !== teamRevision) return;
    const team = teams.find((item) => item.id === selectedTeamId) || teams[0];
    const proposals = team ? await allPages(api.getTeamProposals, { team_id: team.id }) : [];
    if (version !== teamRevision) return;
    availableTeams = teams; teamTasks = tasks; teamProposals = proposals; selectedTeamId = team?.id || null;
    const options = teams.map((item) => `<option value="${escape(item.id)}">${escape(item.name)}</option>`).join('');
    $('#team-select').innerHTML = options; $('#response-team').innerHTML = options;
    $('#team-select').value = selectedTeamId || ''; $('#response-team').value = selectedTeamId || '';
    $('#team-heading-name').textContent = team?.name || 'Команда';
    $('#team-summary').textContent = team ? `${team.points} ${plural(team.points, ['балл', 'балла', 'баллов'])} команды` : 'Создайте команду кнопкой «Команды» вверху страницы.';
    $('#team-profile').innerHTML = team ? [['interests', 'Интересы'], ['skills', 'Навыки'], ['tech', 'Технологии']].map(([key, label]) => `<div class="team-stat"><span>${label}</span><div class="profile-chips">${team[key].map((item) => `<span>${escape(item)}</span>`).join('')}</div></div>`).join('') : '';
    const recommendations = team ? recommendTasks(team, tasks) : [];
    $('#recommendation-counter').textContent = `${recommendations.length} ${plural(recommendations.length, ['задача', 'задачи', 'задач'])}`;
    $('#recommendation-list').innerHTML = recommendations.length ? recommendations.map(({ task, score, matched }) => `<article class="task-card recommendation-card"><div class="task-card-header"><span class="level-badge level-${task.level}">${levelMeta[task.level].label}</span><strong>${score}% совпадение</strong></div><h3>${escape(task.title)}</h3><p class="task-topic">${escape(task.topic)}</p><p>${escape(task.need || 'Потребность пока не описана.')}</p><div class="match-summary"><span>Совпало:</span><div class="match-tags">${(matched.length ? matched : ['подходит по уровню']).map((item) => `<span>${escape(item)}</span>`).join('')}</div></div><button class="primary-button" type="button" data-task-id="${escape(task.id)}">Подробнее / Откликнуться</button></article>`).join('') : '<p class="placeholder-text">Подходящих задач пока нет. Все опубликованные задачи доступны в каталоге.</p>';
    $('#team-proposals-list').innerHTML = proposals.length ? proposals.map((proposal) => `<article class="team-proposal-row"><div><strong>${escape(tasks.find((task) => task.id === proposal.task_id)?.title || proposal.task_id)}</strong><span class="muted">${escape(proposal.deadline)}</span></div><span class="status-badge status-${proposal.status}">${statuses[proposal.status]}</span></article>`).join('') : '<p class="placeholder-text">Команда пока никуда не откликалась.</p>';
    if (selectedTask && team) {
      const task = tasks.find((item) => item.id === selectedTask.id);
      if (task) showTaskDetails(task);
      else { selectedTask = null; $('#team-detail-panel').hidden = true; }
    } else $('#team-detail-panel').hidden = true;
  }

  function showTaskDetails(task, reset = false) {
    if (reset || selectedTask?.id !== task.id) {
      $('#response-form').reset();
      ['idea', 'plan', 'deadline', 'prototype'].forEach((key) => { $(`#response-${key}-error`).textContent = ''; });
    }
    selectedTask = task;
    const team = availableTeams.find((item) => item.id === selectedTeamId);
    const match = recommendTasks(team, [task])[0] || { score: 0, matched: [] };
    const existing = teamProposals.find((proposal) => proposal.task_id === task.id);
    $('#response-team').value = selectedTeamId || '';
    $('#detail-title').textContent = task.title;
    $('#detail-content').innerHTML = `<div class="detail-meta"><span class="level-badge level-${task.level}">${levelMeta[task.level].label}</span><strong>${task.score}/100</strong></div><p class="task-topic">${escape(task.topic)}</p><p>${escape(task.need || 'Потребность пока не описана.')}</p><div class="match-box"><span>Совпадение с профилем: ${match.score}%</span><strong>${escape(match.matched.join(' · ') || 'Совпадения не найдены — отклик всё равно доступен')}</strong></div>`;
    $('#response-form').hidden = Boolean(existing) || !team;
    $('#response-message').textContent = existing ? `Команда уже отправила отклик: ${statuses[existing.status]}.` : '';
    $('#team-detail-panel').hidden = false;
  }
  $('#team-select').addEventListener('change', () => {
    selectedTeamId = $('#team-select').value;
    run(null, renderTeam);
  });
  $('#response-team').addEventListener('change', () => {
    selectedTeamId = $('#response-team').value;
    run(null, renderTeam);
  });
  $('#recommendation-list').addEventListener('click', (event) => {
    const button = event.target.closest('[data-task-id]');
    if (!button) return;
    const task = teamTasks.find((item) => item.id === button.dataset.taskId);
    if (task) showTaskDetails(task, true);
  });
  onClick('#close-detail-button', () => { selectedTask = null; $('#team-detail-panel').hidden = true; });
  $('#response-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!selectedTask || !selectedTeamId) return;
    const payload = { team_id: selectedTeamId, idea: $('#response-idea').value.trim(), plan: $('#response-plan').value.trim(), deadline: $('#response-deadline').value, prototype_url: $('#response-prototype').value.trim() };
    const errors = {}, now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    if (payload.idea.length < 20) errors.idea = 'Идея должна содержать минимум 20 символов.';
    if (payload.plan.length < 20) errors.plan = 'План должен содержать минимум 20 символов.';
    if (!payload.deadline || payload.deadline < today) errors.deadline = 'Срок не может быть в прошлом.';
    try { if (!['http:', 'https:'].includes(new URL(payload.prototype_url).protocol)) throw new Error(); }
    catch { errors.prototype = 'Укажите ссылку, начинающуюся с http:// или https://.'; }
    for (const key of ['idea', 'plan', 'deadline', 'prototype']) $(`#response-${key}-error`).textContent = errors[key] || '';
    if (Object.keys(errors).length) return;
    const taskId = selectedTask.id, button = $('#response-submit-button');
    run(button, async () => {
      button.textContent = 'Отправка…';
      try {
        await api.createProposal(taskId, payload);
        await renderTeam();
        notify('Отклик отправлен. Решение принимает бизнес.');
      } finally { button.textContent = 'Отправить отклик'; }
    }, $('#response-message'));
  });

  renderFields(); updatePublish(); setStep(1);
  run(null, async () => {
    const health = await api.getHealth();
    $('#mode-label').textContent = health.mode === 'demo' ? 'Деморежим · без ИИ'
      : health.ai_configured ? 'Помощник: OpenAI' : 'OpenAI · требуется настройка';
    await refreshScore();
  });
});
