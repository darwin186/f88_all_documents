(() => {
  const controllers = new WeakMap();
  const closeMenus = except => document.querySelectorAll('[data-document-select]').forEach(wrapper => {
    if (wrapper !== except) controllers.get(wrapper)?.close();
  });
  const initSelect = wrapper => {
    if (controllers.has(wrapper)) return;
    const source = wrapper.querySelector('select');
    if (!source) return;
    const toggle = wrapper.querySelector('[data-select-toggle]');
    const label = wrapper.querySelector('[data-select-label]');
    const menu = wrapper.querySelector('[data-select-menu]');
    const search = wrapper.querySelector('[data-select-search]');
    const options = wrapper.querySelector('[data-select-options]');
    const empty = wrapper.querySelector('[data-select-empty]');
    const emptyLabel = [...source.options].find(option => !option.value)?.textContent.trim();
    const placeholder = emptyLabel && !/^-+$/.test(emptyLabel) ? emptyLabel : `-- Chọn ${source.labels?.[0]?.textContent.replace('*', '').trim().toLowerCase() || 'giá trị'} --`;
    const close = () => { menu.hidden = true; toggle.setAttribute('aria-expanded', 'false'); };
    const refresh = () => {
      toggle.disabled = source.disabled;
      toggle.style.color = source.selectedOptions[0]?.dataset.color || source.style.color || '';
      label.textContent = source.value ? source.selectedOptions[0]?.textContent : placeholder;
      const term = search.value.trim().toLocaleLowerCase('vi');
      options.replaceChildren();
      [...source.options].filter(option => option.value && !option.disabled && option.textContent.toLocaleLowerCase('vi').includes(term)).forEach(option => {
        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', String(option.selected));
        button.className = 'w-full text-left px-3 py-2 hover:bg-gray-100 flex items-center justify-between';
        button.textContent = option.textContent;
        if (option.selected) { button.classList.add('bg-gray-50', 'text-f88green'); button.setAttribute('aria-current', 'true'); }
        button.addEventListener('click', () => {
          source.value = option.value;
          source.dispatchEvent(new Event('change', {bubbles: true}));
          close(); toggle.focus();
        });
        item.append(button); options.append(item);
      });
      empty.hidden = options.children.length > 0;
    };
    const open = () => {
      closeMenus(wrapper); search.value = ''; refresh(); menu.hidden = false;
      toggle.setAttribute('aria-expanded', 'true'); search.focus({preventScroll: true});
    };
    toggle.addEventListener('click', () => menu.hidden ? open() : close());
    search.addEventListener('input', refresh);
    search.addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); options.querySelector('button')?.click(); }
      if (event.key === 'ArrowDown') { event.preventDefault(); options.querySelector('button')?.focus(); }
    });
    wrapper.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !menu.hidden) { event.preventDefault(); event.stopPropagation(); close(); toggle.focus(); }
      if (event.key === 'ArrowDown' && event.target === toggle) { event.preventDefault(); open(); }
    });
    wrapper.querySelector('[data-select-clear]').addEventListener('click', () => {
      source.value = ''; source.dispatchEvent(new Event('change', {bubbles: true})); close(); toggle.focus();
    });
    source.addEventListener('invalid', event => { event.preventDefault(); open(); toggle.focus(); });
    source.addEventListener('change', refresh);
    new MutationObserver(refresh).observe(source, {childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'selected', 'label']});
    toggle.setAttribute('aria-haspopup', 'listbox'); options.setAttribute('role', 'listbox');
    // Keep the original select as the submitted/validated field; enhance only its UI.
    source.className = 'sr-only'; source.tabIndex = -1;
    toggle.hidden = false;
    if (source.labels?.[0]) toggle.setAttribute('aria-label', source.labels[0].textContent.trim());
    controllers.set(wrapper, {close}); refresh();
  };
  let DatepickerClass;
  const initDatepickers = root => {
    const inputs = [...root.querySelectorAll('[data-document-datepicker]')];
    if (!inputs.length) return;
    const findConstructor = () => [...document.querySelectorAll('input')].find(input => input.datepicker)?.datepicker.constructor;
    DatepickerClass ||= window.Datepicker || findConstructor();
    if (!DatepickerClass && window.Flowbite?.initDatepickers) {
      // The same bundle used by the create form exposes an initializer, not the class.
      window.Flowbite.initDatepickers();
      DatepickerClass = findConstructor();
    }
    if (!DatepickerClass) return;
    inputs.forEach(input => {
      if (input.dataset.dpAttached) return;
      // Move newly bootstrapped pickers into the dialog's top layer by recreating them.
      input.datepicker?.destroy();
      const dialog = input.closest('dialog');
      const datepicker = new DatepickerClass(input, {
        format: 'dd/mm/yyyy', autohide: true,
        todayBtn: input.hasAttribute('datepicker-buttons'),
        todayBtnMode: input.hasAttribute('datepicker-autoselect-today') ? 1 : 0,
        container: dialog ? `#${dialog.id}` : 'body',
      });
      if (dialog) {
        // Calendar cells are not focusable. Keep the input focused so the native
        // dialog cannot take focus and close the calendar before its click runs.
        datepicker.picker.element.addEventListener('mousedown', event => {
          if (!event.target.closest('input, select, textarea')) event.preventDefault();
        });
      }
      input.dataset.dpAttached = '1';
    });
  };
  const destroy = root => {
    root.querySelectorAll('[data-document-datepicker]').forEach(input => {
      input.datepicker?.destroy(); delete input.dataset.dpAttached;
    });
  };
  const init = root => {
    initDatepickers(root);
    root.querySelectorAll('[data-document-select]').forEach(initSelect);
    root.querySelectorAll('[data-document-attachment]').forEach(wrapper => {
      if (wrapper.dataset.initialized) return;
      wrapper.dataset.initialized = '1';
      const sync = () => {
        const mode = wrapper.querySelector('input[type=radio]:checked').value;
        wrapper.querySelectorAll('[data-attachment-panel]').forEach(panel => {
          panel.hidden = panel.dataset.attachmentPanel !== mode;
          panel.querySelectorAll('input').forEach(input => { input.disabled = panel.hidden; });
        });
      };
      wrapper.querySelectorAll('input[type=radio]').forEach(input => input.addEventListener('change', sync)); sync();
    });
    root.querySelectorAll('select[name=reference_document]').forEach(source => {
      if (source.dataset.referenceReady) return;
      source.dataset.referenceReady = '1';
      source.addEventListener('change', () => {
        const option = source.selectedOptions[0];
        const number = option?.textContent.match(/\(([^()]*)\)\s*$/)?.[1];
        if (number && source.form) {
          source.form.elements.reference_number.value = number;
          source.form.elements.is_reference_document.checked = true;
        }
      });
    });
  };
  document.addEventListener('click', event => {
    if (!event.target.closest('[data-document-select]')) closeMenus();
  });
  document.addEventListener('focusin', event => closeMenus(event.target.closest('[data-document-select]')));
  document.addEventListener('scroll', event => document.querySelectorAll('[data-document-select]').forEach(wrapper => {
    if (event.target === document || event.target.contains?.(wrapper)) controllers.get(wrapper)?.close();
  }), true);
  window.adminDocumentFormControls = {init, destroy};
})();
