document.addEventListener('DOMContentLoaded', () => {
  window.adminDocumentFormControls?.init(document.getElementById('paperModal'));
  const modal = document.getElementById('paperModal');
  const tabs = [...modal.querySelectorAll('[data-paper-tab]')];
  const activate = button => {
    tabs.forEach(tab => { const active = tab === button; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; });
    modal.querySelectorAll('[data-paper-panel]').forEach(panel => { panel.hidden = panel.dataset.paperPanel !== button.dataset.paperTab; });
  };
  tabs.forEach(tab => tab.addEventListener('click', () => activate(tab)));
  modal.querySelector('[role=tablist]').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const index = tabs.indexOf(event.target); if (index < 0) return;
    event.preventDefault();
    const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1) : tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
    activate(next); next.focus();
  });
  if (modal.hasAttribute('data-paper-create-open')) document.querySelector('[data-modal-toggle="paperModal"]').click();
  const notify = options => window.adminDocumentNotify?.(options);
  const importPanel = modal.querySelector('[data-paper-import]');
  const file = importPanel.querySelector('[data-paper-import-file]');
  const process = importPanel.querySelector('[data-paper-process]');
  const commit = importPanel.querySelector('[data-paper-commit]');
  const status = importPanel.querySelector('[data-paper-import-status]');
  const csrf = modal.querySelector('[name=csrfmiddlewaretoken]').value;
  let token = null, busy = false;
  const setBusy = value => { busy = value; file.disabled = value; process.disabled = value; commit.disabled = value || !token; };
  const responseData = async response => {
    const result = response.headers.get('Content-Type')?.includes('application/json') ? await response.json() : null;
    if (!response.ok || !result) throw new Error([result?.error || 'Không thể hoàn tất. Vui lòng kiểm tra kết nối hoặc đăng nhập lại.', ...(result?.details || [])].join('\n'));
    return result;
  };
  file.addEventListener('change', () => { token = null; commit.disabled = true; status.textContent = 'File đã thay đổi. Vui lòng kiểm tra dữ liệu trước khi lưu.'; });
  process.addEventListener('click', async () => {
    if (busy) return;
    token = null; commit.disabled = true;
    if (!file.files[0]) { notify({type: 'error', title: 'Chưa chọn file', message: 'Vui lòng chọn file Excel (.xlsx) để kiểm tra dữ liệu.'}); return; }
    setBusy(true); status.textContent = 'Đang kiểm tra dữ liệu…';
    try {
      const body = new FormData(); body.append('file', file.files[0]); body.append('csrfmiddlewaretoken', csrf);
      const result = await responseData(await fetch(importPanel.dataset.processUrl, {method: 'POST', body, headers: {'X-Requested-With': 'XMLHttpRequest'}}));
      if (!result.token) throw new Error('Chưa nhận được mã xác nhận dữ liệu. Vui lòng kiểm tra lại file.');
      token = result.token; status.textContent = `${result.rows} dòng hợp lệ. Bấm Lưu dữ liệu để tạo giấy hành chính.`;
      notify({type: 'success', title: 'Kiểm tra file thành công', message: `File: ${file.files[0].name}\nSố dòng hợp lệ: ${result.rows}\nBấm Lưu dữ liệu để hoàn tất.`});
    } catch (failure) { status.textContent = 'Kiểm tra thất bại. Chưa có dữ liệu được lưu.'; notify({type: 'error', title: 'Không thể xử lý file Excel', message: failure.message}); }
    finally { setBusy(false); }
  });
  commit.addEventListener('click', async () => {
    if (!token || busy) return;
    setBusy(true); status.textContent = 'Đang lưu dữ liệu…';
    try {
      const body = new FormData(); body.append('token', token); body.append('csrfmiddlewaretoken', csrf);
      const result = await responseData(await fetch(importPanel.dataset.commitUrl, {method: 'POST', body, headers: {'X-Requested-With': 'XMLHttpRequest'}}));
      token = null; status.textContent = `Đã lưu ${result.created} dòng. Đang tải lại danh sách…`;
      const url = new URL(location.href); url.searchParams.delete('edit'); url.searchParams.delete('create'); location.assign(url);
    } catch (failure) { status.textContent = 'Chưa xác nhận được kết quả lưu. Vui lòng kiểm tra lại danh sách trước khi gửi lại.'; notify({type: 'error', title: 'Không thể hoàn tất nhập Excel', message: failure.message}); }
    finally { setBusy(false); }
  });
  const createForm = modal.querySelector('[data-paper-create-form]');
  let creating = false;
  createForm.addEventListener('submit', event => {
    if (creating || busy) { event.preventDefault(); return; }
    creating = true; createForm.querySelector('[type=submit]').disabled = true;
  });
  window.addEventListener('pageshow', () => { creating = false; createForm.querySelector('[type=submit]').disabled = false; });
  document.addEventListener('click', event => {
    if ((busy || creating) && event.target.closest('[data-modal-hide="paperModal"]')) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  const drawer = document.getElementById('docDrawer'), drawerBody = document.getElementById('docDrawerBody');
  let drawerRequest, opener;
  window.closeDocDrawer = () => { drawerRequest?.abort(); drawer.classList.add('hidden'); opener?.focus({preventScroll: true}); };
  drawer.querySelectorAll('[data-paper-drawer-close]').forEach(button => button.addEventListener('click', window.closeDocDrawer));
  const openDrawer = async (href, trigger) => {
    opener = trigger; drawerRequest?.abort(); drawerRequest = new AbortController(); const signal = drawerRequest.signal;
    drawer.classList.remove('hidden'); drawer.querySelector('button[aria-label]').focus(); drawerBody.textContent = 'Đang tải…';
    try {
      const url = new URL(href, location.href); url.searchParams.set('drawer', '1');
      const response = await fetch(url, {signal, headers: {'X-Requested-With': 'XMLHttpRequest'}});
      if (!response.ok || response.redirected) throw new Error('Không thể tải chi tiết giấy hành chính. Vui lòng kiểm tra kết nối hoặc quyền truy cập.');
      const html = await response.text(); if (!signal.aborted) drawerBody.innerHTML = html;
    } catch (failure) { if (failure.name !== 'AbortError') { drawerBody.textContent = failure.message; notify({type: 'error', title: 'Không thể mở Xem nhanh', message: failure.message}); } }
  };
  document.querySelectorAll('[data-document-preview]').forEach(row => {
    row.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = event.target.closest('.doc-detail-link');
      if (!link && event.target.closest('a, button, input, select, textarea, summary, [data-document-actions]')) return;
      if (!link && window.getSelection()?.toString()) return;
      event.preventDefault(); row.focus({preventScroll: true}); openDrawer(row.dataset.documentPreview, row);
    });
    row.addEventListener('keydown', event => {
      if (event.target !== row || !['Enter', ' '].includes(event.key)) return;
      event.preventDefault(); openDrawer(row.dataset.documentPreview, row);
    });
  });
  const activatePreviewTab = button => {
    drawerBody.querySelectorAll('[data-preview-tab]').forEach(tab => { const active = tab === button; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; });
    drawerBody.querySelectorAll('[data-preview-panel]').forEach(panel => { panel.hidden = panel.dataset.previewPanel !== button.dataset.previewTab; });
  };
  drawerBody.addEventListener('click', event => { const tab = event.target.closest('[data-preview-tab]'); if (tab) activatePreviewTab(tab); });
  drawerBody.addEventListener('keydown', event => {
    const current = event.target.closest('[data-preview-tab]'); if (!current || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const tabs = [...drawerBody.querySelectorAll('[data-preview-tab]')], index = tabs.indexOf(current);
    const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1) : tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
    event.preventDefault(); activatePreviewTab(next); next.focus();
  });
  document.addEventListener('keydown', event => {
    if (drawer.classList.contains('hidden') || document.querySelector('dialog[open]')) return;
    if (event.key === 'Escape') window.closeDocDrawer();
    if (event.key !== 'Tab') return;
    const controls = [...drawer.querySelectorAll('a[href], button, input, select, textarea')].filter(el => !el.disabled && el.getClientRects().length);
    if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1)?.focus(); }
    else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0]?.focus(); }
  });
});
