document.addEventListener('DOMContentLoaded', () => {
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
      const maxScore = { context: 10, need: 10, data: 20, expected_result: 15, success_criteria: 15, constraints: 10, users: 10, contact: 5, interaction_format: 5 }[field.key] ?? 0;
      const earned = field.key === 'title' || field.key === 'topic' ? 0 : (window.mockApi?.scoreCard ? window.mockApi.scoreCard({ card: cardState }).breakdown.find((item) => item.field === field.key)?.earned || 0 : 0);
      const scoreLabel = field.key === 'title' || field.key === 'topic' ? 'обязательно' : `${earned}/${maxScore}`;
      const check = earned >= maxScore && maxScore > 0 ? ' ✓' : '';

      return `
        <div class="${wrapperClass}">
          <label for="field-${field.key}">${field.label} · ${scoreLabel}${check}</label>
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
      const label = item.label.replace('_', ' ');
      const check = item.earned >= item.max ? ' ✓' : '';
      return `<li><strong>${label}</strong> · ${item.earned}/${item.max}${check}</li>`;
    }).join('') || '<li>Пустой рейтинг</li>';

    const tips = (result.missing || []).slice(0, 4).map((item) => `<li>+${item.potential_points} баллов: ${item.hint}</li>`);
    tipsList.innerHTML = tips.length ? tips.join('') : '<li>Поля уже достаточно полные. Можно публиковать задачу.</li>';

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
});
