const form = document.querySelector('#note-form');
const input = document.querySelector('#note-text');
const list = document.querySelector('#notes');
const error = document.querySelector('#error');

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Ошибка API (${response.status}). Попробуйте ещё раз.`);
  return response.status === 204 ? null : response.json();
}

async function loadNotes() {
  const notes = await request('/api/notes');
  list.replaceChildren();
  if (!notes.length) {
    const empty = document.createElement('li');
    empty.textContent = 'Пока нет заметок.';
    list.append(empty);
  }
  for (const note of notes) {
    const item = document.createElement('li');
    const text = document.createElement('span');
    text.textContent = note.text;
    const button = document.createElement('button');
    button.textContent = 'Удалить';
    button.addEventListener('click', async () => {
      error.textContent = '';
      button.disabled = true;
      try {
        await request(`/api/notes/${note.id}`, { method: 'DELETE' });
        await loadNotes();
      } catch (err) { error.textContent = err.message; }
      finally { button.disabled = false; }
    });
    item.append(text, button);
    list.append(item);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  error.textContent = '';
  if (!input.value.trim()) { error.textContent = 'Введите текст заметки.'; return; }
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    await request('/api/notes', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: input.value.trim() }),
    });
    form.reset();
    await loadNotes();
    input.focus();
  } catch (err) { error.textContent = err.message; }
  finally { button.disabled = false; }
});

async function init() {
  try {
    await request('/api/health');
    document.querySelector('#status').textContent = '● API и SQLite подключены';
    await loadNotes();
  } catch (err) {
    document.querySelector('#status').textContent = 'Не удалось загрузить данные';
    error.textContent = err.message;
  }
}
init();
