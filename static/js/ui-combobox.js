/* F88 UI Kit — Combobox (tìm kiếm + chọn trong cùng một ô, dữ liệu tải từ server). Xem docs/ui-kit/components/combobox.md */
(() => {
  'use strict';
  const instances = new WeakMap();
  let uid = 0;
  const csv = text => (text || '').split(',').map(part => part.trim()).filter(Boolean);
  const closeOthers = except => document.querySelectorAll('[data-ui-combobox].is-open').forEach(wrapper => {
    if (wrapper !== except) instances.get(wrapper)?.close();
  });

  const init = wrapper => {
    if (instances.has(wrapper)) return;
    const cfg = wrapper.dataset;
    if (!cfg.source) return;
    const free = 'free' in cfg;   // gõ tự do: ô nhập chính là field gửi đi, danh sách chỉ là gợi ý
    const valueInput = cfg.valueInput ? document.querySelector(cfg.valueInput) : null;
    const specialInput = cfg.specialInput ? document.querySelector(cfg.specialInput) : null;
    const [filterName, filterSelector] = (cfg.filter || '').split(/:(.+)/);
    const filterEl = filterSelector ? document.querySelector(filterSelector) : null;
    const filterIgnore = csv(cfg.filterIgnore);
    const idKey = cfg.idKey || 'id';
    const labelKey = cfg.labelKey || 'label';
    const titleKey = cfg.titleKey || labelKey;
    const metaKeys = csv(cfg.metaKeys);
    const metaEmpty = (cfg.metaEmpty || '').split('|');
    const asideKeys = csv(cfg.asideKeys);
    const minChars = Number(cfg.min) || 1;
    const delay = Number(cfg.delay) || 220;
    const id = `ui-combobox-${++uid}`;
    const placeholder = cfg.placeholder || 'Tìm kiếm...';

    const el = (tag, className, attrs = {}) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      Object.entries(attrs).forEach(([key, val]) => node.setAttribute(key, val));
      return node;
    };
    const field = el('div', 'ui-combobox-field');
    const icon = el('span', 'ui-combobox-icon', {'aria-hidden': 'true'});
    const input = el('input', 'ui-combobox-input', {
      type: 'text', role: 'combobox', autocomplete: 'off', placeholder, 'aria-expanded': 'false',
      'aria-controls': `${id}-list`, 'aria-autocomplete': 'list', 'aria-label': cfg.label || placeholder,
    });
    const clearBtn = el('button', 'ui-combobox-clear', {type: 'button', 'aria-label': cfg.clearLabel || 'Bỏ chọn'});
    clearBtn.textContent = '×'; clearBtn.hidden = true;
    if (free) { if (cfg.name) input.name = cfg.name; input.value = cfg.value || ''; input.removeAttribute('aria-autocomplete'); input.setAttribute('aria-autocomplete', 'list'); }
    field.append(icon, input, clearBtn);
    const menu = el('div', 'ui-combobox-menu'); menu.hidden = true;
    const status = el('p', 'ui-combobox-status');
    const list = el('ul', 'ui-combobox-options', {role: 'listbox', id: `${id}-list`});
    const footer = el('button', 'ui-combobox-special', {type: 'button', role: 'option'});
    footer.hidden = !cfg.specialLabel; footer.textContent = cfg.specialLabel || '';
    menu.append(status, list, footer);
    wrapper.append(field, menu);

    let selected = null;      // {id, label, item} | {special: true, label}
    let results = [];
    let active = -1;
    let timer = null;
    let controller = null;

    const emit = (name, detail) => wrapper.dispatchEvent(new CustomEvent(`ui-combobox:${name}`, {bubbles: true, detail}));
    const writeValue = value => {
      if (valueInput && valueInput.value !== value) { valueInput.value = value; valueInput.dispatchEvent(new Event('change', {bubbles: true})); }
    };
    const writeSpecial = flag => {
      if (specialInput && specialInput.value !== flag) { specialInput.value = flag; specialInput.dispatchEvent(new Event('change', {bubbles: true})); }
    };
    const paint = () => {
      wrapper.classList.toggle('is-filled', Boolean(selected));
      wrapper.classList.toggle('is-special', Boolean(selected?.special));
      clearBtn.hidden = !selected && !input.value;
      wrapper.classList.toggle('is-filled', Boolean(selected) || (free && Boolean(input.value)));
    };
    const options = () => [...list.querySelectorAll('.ui-combobox-option'), ...(footer.hidden ? [] : [footer])];
    const setActive = (index, wrap = false) => {
      const items = options();
      active = !items.length || (index < 0 && !wrap) ? -1 : (index + items.length) % items.length;
      items.forEach((item, i) => { item.classList.toggle('is-active', i === active); item.setAttribute('aria-selected', String(i === active)); });
      if (active >= 0) { items[active].scrollIntoView({block: 'nearest'}); input.setAttribute('aria-activedescendant', items[active].id); }
      else input.removeAttribute('aria-activedescendant');
    };
    const setStatus = text => { status.textContent = text; status.hidden = !text; };

    const close = () => {
      menu.hidden = true; wrapper.classList.remove('is-open', 'is-up'); input.setAttribute('aria-expanded', 'false'); setActive(-1);
    };
    const open = () => {
      closeOthers(wrapper);
      if (!menu.hidden) return;
      if (free && !results.length && !status.textContent) return;
      menu.hidden = false; wrapper.classList.add('is-open'); input.setAttribute('aria-expanded', 'true');
      const rect = wrapper.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom;
      wrapper.classList.toggle('is-up', below < Math.min(menu.offsetHeight, 330) + 12 && rect.top > below);
    };

    const render = () => {
      list.replaceChildren();
      results.forEach((item, index) => {
        const li = el('li', 'ui-combobox-option', {role: 'option', id: `${id}-opt-${index}`, 'aria-selected': 'false'});
        const main = el('div', 'ui-combobox-main');
        const title = el('div', 'ui-combobox-title'); title.textContent = item[titleKey] || '-';
        main.append(title);
        if (metaKeys.length) {
          const meta = el('div', 'ui-combobox-meta');
          meta.textContent = metaKeys.map((key, i) => item[key] || metaEmpty[i] || '').filter(Boolean).join(' · ');
          main.append(meta);
        }
        li.append(main);
        const asideText = asideKeys.map(key => item[key]).filter(Boolean);
        if (asideText.length) {
          const aside = el('div', 'ui-combobox-aside');
          asideText.forEach(text => { const line = el('div'); line.textContent = text; aside.append(line); });
          li.append(aside);
        }
        li._item = item;
        list.append(li);
      });
      setActive(results.length && !free ? 0 : -1);
    };

    const params = extra => {
      const query = new URLSearchParams(extra);
      const filterValue = (filterEl?.value || '').trim();
      if (filterName && filterValue && !filterIgnore.includes(filterValue)) query.set(filterName, filterValue);
      return query;
    };
    const fetchJson = async query => {
      controller?.abort();
      controller = new AbortController();
      const response = await fetch(`${cfg.source}${cfg.source.includes('?') ? '&' : '?'}${query}`, {headers: {'X-Requested-With': 'XMLHttpRequest'}, signal: controller.signal});
      if (!response.ok) throw new Error(String(response.status));
      return (await response.json()).results || [];
    };
    const search = async () => {
      const term = input.value.trim();
      if (term.length < minChars) { results = []; render(); setStatus(cfg.hint || ''); if (free) close(); return; }
      setStatus('Đang tìm…');
      try {
        results = await fetchJson(params({[cfg.queryParam || 'q']: term}));
        render();
        setStatus(results.length ? '' : (free ? (cfg.emptyText || '') : (cfg.emptyText || 'Không có kết quả phù hợp.')));
        if (free) { if (results.length || status.textContent) open(); else close(); }
      } catch (error) {
        if (error.name === 'AbortError') return;
        results = []; render(); setStatus(cfg.errorText || 'Không tải được kết quả. Thử lại.');
      }
    };

    const showSelected = () => { input.value = selected ? selected.label : ''; paint(); };
    const pick = item => {
      if (free) {
        input.value = item[labelKey] || item[titleKey] || ''; paint(); close();
        input.dispatchEvent(new Event('change', {bubbles: true})); emit('select', {item}); return;
      }
      selected = {id: item[idKey], label: item[labelKey] || item[titleKey] || '', item};
      writeSpecial(''); writeValue(String(selected.id)); showSelected(); close();
      emit('select', {item});
    };
    const pickSpecial = () => {
      selected = {special: true, label: cfg.specialLabel};
      writeValue(''); writeSpecial('1'); showSelected(); close();
      emit('special', {label: cfg.specialLabel});
    };
    const clear = (focus = true) => {
      const had = Boolean(selected);
      selected = null; results = []; render();
      writeValue(''); writeSpecial(''); input.value = ''; paint();
      if (had) emit('clear', {});
      if (focus) { input.focus(); setStatus(cfg.hint || ''); if (!free) open(); }
    };

    input.addEventListener('focus', () => { open(); if (!selected && !input.value) setStatus(cfg.hint || ''); });
    input.addEventListener('click', open);
    input.addEventListener('input', () => {
      if (selected) { selected = null; writeValue(''); writeSpecial(''); emit('clear', {}); }
      paint(); if (!free) open();
      window.clearTimeout(timer); timer = window.setTimeout(search, delay);
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') { event.preventDefault(); open(); setActive(active + 1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); open(); setActive(active - 1, true); }
      else if (event.key === 'Enter') {
        if (!menu.hidden && active >= 0) { event.preventDefault(); const item = options()[active]; if (item === footer) pickSpecial(); else if (item._item) pick(item._item); }
        else if (!menu.hidden && !free) event.preventDefault();
      }
      else if (event.key === 'Escape' && !menu.hidden) { event.preventDefault(); event.stopPropagation(); close(); }
      else if (event.key === 'Backspace' && selected && !input.value) { clear(false); }
    });
    input.addEventListener('blur', () => { window.setTimeout(() => { if (!wrapper.contains(document.activeElement)) { close(); if (selected) showSelected(); } }, 120); });
    list.addEventListener('mousedown', event => event.preventDefault());
    list.addEventListener('click', event => { const item = event.target.closest('.ui-combobox-option'); if (item?._item) pick(item._item); });
    footer.addEventListener('mousedown', event => event.preventDefault());
    footer.addEventListener('click', pickSpecial);
    clearBtn.addEventListener('click', () => clear());
    filterEl?.addEventListener('change', () => { if (!selected && input.value.trim()) search(); });

    footer.id = `${id}-special`;
    // Khôi phục lựa chọn có sẵn từ server (form dựng lại sau lỗi validate)
    const restore = async () => {
      if (free) { paint(); return; }
      if (specialInput?.value) { selected = {special: true, label: cfg.specialLabel}; showSelected(); return; }
      const current = (valueInput?.value || '').trim();
      if (!current) { paint(); return; }
      try {
        const [item] = await fetchJson(new URLSearchParams({[cfg.selectParam || 'selected_id']: current}));
        if (item) { selected = {id: item[idKey], label: item[labelKey] || item[titleKey] || '', item}; showSelected(); emit('restore', {item}); }
      } catch (error) { /* giữ nguyên giá trị ẩn, ô hiển thị trống */ }
    };

    instances.set(wrapper, {
      close,
      setSpecial: pickSpecial,
      clear,
      reset: () => { selected = null; results = []; render(); input.value = ''; paint(); },
      hasValue: () => Boolean(selected),
    });
    paint();
    restore();
  };

  const initAll = root => {
    if (root.matches?.('[data-ui-combobox]')) init(root);
    root.querySelectorAll?.('[data-ui-combobox]').forEach(init);
  };
  document.addEventListener('pointerdown', event => { if (!event.target.closest('[data-ui-combobox]')) closeOthers(null); });
  const start = () => {
    initAll(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => { if (node.nodeType === 1) initAll(node); })))
      .observe(document.body, {childList: true, subtree: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.uiCombobox = {
    init: initAll,
    clear: wrapper => instances.get(wrapper)?.clear(false),
    setSpecial: wrapper => instances.get(wrapper)?.setSpecial(),
    reset: wrapper => instances.get(wrapper)?.reset(),
  };
})();
