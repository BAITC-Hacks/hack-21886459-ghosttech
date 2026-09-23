document.addEventListener('DOMContentLoaded', () => {
  const fallbackFieldHints = {
    title: { label: 'Название', max: 0, hint_empty: 'Добавьте короткое название задачи — без него публикация невозможна.', hint_partial: '' },
    topic: { label: 'Тема', max: 0, hint_empty: 'Выберите тему — по ней студенты фильтруют каталог.', hint_partial: '' },
    context: { label: 'Контекст', max: 10, hint_empty: 'Опишите, как всё устроено сейчас: кто и как решает эту задачу сегодня.', hint_partial: 'Добавьте деталей о текущей ситуации: что именно происходит и где неудобно.' },
    need: { label: 'Потребность', max: 10, hint_empty: 'Сформулируйте, что именно нужно изменить или улучшить.', hint_partial: 'Уточните потребность: какую проблему должно снять решение.' },
    data: { label: 'Данные и материалы', max: 20, hint_empty: 'Укажите, какие данные есть: выгрузки, таблицы, примеры документов, источники.', hint_partial: 'Уточните формат и объём данных: например, «Excel за 2 месяца, ~300 строк».' },
    expected_result: { label: 'Ожидаемый результат', max: 15, hint_empty: 'Опишите, что команда должна сдать в итоге: прототип, дашборд, бот, отчёт.', hint_partial: 'Конкретизируйте результат: что именно должно работать в конце.' },
    success_criteria: { label: 'Критерии успеха', max: 15, hint_empty: 'Добавьте измеримый признак успеха, например «отметка посещаемости занимает до 1 минуты».', hint_partial: 'Добавьте число или процент — так критерий станет измеримым.' },
    constraints: { label: 'Ограничения', max: 10, hint_empty: 'Укажите сроки, технологии, доступы или другие границы работы.', hint_partial: 'Уточните ограничения: срок, стек, доступ к системам.' },
    users: { label: 'Пользователи', max: 10, hint_empty: 'Опишите, кто будет пользоваться решением: сотрудники, клиенты, родители.', hint_partial: 'Уточните пользователей: роли, сколько их, в какой ситуации они работают.' },
    contact: { label: 'Контакт', max: 5, hint_empty: 'Укажите контакт для связи с командой (email).', hint_partial: '' },
    interaction_format: { label: 'Формат взаимодействия', max: 5, hint_empty: 'Опишите формат: как часто созвоны, как даёте обратную связь.', hint_partial: '' }
  };

  window.fieldHints = fallbackFieldHints;
  const fieldHintsReady = fetch('../prompts/field_hints.json')
    .then((response) => response.ok ? response.json() : Promise.reject(new Error('field_hints.json недоступен')))
    .then((hints) => {
      window.fieldHints = hints;
      return hints;
    })
    .catch(() => fallbackFieldHints);

  const tabButtons = document.querySelectorAll('[data-tab]');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const target = button.dataset.tab;

      tabButtons.forEach((item) => {
        const active = item === button;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-selected', String(active));
      });

      tabPanels.forEach((panel) => {
        const active = panel.id === target;
        panel.hidden = !active;
        panel.classList.toggle('is-active', active);
      });

      if (target === 'catalog') renderCatalog();
      if (target === 'business-proposals') {
        if (!proposalTask.options.length) {
          proposalTask.innerHTML = (window.mockApi?.listTasks?.() || [])
            .map((task) => `<option value="${task.id}">${task.title}</option>`)
            .join('');
        }
        renderProposals();
      }
      if (target === 'team') renderTeam();
    });
  });

  const modeLabel = document.querySelector('#mode-label');
  if (modeLabel) {
    modeLabel.textContent = window.api && window.api.USE_MOCK ? 'Режим: Демо-режим без ключа' : 'Режим: AI';
  }

  const CARD_FIELDS = [
    'title',
    'topic',
    'context',
    'need',
    'users',
    'data',
    'constraints',
    'expected_result',
    'success_criteria',
    'contact',
    'interaction_format'
  ];

  const wizardSteps = Array.from(document.querySelectorAll('.wizard-step'));
  const wizardPanels = Array.from(document.querySelectorAll('.wizard-panel'));
  const draftText = document.querySelector('#draft-text');
  const taskTopic = document.querySelector('#task-topic');
  const analyzeButton = document.querySelector('#analyze-button');
  const sampleButton = document.querySelector('#sample-button');
  const buildCardButton = document.querySelector('#build-card-button');
  const questionList = document.querySelector('#question-list');
  const questionsCounter = document.querySelector('#questions-counter');
  const cardForm = document.querySelector('#card-form');
  const scoreLevel = document.querySelector('#score-level');
  const scoreValue = document.querySelector('#score-value');
  const scoreProgress = document.querySelector('#score-progress');
  const breakdownList = document.querySelector('#breakdown-list');
  const tipsList = document.querySelector('#tips-list');
  const confirmCheck = document.querySelector('#confirm-check');
  const publishButton = document.querySelector('#publish-button');
  const publishMessage = document.querySelector('#publish-message');
  const catalogTopic = document.querySelector('#catalog-topic');
  const catalogLevel = document.querySelector('#catalog-level');
  const catalogCounter = document.querySelector('#catalog-counter');
  const catalogList = document.querySelector('#catalog-list');
  const proposalTask = document.querySelector('#proposal-task');
  const proposalList = document.querySelector('#proposal-list');
  const teamSelect = document.querySelector('#team-select');
  const teamName = document.querySelector('#team-name');
  const teamSummary = document.querySelector('#team-summary');
  const teamProfile = document.querySelector('#team-profile');
  const recommendationCounter = document.querySelector('#recommendation-counter');
  const recommendationList = document.querySelector('#recommendation-list');
  const teamProposalsList = document.querySelector('#team-proposals-list');
  const teamDetailPanel = document.querySelector('#team-detail-panel');
  const detailTitle = document.querySelector('#detail-title');
  const detailContent = document.querySelector('#detail-content');
  const closeDetailButton = document.querySelector('#close-detail-button');
  const responseForm = document.querySelector('#response-form');
  const responseIdea = document.querySelector('#response-idea');
  const responsePlan = document.querySelector('#response-plan');
  const responseDeadline = document.querySelector('#response-deadline');
  const responseMessage = document.querySelector('#response-message');

  let currentStep = 1;
  let questions = [];
  let cardState = {
    title: '',
    topic: '',
    context: '',
    need: '',
    users: '',
    data: '',
    constraints: '',
    expected_result: '',
    success_criteria: '',
    contact: '',
    interaction_format: ''
  };
  let selectedTeam = null;
  let selectedRecommendation = null;

  function recommendTasks(team, tasks) {
    const allowedLevels = new Set(['working', 'ready', 'priority']);
    const interests = (team?.interests || []).map((item) => item.toLowerCase());
    const skills = (team?.skills || []).map((item) => item.toLowerCase());

    return tasks
      .filter((task) => allowedLevels.has(task.level))
      .map((task) => {
        const haystack = `${task.title} ${task.topic} ${task.need}`.toLowerCase();
        const matched = [...new Set([
          ...interests.filter((interest) => task.topic.toLowerCase() === interest || haystack.includes(interest)),
          ...skills.filter((skill) => haystack.includes(skill))
        ])];
        const topicMatch = interests.includes(task.topic.toLowerCase());
        const score = Math.min(100, (topicMatch ? 70 : 0) + Math.min(matched.length * 10, 30));
        return { task, score, matched };
      })
      .sort((left, right) => right.score - left.score || right.task.score - left.task.score);
  }

  window.recommendTasks = recommendTasks;

  const levelLabels = {
    draft: 'Черновик',
    working: 'Рабочая',
    ready: 'Готовая',
    priority: 'Приоритетная'
  };

  const statusLabels = {
    pending: 'На рассмотрении',
    accepted: 'Принят',
    rejected: 'Отклонён'
  };

  const renderCatalog = () => {
    const tasks = window.mockApi?.listTasks?.({ topic: catalogTopic.value, level: catalogLevel.value }) || [];
    catalogCounter.textContent = `${tasks.length} ${tasks.length === 1 ? 'задача' : 'задач'}`;
    catalogList.innerHTML = tasks.length ? tasks.map((task) => `
      <article class="task-card">
        <div class="task-card-header">
          <span class="level-badge level-${task.level}">${levelLabels[task.level] || task.level}</span>
          <strong>${task.score}/100</strong>
        </div>
        <h3>${task.title}</h3>
        <p class="task-topic">${task.topic}</p>
        <p>${task.need || 'Потребность пока не описана.'}</p>
        <div class="task-card-footer">
          <span>${task.proposals_count} откликов</span>
          <button class="secondary-button view-proposals" type="button" data-task-id="${task.id}">Смотреть отклики</button>
        </div>
      </article>
    `).join('') : '<p class="placeholder-text">По выбранным фильтрам задач пока нет.</p>';

    catalogList.querySelectorAll('.view-proposals').forEach((button) => {
      button.addEventListener('click', () => {
        proposalTask.value = button.dataset.taskId;
        renderProposals();
        document.querySelector('[data-tab="business-proposals"]').click();
      });
    });
  };

  const renderProposals = () => {
    const task = proposalTask.value ? window.mockApi?.getTask?.(proposalTask.value) : null;
    const teams = window.mockApi?.getTeams?.() || [];
    const proposals = task?.proposals || [];
    proposalList.innerHTML = proposals.length ? proposals.map((proposal) => {
      const team = teams.find((item) => item.id === proposal.team_id);
      const isPending = proposal.status === 'pending';
      return `
        <article class="proposal-card">
          <div class="proposal-header">
            <div><h3>${team?.name || proposal.team_id}</h3><span class="muted">${team?.points || 0} баллов команды</span></div>
            <span class="status-badge status-${proposal.status}">${statusLabels[proposal.status] || proposal.status}</span>
          </div>
          <p><strong>Идея:</strong> ${proposal.idea}</p>
          <p><strong>План:</strong> ${proposal.plan}</p>
          <div class="proposal-footer">
            <span>Срок: ${proposal.deadline}</span>
            ${isPending ? `<div class="action-row"><button class="primary-button proposal-decision" data-proposal-id="${proposal.id}" data-decision="accepted" type="button">Принять</button><button class="secondary-button proposal-decision" data-proposal-id="${proposal.id}" data-decision="rejected" type="button">Отклонить</button></div>` : ''}
          </div>
        </article>
      `;
    }).join('') : '<p class="placeholder-text">У этой задачи пока нет откликов.</p>';

    proposalList.querySelectorAll('.proposal-decision').forEach((button) => {
      button.addEventListener('click', () => {
        window.mockApi.decideProposal(button.dataset.proposalId, { decision: button.dataset.decision });
        renderProposals();
        renderCatalog();
      });
    });
  };

  const renderTeamProfile = () => {
    if (!selectedTeam) return;
    teamName.textContent = selectedTeam.name;
    teamSummary.textContent = `${selectedTeam.points} баллов команды · ${selectedTeam.interests.join(', ')}`;
    teamProfile.innerHTML = `
      <div class="team-stat"><span>Интересы</span><strong>${selectedTeam.interests.join(' · ')}</strong></div>
      <div class="team-stat"><span>Навыки</span><strong>${selectedTeam.skills.join(' · ')}</strong></div>
      <div class="team-stat"><span>Технологии</span><strong>${selectedTeam.tech.join(' · ')}</strong></div>
    `;
  };

  const renderTeamProposals = () => {
    if (!selectedTeam) return;
    const tasks = window.mockApi?.listTasks?.() || [];
    const taskMap = new Map(tasks.map((task) => [task.id, task]));
    const proposals = window.api?.getProposals
      ? window.api.getProposals({ team_id: selectedTeam.id })
      : window.mockApi?.getProposals?.({ team_id: selectedTeam.id }) || [];
    const render = (items) => {
      teamProposalsList.innerHTML = items.length ? items.map((proposal) => {
        const task = taskMap.get(proposal.task_id);
        return `<article class="team-proposal-row"><div><strong>${task?.title || proposal.task_id}</strong><span class="muted">${proposal.deadline || 'Срок не указан'}</span></div><span class="status-badge status-${proposal.status}">${statusLabels[proposal.status] || proposal.status}</span></article>`;
      }).join('') : '<p class="placeholder-text">Команда пока никуда не откликалась.</p>';
    };
    if (proposals?.then) proposals.then(render);
    else render(proposals);
  };

  const showRecommendationDetails = (recommendation) => {
    selectedRecommendation = recommendation;
    const { task, score, matched } = recommendation;
    const existingProposal = (window.mockApi?.getProposals?.({ team_id: selectedTeam.id }) || [])
      .find((proposal) => proposal.task_id === task.id);
    detailTitle.textContent = task.title;
    detailContent.innerHTML = `
      <div class="detail-meta"><span class="level-badge level-${task.level}">${levelLabels[task.level]}</span><strong>${task.score}/100</strong></div>
      <p class="task-topic">${task.topic}</p>
      <p>${task.need || 'Потребность пока не описана.'}</p>
      <div class="match-box"><span>Совпадение с профилем: ${score}%</span><strong>${matched.length ? matched.join(' · ') : 'Общее направление'}</strong></div>
    `;
    responseForm.hidden = Boolean(existingProposal);
    responseMessage.textContent = existingProposal ? `Команда уже отправила отклик: ${statusLabels[existingProposal.status] || existingProposal.status}.` : '';
    teamDetailPanel.hidden = false;
  };

  const renderTeam = () => {
    const teams = window.mockApi?.getTeams?.() || [];
    if (!teams.length) return;
    if (!teamSelect.options.length) {
      teamSelect.innerHTML = teams.map((team) => `<option value="${team.id}">${team.name}</option>`).join('');
    }
    selectedTeam = teams.find((team) => team.id === teamSelect.value) || teams[0];
    teamSelect.value = selectedTeam.id;
    renderTeamProfile();
    const recommendations = recommendTasks(selectedTeam, window.mockApi?.listTasks?.() || []);
    recommendationCounter.textContent = `${recommendations.length} задач`;
    recommendationList.innerHTML = recommendations.length ? recommendations.map(({ task, score, matched }) => `
      <article class="task-card recommendation-card">
        <div class="task-card-header"><span class="level-badge level-${task.level}">${levelLabels[task.level]}</span><strong>${score}% совпадение</strong></div>
        <h3>${task.title}</h3>
        <p class="task-topic">${task.topic}</p>
        <p>${task.need || 'Потребность пока не описана.'}</p>
        <div class="match-tags">${(matched.length ? matched : ['подходит по уровню']).map((item) => `<span>${item}</span>`).join('')}</div>
        <button class="primary-button recommendation-details" type="button" data-task-id="${task.id}">Подробнее / Откликнуться</button>
      </article>
    `).join('') : '<p class="placeholder-text">Подходящих задач пока нет.</p>';
    recommendationList.querySelectorAll('.recommendation-details').forEach((button) => {
      button.addEventListener('click', () => showRecommendationDetails(recommendations.find((item) => item.task.id === button.dataset.taskId)));
    });
    renderTeamProposals();
  };

  const setStep = (step) => {
    currentStep = step;
    wizardSteps.forEach((button) => {
      const active = Number(button.dataset.step) === step;
      button.classList.toggle('is-active', active);
    });

    wizardPanels.forEach((panel) => {
      const visible = Number(panel.dataset.panel) === step;
      panel.hidden = !visible;
    });
  };

  const sampleDrafts = [
    {
      topic: 'образование',
      text: 'Нужно вести учёт посещаемости кружков. Сейчас всё в бумажном журнале и листках. Хочется, чтобы родители видели, кто приходил, а руководитель видел статистику по группам.'
    }
  ];

  const updatePublishButton = () => {
    const canPublish = confirmCheck.checked && cardState.title && cardState.topic;
    publishButton.disabled = !canPublish;
  };

  const renderCardForm = () => {
    const fields = [
      { key: 'title', label: 'Название задачи', full: true },
      { key: 'topic', label: 'Тема', full: true },
      { key: 'context', label: 'Контекст и проблема', full: true },
      { key: 'need', label: 'Потребность', full: true },
      { key: 'users', label: 'Пользователи и участники', full: true },
      { key: 'data', label: 'Данные и материалы', full: true },
      { key: 'constraints', label: 'Ограничения', full: true },
      { key: 'expected_result', label: 'Ожидаемый результат', full: true },
      { key: 'success_criteria', label: 'Критерии успеха', full: true },
      { key: 'contact', label: 'Контакт', full: false },
      { key: 'interaction_format', label: 'Формат взаимодействия', full: false }
    ];

    cardForm.innerHTML = fields.map((field) => {
      const value = cardState[field.key] || '';
      const wrapperClass = field.full ? 'field-block full' : 'field-block';
      const fieldHint = window.fieldHints[field.key] || {};
      const maxScore = fieldHint.max ?? 0;
      const earned = field.key === 'title' || field.key === 'topic' ? 0 : (window.mockApi?.scoreCard ? window.mockApi.scoreCard({ card: cardState }).breakdown.find((item) => item.field === field.key)?.earned || 0 : 0);
      const scoreLabel = field.key === 'title' || field.key === 'topic' ? 'обязательно' : `${earned}/${maxScore}`;
      const check = earned >= maxScore && maxScore > 0 ? ' ✓' : '';

      return `
        <div class="${wrapperClass}">
          <label for="field-${field.key}">${fieldHint.label || field.label} · ${scoreLabel}${check}</label>
          <textarea id="field-${field.key}" data-field="${field.key}">${value}</textarea>
        </div>
      `;
    }).join('');

    cardForm.querySelectorAll('textarea[data-field]').forEach((textarea) => {
      textarea.addEventListener('input', (event) => {
        const field = event.target.dataset.field;
        cardState[field] = event.target.value;
        refreshScore();
        updatePublishButton();
      });
    });
  };

  const levelMeta = {
    draft: { label: 'Черновик', className: 'level-draft', color: '#9CA3AF' },
    working: { label: 'Рабочая', className: 'level-working', color: '#3B82F6' },
    ready: { label: 'Готовая', className: 'level-ready', color: '#10B981' },
    priority: { label: 'Приоритетная', className: 'level-priority', color: '#F59E0B' }
  };

  const animateScore = (target) => {
    const current = Number(scoreValue.dataset.value || 0);
    const start = Number.isFinite(current) ? current : 0;
    const step = Math.max(1, Math.round(Math.abs(target - start) / 20));

    let index = start;
    const timer = setInterval(() => {
      if (index >= target) {
        scoreValue.textContent = String(target);
        scoreValue.dataset.value = String(target);
        clearInterval(timer);
        return;
      }
      index += step;
      if (index > target) index = target;
      scoreValue.textContent = String(index);
      scoreValue.dataset.value = String(index);
    }, 16);
  };

  const refreshScore = async () => {
    const payload = { card: { ...cardState } };
    const result = window.mockApi?.scoreCard ? window.mockApi.scoreCard(payload) : { score: 0, level: 'draft', breakdown: [], missing: [] };

    const level = levelMeta[result.level] || levelMeta.draft;
    const targetValue = result.score ?? 0;
    scoreLevel.textContent = level.label;
    scoreLevel.className = `level-badge ${level.className}`;
    scoreProgress.style.width = `${Math.min(targetValue, 100)}%`;
    scoreProgress.style.background = level.color;

    breakdownList.innerHTML = (result.breakdown || []).map((item) => {
      const fieldHint = window.fieldHints[item.field] || {};
      const label = fieldHint.label || item.label || item.field;
      const check = item.max > 0 && item.earned >= item.max ? ' ✓' : '';
      const progress = item.max ? Math.round((item.earned / item.max) * 100) : 0;
      return `<li class="breakdown-item"><div class="breakdown-line"><strong>${label} · ${item.earned}/${item.max}${check}</strong><span>${item.reason || ''}</span></div><span class="field-progress"><span style="width: ${progress}%"></span></span></li>`;
    }).join('') || '<li>Пустой рейтинг</li>';

    const tips = (result.missing || []).slice(0, 4).map((item) => {
      const fieldHint = window.fieldHints[item.field] || {};
      return `<li><strong>+${item.potential_points} баллов · ${fieldHint.label || item.field}</strong><span>${item.hint}</span></li>`;
    });
    tipsList.innerHTML = tips.length ? tips.join('') : '<li>Задача полностью готова 🎉</li>';

    animateScore(targetValue);
  };

  const renderQuestions = () => {
    if (!questions.length) {
      questionList.innerHTML = '<p class="placeholder-text">Сначала нажмите «Проанализировать» и система предложит уточняющие вопросы.</p>';
      questionsCounter.textContent = '0 вопросов';
      return;
    }

    questionList.innerHTML = questions.map((question) => `
      <div class="question-item">
        <small>${question.field}</small>
        <label for="answer-${question.id}">${question.question}</label>
        <textarea id="answer-${question.id}" data-question-id="${question.id}" data-field="${question.field}" placeholder="Напишите ответ..."></textarea>
      </div>
    `).join('');

    questionsCounter.textContent = `${questions.length} вопросов`;

    questionList.querySelectorAll('textarea[data-question-id]').forEach((textarea) => {
      textarea.addEventListener('input', (event) => {
        const field = event.target.dataset.field;
        const answer = event.target.value;
        const questionId = event.target.dataset.questionId;

        const existing = cardState[field] || '';
        if (existing !== answer) {
          cardState[field] = answer;
          renderCardForm();
          refreshScore();
        }

        const question = questions.find((item) => item.id === questionId);
        if (question) {
          question.answer = answer;
        }
      });
    });
  };

  const collectBuiltCard = async () => {
    const payload = {
      draft_text: draftText.value,
      topic: taskTopic.value,
      answers: questions.map((question) => ({
        question_id: question.id,
        field: question.field,
        answer: document.querySelector(`#answer-${question.id}`)?.value || ''
      }))
    };

    const result = window.mockApi?.buildCard ? window.mockApi.buildCard(payload) : { card: { ...cardState }, warnings: [] };
    Object.assign(cardState, result.card || {});
    renderCardForm();
    await refreshScore();
    setStep(3);
  };

  analyzeButton.addEventListener('click', async () => {
    const payload = {
      draft_text: draftText.value,
      topic: taskTopic.value
    };

    const result = window.mockApi?.analyze ? window.mockApi.analyze(payload) : { questions: [], filled_fields: [], missing_fields: [], mode: 'demo' };
    questions = result.questions || [];
    renderQuestions();
    setStep(2);
  });

  sampleButton.addEventListener('click', () => {
    const sample = sampleDrafts[0];
    draftText.value = sample.text;
    taskTopic.value = sample.topic;
    questions = [];
    renderQuestions();
  });

  buildCardButton.addEventListener('click', async () => {
    await collectBuiltCard();
  });

  confirmCheck.addEventListener('change', updatePublishButton);
  catalogTopic.addEventListener('change', renderCatalog);
  catalogLevel.addEventListener('change', renderCatalog);
  proposalTask.addEventListener('change', renderProposals);
  teamSelect.addEventListener('change', renderTeam);
  closeDetailButton.addEventListener('click', () => {
    teamDetailPanel.hidden = true;
    selectedRecommendation = null;
  });

  responseForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!selectedTeam || !selectedRecommendation) return;
    const proposal = window.mockApi.createProposal(selectedRecommendation.task.id, {
      team_id: selectedTeam.id,
      idea: responseIdea.value.trim(),
      plan: responsePlan.value.trim(),
      deadline: responseDeadline.value,
      prototype_url: ''
    });
    responseMessage.textContent = `Отклик отправлен: ${proposal.id}.`;
    responseForm.hidden = true;
    renderTeamProposals();
  });

  publishButton.addEventListener('click', async () => {
    if (!cardState.title || !cardState.topic) {
      publishMessage.textContent = 'Заполните название и тему задачи перед публикацией.';
      return;
    }

    const result = window.mockApi?.createTask ? window.mockApi.createTask({ card: cardState, confirmed: true }) : { id: 't1', card: cardState, score: 0, level: 'draft' };
    publishMessage.textContent = `Задача опубликована: ${result.id}. Место в каталоге будет обновлено после проверки.`;
  });

  renderCardForm();
  refreshScore();
  updatePublishButton();
  setStep(1);
  fieldHintsReady.then(() => {
    renderCardForm();
    refreshScore();
  });
});
