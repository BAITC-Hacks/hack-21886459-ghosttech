window.mockApi = (() => {
  const fs = window.__mockData || {};
  const draftData = fs.drafts || [];
  const cardData = fs.cards || [];
  const teamData = fs.teams || [];
  const proposalData = fs.proposals || [];

  const getCards = () => window.__mockData?.cards || cardData;
  const getTeams = () => window.__mockData?.teams || teamData;
  const getProposalData = () => window.__mockData?.proposals || proposalData;

  const FIELD_CONFIG = {
    context: { max: 10, full: 40, half: 10 },
    need: { max: 10, full: 40, half: 10 },
    data: { max: 20, full: 30, half: 20 },
    expected_result: { max: 15, full: 30, half: 15 },
    success_criteria: { max: 15, full: 1, half: 10 },
    constraints: { max: 10, full: 20, half: 10 },
    users: { max: 10, full: 20, half: 10 },
    contact: { max: 5, full: 1, half: 0 },
    interaction_format: { max: 5, full: 1, half: 0 }
  };

  const normalizeText = (value) => String(value ?? '').trim();

  const scoreField = (field, value) => {
    const entry = FIELD_CONFIG[field];
    if (!entry) return 0;
    const text = normalizeText(value);
    if (!text) return 0;
    if (field === 'success_criteria') {
      return /\d|%/.test(text) ? entry.max : entry.half;
    }
    if (text.length >= entry.full) return entry.max;
    if (text.length >= entry.half) return Math.floor(entry.max / 2);
    return 0;
  };

  const scoreCard = (card) => {
    const breakdown = Object.keys(FIELD_CONFIG).map((field) => {
      const value = card[field] || '';
      const earned = scoreField(field, value);
      const max = FIELD_CONFIG[field].max;
      const label = field.replace(/_/g, ' ');
      return { field, label, max, earned, reason: 'Проверка по формуле рейтинга' };
    });

    const total = breakdown.reduce((sum, row) => sum + row.earned, 0);
    const score = Math.min(total, 100);
    const level = score >= 90 ? 'priority' : score >= 70 ? 'ready' : score >= 40 ? 'working' : 'draft';
    const missing = Object.keys(FIELD_CONFIG)
      .filter((field) => scoreField(field, card[field] || '') === 0)
      .map((field) => ({
        field,
        hint: field === 'success_criteria' ? 'Добавьте измеримый критерий успеха: например, «сократить время на 30%».' : 'Добавьте более подробную информацию, чтобы повысить рейтинг задачи.',
        potential_points: FIELD_CONFIG[field].max
      }));

    return { score, level, breakdown, missing };
  };

  const findTaskById = (id) => getCards().find((task) => task.id === id);
  const findProposalById = (id) => getProposalData().find((proposal) => proposal.id === id);

  const makeTaskPayload = (task) => ({
    id: task.id,
    card: task.card,
    score: task.score,
    level: task.level,
    breakdown: task.breakdown,
    created_at: task.created_at,
    confirmed: task.confirmed,
    proposals: task.proposals || []
  });

  return {
    health: () => ({ status: 'ok', mode: 'demo' }),

    analyze: ({ draft_text, topic }) => {
      const text = normalizeText(draft_text || '');
      const questions = [
        { id: 'q1', field: 'data', question: 'Какие данные и материалы уже есть у вас для решения задачи?' },
        { id: 'q2', field: 'context', question: 'Что именно происходит сейчас и в чём проблема бизнеса?' },
        { id: 'q3', field: 'need', question: 'Какую конкретную потребность или цель должен закрыть продукт?' },
        { id: 'q4', field: 'expected_result', question: 'Какой результат вы ожидаете после внедрения решения?' },
        { id: 'q5', field: 'success_criteria', question: 'Как вы будете понимать, что задача решена успешно? Укажите метрику или процент.' }
      ].filter((q) => text.length > 0 || topic);

      return {
        questions: questions.slice(0, 5),
        filled_fields: [],
        missing_fields: ['data', 'context', 'need', 'expected_result', 'success_criteria'],
        mode: 'demo'
      };
    },

    buildCard: ({ draft_text, topic, answers = [] }) => {
      const base = {
        title: '',
        topic: topic || '',
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

      answers.forEach(({ field, answer }) => {
        if (field && field in base) {
          base[field] = normalizeText(answer);
        }
      });

      const draft = normalizeText(draft_text || '');
      if (draft && !base.context) {
        base.context = draft.slice(0, 250);
      }
      if (!base.title && topic) {
        base.title = topic.charAt(0).toUpperCase() + topic.slice(1).toLowerCase();
      }

      const warnings = [];
      if (!base.title || !base.topic) {
        warnings.push('Название или тема не заполнены.');
      }
      return { card: base, warnings };
    },

    scoreCard: ({ card }) => scoreCard(card || {}),

    createTask: ({ card, confirmed = false }) => {
      const safeCard = { ...card };
      const id = `t${cardData.length + 1}`;
      const scored = scoreCard(safeCard);
      const task = {
        id,
        card: safeCard,
        score: scored.score,
        level: scored.level,
        breakdown: scored.breakdown,
        missing: scored.missing,
        created_at: new Date().toISOString(),
        confirmed,
        proposals: []
      };
      cardData.push(task);
      return makeTaskPayload(task);
    },

    updateTask: (id, { card, confirmed = false }) => {
      const found = findTaskById(id);
      if (!found) {
        const error = { error: { code: 404, message: 'Задача не найдена.' } };
        throw new Error(JSON.stringify(error));
      }
      const scored = scoreCard(card || found.card);
      found.card = { ...card };
      found.score = scored.score;
      found.level = scored.level;
      found.breakdown = scored.breakdown;
      found.missing = scored.missing;
      found.confirmed = confirmed;
      return makeTaskPayload(found);
    },

    listTasks: ({ topic = '', level = '' } = {}) => {
      const tasks = getCards().filter((task) => {
        const matchesTopic = !topic || task.card.topic === topic;
        const matchesLevel = !level || task.level === level;
        return matchesTopic && matchesLevel;
      });
      return tasks
        .map((task) => ({
          id: task.id,
          title: task.card.title || 'Без названия',
          topic: task.card.topic || '',
          score: task.score,
          level: task.level,
          need: task.card.need || '',
          proposals_count: task.proposals.length,
          created_at: task.created_at
        }))
        .sort((a, b) => b.score - a.score);
    },

    getTask: (id) => {
      const task = findTaskById(id);
      if (!task) {
        const error = { error: { code: 404, message: 'Задача не найдена.' } };
        throw new Error(JSON.stringify(error));
      }
      return {
        ...makeTaskPayload(task),
        proposals: getProposalData().filter((proposal) => proposal.task_id === id)
      };
    },

    getTeams,

    getProposals: ({ team_id = '' } = {}) => getProposalData()
      .filter((proposal) => !team_id || proposal.team_id === team_id)
      .map((proposal) => ({ ...proposal })),

    createProposal: (taskId, payload) => {
      const task = findTaskById(taskId);
      if (!task) {
        const error = { error: { code: 404, message: 'Задача не найдена.' } };
        throw new Error(JSON.stringify(error));
      }
      const proposalStore = getProposalData();
      const newProposal = {
        id: `p${proposalStore.length + 1}`,
        task_id: taskId,
        team_id: payload.team_id,
        idea: payload.idea,
        plan: payload.plan,
        deadline: payload.deadline,
        prototype_url: payload.prototype_url,
        status: 'pending'
      };
      proposalStore.push(newProposal);
      task.proposals.push(newProposal.id);
      return newProposal;
    },

    decideProposal: (proposalId, { decision }) => {
      const proposal = findProposalById(proposalId);
      if (!proposal) {
        const error = { error: { code: 404, message: 'Отклик не найден.' } };
        throw new Error(JSON.stringify(error));
      }
      proposal.status = decision === 'accepted' ? 'accepted' : 'rejected';
      return proposal;
    },

    updateProgress: (proposalId, { stage }) => {
      const proposal = findProposalById(proposalId);
      if (!proposal) {
        const error = { error: { code: 404, message: 'Отклик не найден.' } };
        throw new Error(JSON.stringify(error));
      }
      if (proposal.status !== 'accepted') {
        const error = { error: { code: 409, message: 'Отклик должен быть принят бизнесом.' } };
        throw new Error(JSON.stringify(error));
      }
      const stageMap = { prototype: 10, testing: 20, final: 30 };
      const stagesDone = new Set((proposal.stages_done || []).slice());
      if (stagesDone.has(stage)) {
        const error = { error: { code: 409, message: 'Этап уже подтверждён.' } };
        throw new Error(JSON.stringify(error));
      }
      stagesDone.add(stage);
      proposal.stages_done = Array.from(stagesDone);
      const pointsTotal = Array.from(stagesDone).reduce((sum, item) => sum + (stageMap[item] || 0), 0);
      return {
        proposal_id: proposalId,
        team_id: proposal.team_id,
        stages_done: proposal.stages_done,
        points_total: pointsTotal
      };
    }
  };
})();

if (typeof window !== 'undefined') {
  window.__mockData = {
    drafts: [
      { id: 'd1', topic: 'образование', text: 'Нужно вести учёт посещаемости кружков. Сейчас всё в бумажном журнале и листках. Хочется, чтобы родители видели, кто приходил, а руководитель видел статистику по группам.', completeness: 'low' },
      { id: 'd2', topic: 'образование', text: 'Нужно помогать школам быстрее собирать заявки на кружки и распределять детей по группам. Сейчас много звонков и Excel, сложно понять, кто уже записан и кто остался в листе ожидания.', completeness: 'medium' },
      { id: 'd3', topic: 'ритейл', text: 'Планируем улучшить работу магазина с онлайн-заказами. Участники хотели бы видеть, сколько заказов не собрали, где задержки и как быстро реагировать на претензии.', completeness: 'medium' },
      { id: 'd4', topic: 'логистика', text: 'Проблема в доставке между складами, нужно понять, почему теряются маршруты и сколько времени уходит на каждую смену. Нам важно сократить простой транспорта и ускорить сбор.', completeness: 'high' },
      { id: 'd5', topic: 'городские сервисы', text: 'Нужно сделать систему для контроля заявок на ремонт улиц и дворов. Пользователи пишут о проблемах, а сотрудники хотят видеть очередность и статус решения.', completeness: 'high' }
    ],
    cards: [
      {
        id: 't1',
        card: {
          title: 'Система учёта посещаемости кружков',
          topic: 'образование',
          context: 'Школа ведёт кружки в нескольких группах, а данные по посещаемости собираются вручную в бумажный журнал. Руководитель не всегда видит, кто пропустил занятие и кто уже записан в резервный список.',
          need: 'Нужно быстро фиксировать посещаемость, видеть динамику по группам и вовремя сообщать родителям об отсутствии ребёнка.',
          users: 'Руководитель кружков, педагоги, родители, администратор школы.',
          data: 'Данные о расписании, посещаемости, списках учеников, заявках и контактах родителей.',
          constraints: 'Нужно работать в пределах текущих регламентов школы и не усложнять процесс для педагогов.',
          expected_result: 'В системе все занятия будут отмечаться в одном месте, а отчёты станут доступны за 1–2 клика.',
          success_criteria: 'Сокращение времени учёта посещаемости на 40% и отсутствие потерянных записей.',
          contact: 'school@example.com',
          interaction_format: 'Веб-интерфейс для педагога и родителей'
        },
        score: 82,
        level: 'ready',
        created_at: '2026-09-20T10:00:00Z',
        proposals: ['p1']
      },
      {
        id: 't2',
        card: {
          title: 'Платформа заявок на кружки',
          topic: 'образование',
          context: 'В школе одновременно открываются несколько потоков кружков, а сотрудники обрабатывают заявки через Excel и телефонные сообщения.',
          need: 'Нужно уменьшить ручную работу и сделать прозрачный список свободных мест и ожидания.',
          users: 'Администратор, педагог, родители, менеджер по развитию.',
          data: 'Список детей, их возраст, предпочтения, дата заявки и наличие мест в группе.',
          constraints: 'Данные должны храниться без нарушения требований к персональным данным и не перегружать педагогов.',
          expected_result: 'Родители видят свободные места, а администратор быстро распределяет заявки по группам.',
          success_criteria: '90% заявок обрабатываются без ручного перепроверения.',
          contact: 'adm@example.com',
          interaction_format: 'Сайт и внутренний кабинет администратора'
        },
        score: 69,
        level: 'working',
        created_at: '2026-09-21T09:30:00Z',
        proposals: ['p2']
      },
      {
        id: 't3',
        card: {
          title: 'Управление онлайн-заказами в магазине',
          topic: 'ритейл',
          context: 'Магазин получает много заказов через сайт и соцсети. Часть заказов остаётся не собранной, а менеджер не всегда понимает причину задержки.',
          need: 'Сделать единую картину статусов заказов, чтобы быстро видеть задержки и корректировать сборку.',
          users: 'Менеджер магазина, кладовщик, курьер, клиентский сервис.',
          data: 'Заказы, статусы сборки, время оплаты, данные адреса и комментарии клиента.',
          constraints: 'Система должна быть понятной для сотрудников без дополнительной длительной настройки.',
          expected_result: 'Каждый заказ будет иметь понятный статус и таймлайн по этапам сборки.',
          success_criteria: 'Уменьшение времени реакции на задержки на 30%.',
          contact: 'retail@example.com',
          interaction_format: 'Личный кабинет сотрудника и уведомления'
        },
        score: 91,
        level: 'priority',
        created_at: '2026-09-18T08:45:00Z',
        proposals: ['p3']
      },
      {
        id: 't4',
        card: {
          title: 'Аналитика маршрутов доставки между складами',
          topic: 'логистика',
          context: 'Компания ведёт маршруты в Excel, а иногда теряется информация о расходе времени на одну смену. Решение нужно быстро находить причины задержек.',
          need: 'Понимать, где возникают простои и как улучшить маршрутизацию между складами.',
          users: 'Диспетчер, логист, начальник отдела перевозок.',
          data: 'Маршруты, время выезда и прибытия, данные по машинам, объём заказов и нарушения графика.',
          constraints: 'Система не должна зависеть от сторонних сервисов для основного учёта маршрутов.',
          expected_result: 'Диспетчер получает понятную карту задержек и видит проблемные участки маршрута.',
          success_criteria: 'Сокращение среднего времени в пути на 15%.',
          contact: 'logistics@example.com',
          interaction_format: 'Дашборд и отчёты в браузере'
        },
        score: 43,
        level: 'working',
        created_at: '2026-09-19T14:10:00Z',
        proposals: ['p4']
      },
      {
        id: 't5',
        card: {
          title: 'Учет заявок на ремонт инфраструктуры',
          topic: 'городские сервисы',
          context: 'Жители подают заявки через разные каналы, управленцы замечают, что часть обращений теряется и сложно понять реальную очередь по районам.',
          need: 'Нужен единый учёт всех обращений и понятная система приоритета по срочности.',
          users: 'Жители, диспетчеры, сотрудники городских служб, руководитель департамента.',
          data: 'Текст заявки, район, категория проблемы, статус, сроки и ответственный исполнитель.',
          constraints: 'Сервис должен работать в условиях ограниченного бюджета и без сложной интеграции с внешними системами.',
          expected_result: 'Все запросы фиксируются и видны по статусам и приоритетам.',
          success_criteria: 'Снижение числа потерянных обращений до 0 и ускорение ответа на срочные заявки на 25%.',
          contact: 'city@example.com',
          interaction_format: 'Портал для жителей и рабочая панель для сотрудников'
        },
        score: 26,
        level: 'draft',
        created_at: '2026-09-22T17:00:00Z',
        proposals: ['p5']
      }
    ],
    teams: [
      { id: 'team1', name: 'EduPulse', interests: ['образование', 'аналитика', 'цифровые сервисы'], skills: ['UX', 'product', 'дизайн'], tech: ['Figma', 'web'], points: 120 },
      { id: 'team2', name: 'RetailFlow', interests: ['ритейл', 'логистика', 'маркетплейсы'], skills: ['аналитика', 'операционный процесс'], tech: ['Python', 'SQL'], points: 80 },
      { id: 'team3', name: 'CityOps', interests: ['городские сервисы', 'госуслуги', 'карта города'], skills: ['администрирование', 'модерация'], tech: ['React', 'maps'], points: 95 },
      { id: 'team4', name: 'LogiBoost', interests: ['логистика', 'доставка', 'маршруты'], skills: ['операции', 'автоматизация'], tech: ['Python', 'API'], points: 140 },
      { id: 'team5', name: 'EdTech Lab', interests: ['образование', 'процессы', 'онлайн-обучение'], skills: ['продукт', 'коммуникации', 'аналитика'], tech: ['JavaScript', 'web'], points: 110 }
    ],
    proposals: [
      { id: 'p1', task_id: 't1', team_id: 'team1', idea: 'Сделаем простой интерфейс для педагогов и родителей, где видно посещаемость и список пропусков.', plan: 'Сначала соберём список полей, затем настроим учёт посещаемости и автоматические уведомления.', deadline: '2026-10-05', prototype_url: 'https://example.com/prototype/edu-visit', status: 'accepted', stages_done: ['prototype', 'testing', 'final'] },
      { id: 'p2', task_id: 't2', team_id: 'team5', idea: 'Построим систему распределения заявок на кружки по пулам и очередям ожидания.', plan: 'Нарисуем MVP списка заявок, затем добавим фильтры и статусы по группам.', deadline: '2026-10-08', prototype_url: 'https://example.com/prototype/circle-flow', status: 'pending', stages_done: [] },
      { id: 'p3', task_id: 't3', team_id: 'team2', idea: 'Сделаем дашборд статусов заказов и аналитический экран для задержек сборки.', plan: 'Построим карточки заказов, фильтры и таймлайн сборки по этапам.', deadline: '2026-10-12', prototype_url: 'https://example.com/prototype/retail-flow', status: 'rejected', stages_done: [] },
      { id: 'p4', task_id: 't4', team_id: 'team4', idea: 'Сконцентрируемся на визуализации маршрутов и причин задержек между складами.', plan: 'Соберём реестр маршрутов и аномалий, затем покажем проблемные участки на карте.', deadline: '2026-10-15', prototype_url: 'https://example.com/prototype/logi-map', status: 'accepted', stages_done: ['prototype'] },
      { id: 'p5', task_id: 't5', team_id: 'team3', idea: 'Делаем единый канал заявок для жителей и удобный статусный экран для сотрудников.', plan: 'Реализуем модель приоритетов и рабочий поток для исполнителей.', deadline: '2026-10-10', prototype_url: 'https://example.com/prototype/city-requests', status: 'pending', stages_done: [] }
    ]
  };

}
