/* Translate interface text without replacing elements, form values or handlers. */
(() => {
  const normalize = (value) => String(value).replace(/\s+/g, ' ').trim();
  const dictionary = window.GhostTranslations || {};
  for (const [key, value] of Object.entries(dictionary)) { const lower = key.toLocaleLowerCase('ru'); if (!dictionary[lower]) dictionary[lower] = value; }
  const originals = new WeakMap();
  const escaped = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = Object.entries(dictionary).filter(([key]) => /\{\w+\}/.test(key)).map(([key, values]) => {
    const names = [...key.matchAll(/\{(\w+)\}/g)].map((match) => match[1]);
    return { expression: new RegExp('^' + key.split(/\{\w+\}/).map(escaped).join('(.+?)') + '$'), names, values };
  });
  let language = 'ru';
  try { const saved = localStorage.getItem('ghosttech.language'); if (['ru', 'kk', 'en'].includes(saved)) language = saved; } catch { /* Storage is optional. */ }
  function translate(value, depth = 0) {
    if (language === 'ru' || !value || depth > 5) return value;
    const text = normalize(value), index = language === 'kk' ? 0 : 1;
    let result = dictionary[text]?.[index];
    if (result === undefined) {
      for (const pattern of patterns) {
        const match = text.match(pattern.expression);
        if (match) {
          result = pattern.values[index].replace(/\{(\w+)\}/g, (_, name) => translate(match[pattern.names.indexOf(name) + 1], depth + 1));
          break;
        }
      }
    }
    if (result === undefined && /\s[·→—]\s/.test(text)) result = text.split(/(\s[·→—]\s)/).map((part) => translate(part, depth + 1)).join('');
    if (result === undefined && /^[✓⭐]\s/.test(text)) result = text.slice(0, 2) + translate(text.slice(2), depth + 1);
    if (result === undefined && /:/.test(text)) result = text.split(/(:\s*)/).map((part) => translate(part, depth + 1)).join('');
    if (result === undefined && / \(\d+\)$/.test(text)) result = text.replace(/^(.*?)( \(\d+\))$/, (_, label, count) => translate(label, depth + 1) + count);
    if (result === undefined && text.endsWith(':')) result = translate(text.slice(0, -1), depth + 1) + ':';
    if (result === undefined) return value;
    if (language === 'en') result = result.replace(/(^|[^\d.])1 (open tasks|tasks|points|applications|questions|members|participants|projects|profiles)\b/g, (_, prefix, noun) => `${prefix}1 ${noun.slice(0, -1)}`);
    return value.replace(/\S[\s\S]*\S|\S/, () => result);
  }
  function updateValue(node, key, current, write) {
    let record = originals.get(node);
    if (!record) { record = {}; originals.set(node, record); }
    let entry = record[key];
    if (!entry || current !== entry.rendered) {
      let source = current;
      // Some controls cache their visible label while a request is pending.
      for (const [russian, values] of Object.entries(dictionary)) {
        if (values.includes(normalize(current))) { source = current.replace(/\S[\s\S]*\S|\S/, russian); break; }
      }
      entry = record[key] = { source, rendered: current };
    }
    const result = translate(entry.source);
    entry.rendered = result;
    if (current !== result) write(result);
  }
  function visit(root) {
    if (root.nodeType === 3) {
      if (!root.parentElement?.closest('script, style, textarea, [translate="no"], [data-no-i18n]')) updateValue(root, 'text', root.nodeValue, (value) => { root.nodeValue = value; });
      return;
    }
    if (root.nodeType !== 1 || root.matches('script, style, textarea, [translate="no"], [data-no-i18n]')) {
      if (root.nodeType === 1 && root.matches('textarea')) for (const attr of ['placeholder', 'aria-label']) if (root.hasAttribute(attr)) updateValue(root, attr, root.getAttribute(attr), (value) => root.setAttribute(attr, value));
      return;
    }
    for (const attr of ['placeholder', 'title', 'aria-label']) if (root.hasAttribute(attr)) updateValue(root, attr, root.getAttribute(attr), (value) => root.setAttribute(attr, value));
    for (const child of root.childNodes) visit(child);
  }
  const observer = new MutationObserver((records) => {
    const roots = new Set();
    for (const record of records) {
      if (record.type === 'childList') for (const node of record.addedNodes) roots.add(node);
      else roots.add(record.target);
    }
    roots.forEach(visit);
  });
  function apply() {
    document.documentElement.lang = language;
    visit(document.documentElement);
    document.querySelectorAll('[data-language]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.language === language)));
  }
  window.GhostI18n = {
    t: translate,
    language: () => language,
    locale: () => ({ ru: 'ru-RU', kk: 'kk-KZ', en: 'en-GB' })[language],
    originalText: (element) => [...element.childNodes].map((node) => originals.get(node)?.text?.source ?? node.textContent).join(''),
    setLanguage(next) {
      if (!['ru', 'kk', 'en'].includes(next)) return;
      language = next;
      try { localStorage.setItem('ghosttech.language', language); } catch { /* Storage is optional. */ }
      apply();
      document.dispatchEvent(new CustomEvent('languagechange', { detail: { language } }));
    },
  };
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-language]').forEach((button) => button.addEventListener('click', () => window.GhostI18n.setLanguage(button.dataset.language)));
    observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'aria-label', 'title'] });
    apply();
  });
})();
