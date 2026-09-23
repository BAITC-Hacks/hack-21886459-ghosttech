document.addEventListener('DOMContentLoaded', () => {
  const $ = (selector) => document.querySelector(selector);
  const api = window.api;
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
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
  const stages = { prototype: ['Прототип', 10], testing: ['Тестирование', 20], final: ['Финал', 30] };
  let myTeam = null, availableTeams = [], questions = [], publishedId = null, currentTaskId = null;
  let card = Object.fromEntries(fields.map(([key]) => [key, '']));
  let catalogTasks = [], catalogRevision = 0, proposalRevision = 0, scoreRevision = 0, scoreTimer;

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
      $('#team-dialog').close(); notify('Команда сохранена. Теперь можно отправить отклик в каталоге.');
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
  }
  document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => run(null, () => showTab(button.dataset.tab))));
  function setStep(step) {
    document.querySelectorAll('.wizard-step').forEach((button) => {
      button.classList.toggle('is-active', Number(button.dataset.step) === step);
      if (Number(button.dataset.step) === step) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
    document.querySelectorAll('.wizard-panel').forEach((panel) => { panel.hidden = Number(panel.dataset.panel) !== step; });
  }
  document.querySelectorAll('.wizard-step').forEach((button) => button.addEventListener('click', () => setStep(Number(button.dataset.step))));
  function updatePublish() {
    $('#publish-button').disabled = !($('#confirm-check').checked && card.title.trim() && card.topic.trim());
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
    $('#breakdown-list').innerHTML = result.breakdown.map((row) => `<li><strong>${escape(row.label)}</strong> · ${row.earned}/${row.max}${row.earned === row.max ? ' ✓' : ''}</li>`).join('');
    $('#tips-list').innerHTML = result.missing.length ? result.missing.slice(0, 4).map((row) => `<li>+${row.potential_points} баллов: ${escape(row.hint)}</li>`).join('') : '<li>Поля уже достаточно полные. Можно публиковать задачу.</li>';
    for (const [key, label] of fields) {
      const row = result.breakdown.find((row) => row.field === key);
      $(`#label-${key}`).textContent = `${label} · ${row ? `${row.earned}/${row.max}${row.earned === row.max ? ' ✓' : ''}` : 'обязательно'}`;
    }
  }
  $('#card-form').addEventListener('input', (event) => {
    if (!event.target.dataset.field) return;
    card[event.target.dataset.field] = event.target.value;
    $('#confirm-check').checked = false; updatePublish();
    ++scoreRevision; clearTimeout(scoreTimer);
    scoreTimer = setTimeout(() => run(null, refreshScore), 250);
  });
  onClick('#sample-button', async () => {
    $('#draft-text').value = 'Нужно вести учёт посещаемости кружков. Сейчас всё в бумажном журнале и листках. Хочется, чтобы родители видели, кто приходил, а руководитель видел статистику по группам.';
    $('#task-topic').value = 'образование'; publishedId = null; questions = [];
    card = Object.fromEntries(fields.map(([key]) => [key, ''])); renderFields();
    $('#confirm-check').checked = false; $('#publish-message').textContent = ''; updatePublish();
    $('#question-list').replaceChildren(); $('#questions-counter').textContent = '0 вопросов';
    await refreshScore();
  });
  onClick('#analyze-button', async () => {
    const result = await api.analyzeTask({ draft_text: $('#draft-text').value, topic: $('#task-topic').value });
    questions = result.questions;
    $('#question-list').innerHTML = questions.map((q) => `<div class="question-item"><small>${escape(q.field)}</small><label for="answer-${escape(q.id)}">${escape(q.question)}</label><textarea id="answer-${escape(q.id)}" maxlength="5000" placeholder="Напишите ответ..."></textarea></div>`).join('');
    $('#questions-counter').textContent = `${questions.length} вопросов`;
    setStep(2); notify('');
  });
  onClick('#build-card-button', async () => {
    const result = await api.buildCard({ draft_text: $('#draft-text').value, topic: $('#task-topic').value,
      answers: questions.map((q) => ({ question_id: q.id, field: q.field, answer: document.getElementById(`answer-${q.id}`).value })) });
    card = result.card; publishedId = null; $('#confirm-check').checked = false;
    renderFields(); updatePublish(); await refreshScore(); setStep(3);
    if (result.warnings.length) notify(result.warnings.join(' '));
  });
  $('#confirm-check').addEventListener('change', updatePublish);
  onClick('#publish-button', async () => {
    if (!$('#confirm-check').checked || !card.title.trim() || !card.topic.trim()) return;
    const payload = { card: { ...card }, confirmed: $('#confirm-check').checked };
    const task = await (publishedId ? api.updateTask(publishedId, payload) : api.createTask(payload));
    publishedId = task.id;
    $('#publish-message').textContent = 'Задача сохранена и опубликована в каталоге.';
  });

  async function renderCatalog(append = false) {
    const version = ++catalogRevision;
    const tasks = await api.getTasks({ topic: $('#catalog-topic').value, level: $('#catalog-level').value,
      offset: append ? catalogTasks.length : 0, limit: 50 });
    if (version !== catalogRevision) return;
    catalogTasks = append ? [...catalogTasks, ...tasks] : tasks;
    $('#catalog-counter').textContent = `${catalogTasks.length} задач`;
    $('#catalog-more').hidden = tasks.length < 50;
    $('#catalog-list').innerHTML = catalogTasks.length ? catalogTasks.map((task) => {
      return `<article class="task-card"><div class="task-card-header"><span class="level-badge level-${task.level}">${levelMeta[task.level].label}</span><strong>${task.score}/100</strong></div><h3>${escape(task.title)}</h3><p class="task-topic">${escape(task.topic)}</p><p>${escape(task.need || 'Потребность пока не описана.')}</p><div class="task-card-footer"><span>${task.proposals_count} откликов</span><button class="secondary-button" type="button" data-action="proposals" data-task-id="${escape(task.id)}">Смотреть отклики</button><button class="primary-button" type="button" data-action="apply" data-task-id="${escape(task.id)}">Откликнуться</button></div></article>`;
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
      const task = await api.getTask(button.dataset.taskId);
      availableTeams = await allTeams();
      if (!availableTeams.length) { await openTeam(); notify('Сначала создайте команду.'); return; }
      currentTaskId = task.id; $('#proposal-form').reset(); $('#proposal-error').textContent = '';
      $('#proposal-target').textContent = task.card.title;
      $('#proposal-team').innerHTML = availableTeams.map((team) => `<option value="${escape(team.id)}">${escape(team.name)}</option>`).join('');
      $('#proposal-dialog').showModal();
    });
  });
  $('#proposal-form').addEventListener('submit', (event) => {
    event.preventDefault(); $('#proposal-error').textContent = '';
    run(event.currentTarget.querySelector('[type="submit"]'), async () => {
      const values = Object.fromEntries(new FormData($('#proposal-form')));
      await api.createProposal(currentTaskId, values);
      $('#proposal-dialog').close(); notify('Отклик отправлен. Он доступен во вкладке «Бизнес: отклики».');
      await renderCatalog();
    }, $('#proposal-error'));
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

  renderFields(); updatePublish(); setStep(1);
  run(null, async () => {
    const health = await api.getHealth();
    $('#mode-label').textContent = health.mode === 'demo' ? 'Режим: Демо-режим без ключа' : 'Режим: AI';
    await refreshScore();
  });
});
