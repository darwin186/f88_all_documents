/* F88 UI Kit — Select. Dùng: <div class="ui-select" data-ui-select>{{ <select> }}</div>. Xem docs/ui-kit/components/select.md */
(() => {
  'use strict';
  const instances = new WeakMap();
  let uid = 0;
  const fold = text => text.toLocaleLowerCase('vi');
  const closeOthers = except => document.querySelectorAll('[data-ui-select].is-open').forEach(wrapper => {
    if (wrapper !== except) instances.get(wrapper)?.close();
  });

  const init = wrapper => {
    if (instances.has(wrapper)) return;
    const source = wrapper.querySelector('select');
    if (!source) return;
    const multiple = source.multiple;
    const cfg = wrapper.dataset;
    const max = Number(cfg.max) || 0;
    const limit = Number(cfg.limit) || 300;
    const id = source.id || `ui-select-${++uid}`;
    const labelText = (source.labels?.[0]?.textContent || '').replace('*', '').trim();
    const lowerLabel = labelText.toLocaleLowerCase('vi');
    const emptyOption = [...source.options].find(option => !option.value);
    const emptyText = emptyOption?.textContent.trim();
    const placeholder = cfg.placeholder || (emptyText && !/^-+$/.test(emptyText) ? emptyText : `Chọn ${lowerLabel || 'giá trị'}`);

    const el = (tag, className, attrs = {}) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      Object.entries(attrs).forEach(([key, val]) => node.setAttribute(key, val));
      return node;
    };
    const toggle = el('button', 'ui-select-toggle', {type: 'button', 'aria-haspopup': 'listbox', 'aria-expanded': 'false', 'aria-controls': `${id}-menu`});
    const value = el('span', 'ui-select-value');
    toggle.append(value, el('span', 'ui-select-arrow', {'aria-hidden': 'true'}));
    const menu = el('div', 'ui-select-menu', {id: `${id}-menu`});
    menu.hidden = true;
    const head = el('div', 'ui-select-head');
    const count = el('span', 'ui-select-count');
    const actions = el('span', 'ui-select-actions');
    const allLink = el('button', 'ui-select-link', {type: 'button'}); allLink.textContent = 'Chọn tất cả';
    const clearLink = el('button', 'ui-select-link', {type: 'button'}); clearLink.textContent = 'Bỏ chọn';
    actions.append(allLink, clearLink); head.append(count, actions);
    const search = el('input', 'ui-select-search', {
      type: 'search', autocomplete: 'off',
      placeholder: cfg.searchPlaceholder || (lowerLabel ? `Tìm kiếm ${lowerLabel}...` : 'Tìm kiếm...'),
      'aria-label': `Tìm ${labelText || 'lựa chọn'}`,
    });
    const list = el('ul', 'ui-select-options', {role: 'listbox', 'aria-label': labelText || placeholder});
    if (multiple) list.setAttribute('aria-multiselectable', 'true');
    const empty = el('p', 'ui-select-empty'); empty.textContent = cfg.emptyText || 'Không tìm thấy kết quả'; empty.hidden = true;
    const note = el('p', 'ui-select-note'); note.hidden = true;
    menu.append(head, search, list, empty, note);

    const realOptions = () => [...source.options].filter(option => option.value && !option.hidden);
    const showSearch = () => cfg.search === 'on' || (cfg.search !== 'off' && realOptions().length > 7);
    const showClear = () => cfg.clear === 'on' || (cfg.clear !== 'off' && (multiple || !source.required));
    const selected = () => realOptions().filter(option => option.selected);
    const fire = () => source.dispatchEvent(new Event('change', {bubbles: true}));

    const renderValue = () => {
      const chosen = selected();
      value.replaceChildren();
      value.classList.toggle('is-placeholder', chosen.length === 0);
      value.style.color = '';
      toggle.title = chosen.map(option => option.textContent.trim()).join(', ');
      if (!chosen.length) { value.textContent = placeholder; return; }
      if (!multiple) { value.textContent = chosen[0].textContent.trim(); value.style.color = chosen[0].dataset.color || ''; return; }
      if (cfg.summary === 'count' || chosen.length > 3) { value.textContent = `Đã chọn ${chosen.length}`; return; }
      chosen.slice(0, 2).forEach(option => { const chip = el('span', 'ui-select-chip'); chip.textContent = option.textContent.trim(); value.append(chip); });
      if (chosen.length > 2) { const more = el('span', 'ui-select-chip is-more'); more.textContent = `+${chosen.length - 2}`; value.append(more); }
    };

    const makeOption = option => {
      const item = el('li', 'ui-select-option', {role: 'option', tabindex: '-1', 'aria-selected': String(option.selected)});
      item._option = option;
      const atMax = multiple && max && !option.selected && selected().length >= max;
      if (option.disabled || atMax) item.setAttribute('aria-disabled', 'true');
      if (multiple) item.append(el('span', 'ui-select-box', {'aria-hidden': 'true'}));
      const text = el('span', 'ui-select-option-text'); text.textContent = option.textContent.trim();
      if (option.dataset.color) text.style.color = option.dataset.color;
      item.append(text);
      return item;
    };
    const renderList = () => {
      const term = fold(search.value.trim());
      const keepScroll = list.scrollTop;
      list.replaceChildren();
      let shown = 0, matched = 0, group = null;
      const seenGroups = new Set();
      const walk = node => {
        if (node.tagName === 'OPTGROUP') { group = node; [...node.children].forEach(walk); group = null; return; }
        if (node.tagName !== 'OPTION' || !node.value || node.hidden) return;
        if (term && !fold(node.textContent).includes(term)) return;
        matched += 1;
        if (shown >= limit) return;
        if (group && !seenGroups.has(group)) {
          seenGroups.add(group);
          const heading = el('li', 'ui-select-group', {role: 'presentation'}); heading.textContent = group.label; list.append(heading);
        }
        list.append(makeOption(node)); shown += 1;
      };
      [...source.children].forEach(walk);
      empty.hidden = matched > 0;
      note.hidden = matched <= shown;
      if (matched > shown) note.textContent = `Hiển thị ${shown}/${matched} kết quả — gõ thêm để lọc.`;
      list.scrollTop = keepScroll;
      const chosen = selected().length;
      count.textContent = multiple ? (max ? `Đã chọn ${chosen}/${max}` : `Đã chọn ${chosen}`) : '';
      count.hidden = !multiple;
      allLink.hidden = !multiple || Boolean(max);
      clearLink.hidden = !showClear();
      head.hidden = !multiple && clearLink.hidden;
      search.hidden = !showSearch();
    };
    const refresh = () => {
      toggle.disabled = source.disabled;
      renderValue();
      if (!menu.hidden) renderList();
    };

    const close = () => { menu.hidden = true; wrapper.classList.remove('is-open', 'is-up'); toggle.setAttribute('aria-expanded', 'false'); };
    const open = () => {
      if (source.disabled) return;
      closeOthers(wrapper);
      search.value = '';
      renderList();
      menu.hidden = false;
      wrapper.classList.add('is-open');
      const rect = wrapper.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom;
      wrapper.classList.toggle('is-up', below < Math.min(menu.offsetHeight, 330) + 12 && rect.top > below);
      toggle.setAttribute('aria-expanded', 'true');
      (showSearch() ? search : list.querySelector('[aria-selected="true"]') || list.querySelector('.ui-select-option'))?.focus({preventScroll: true});
      list.querySelector('[aria-selected="true"]')?.scrollIntoView({block: 'nearest'});
    };
    const choose = item => {
      const option = item._option;
      if (!option || item.getAttribute('aria-disabled') === 'true') return;
      if (multiple) {
        option.selected = !option.selected;
        fire(); renderValue(); renderList();
        [...list.querySelectorAll('.ui-select-option')].find(node => node._option === option)?.focus({preventScroll: true});
      } else {
        option.selected = true; fire(); renderValue(); close(); toggle.focus();
      }
      toggle.classList.remove('is-invalid');
    };
    const enabledItems = () => [...list.querySelectorAll('.ui-select-option:not([aria-disabled="true"])')];

    toggle.addEventListener('click', () => (menu.hidden ? open() : close()));
    toggle.addEventListener('keydown', event => {
      if (['ArrowDown', 'ArrowUp'].includes(event.key) && menu.hidden) { event.preventDefault(); open(); }
    });
    list.addEventListener('click', event => { const item = event.target.closest('.ui-select-option'); if (item) choose(item); });
    list.addEventListener('keydown', event => {
      const items = enabledItems();
      const index = items.indexOf(document.activeElement);
      if (event.key === 'ArrowDown') { event.preventDefault(); items[Math.min(index + 1, items.length - 1)]?.focus(); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); if (index <= 0 && showSearch()) search.focus(); else items[Math.max(index - 1, 0)]?.focus(); }
      else if (event.key === 'Home') { event.preventDefault(); items[0]?.focus(); }
      else if (event.key === 'End') { event.preventDefault(); items[items.length - 1]?.focus(); }
      else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (document.activeElement?._option) choose(document.activeElement); }
    });
    search.addEventListener('input', renderList);
    search.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') { event.preventDefault(); enabledItems()[0]?.focus(); }
      if (event.key === 'Enter') { event.preventDefault(); const first = enabledItems()[0]; if (first) choose(first); }
    });
    wrapper.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !menu.hidden) { event.preventDefault(); event.stopPropagation(); close(); toggle.focus(); }
      if (event.key === 'Tab' && !menu.hidden) close();
    });
    clearLink.addEventListener('click', () => {
      selected().forEach(option => { option.selected = false; });
      if (!multiple && emptyOption) emptyOption.selected = true;
      fire(); renderValue();
      if (multiple) renderList(); else close();
      toggle.focus();
    });
    allLink.addEventListener('click', () => {
      const term = fold(search.value.trim());
      realOptions().forEach(option => { if (!option.disabled && (!term || fold(option.textContent).includes(term))) option.selected = true; });
      fire(); renderValue(); renderList();
    });
    source.addEventListener('invalid', event => { event.preventDefault(); toggle.classList.add('is-invalid'); open(); });
    source.addEventListener('change', refresh);
    source.form?.addEventListener('reset', () => setTimeout(refresh));
    let queued = false;
    new MutationObserver(() => { if (!queued) { queued = true; queueMicrotask(() => { queued = false; refresh(); }); } })
      .observe(source, {childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'selected', 'label', 'hidden']});
    if (!source.id) source.id = id;
    document.querySelectorAll(`label[for="${CSS.escape(source.id)}"]`).forEach(label => label.addEventListener('click', event => { event.preventDefault(); toggle.focus(); }));

    wrapper.classList.toggle('is-multiple', multiple);
    source.classList.add('ui-select-native'); source.tabIndex = -1; source.setAttribute('aria-hidden', 'true');
    if (labelText) toggle.setAttribute('aria-label', labelText);
    if ('invalid' in cfg) toggle.classList.add('is-invalid');
    wrapper.append(toggle, menu);
    instances.set(wrapper, {close, refresh});
    refresh();
  };

  const initAll = root => {
    if (root.matches?.('[data-ui-select]')) init(root);
    root.querySelectorAll?.('[data-ui-select]').forEach(init);
  };
  document.addEventListener('pointerdown', event => { if (!event.target.closest('[data-ui-select]')) closeOthers(null); });
  const start = () => {
    initAll(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => { if (node.nodeType === 1) initAll(node); })))
      .observe(document.body, {childList: true, subtree: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
  window.uiSelect = {
    init: initAll,
    closeAll: root => (root || document).querySelectorAll('[data-ui-select].is-open').forEach(wrapper => instances.get(wrapper)?.close()),
  };
})();
