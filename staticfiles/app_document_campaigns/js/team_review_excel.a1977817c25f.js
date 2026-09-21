document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-review-excel]');
  if (!root) return;
  const base = new URL(root.dataset.url, window.location.origin);
  const fileInput = root.querySelector('[data-excel-file]');
  const buttons = {export: root.querySelector('[data-excel-export]'), import: root.querySelector('[data-excel-import]')};
  const states = {export: root.querySelector('[data-excel-export-state]'), import: root.querySelector('[data-excel-import-state]')};
  const generations = {export: 0, import: 0};
  const showError = (kind, message) => {
    states[kind].textContent = message;
    window.campaignToast?.(message, 'error');
  };
  const poll = async (kind, id, notify, generation) => {
    if (generations[kind] !== generation) return;
    try {
      const response = await fetch(new URL(`${id}/`, base), {cache: 'no-store'});
      if (!response.ok) throw new Error('Không kiểm tra được tiến độ Excel.');
      const job = await response.json();
      if (generations[kind] !== generation) return;
      states[kind].replaceChildren();
      if (['queued', 'running'].includes(job.status)) {
        buttons[kind].disabled = true;
        const spinner = document.createElement('span');
        spinner.className = 'review-spinner';
        states[kind].append(spinner, `Đang xử lý · ${job.progress}%`);
        setTimeout(() => poll(kind, id, true, generation), 2000);
        return;
      }
      buttons[kind].disabled = false;
      if (job.status === 'failed') {
        states[kind].textContent = job.message;
        if (notify) window.campaignToast?.(job.message, 'error');
      } else if (kind === 'export' && job.download_url) {
        const link = document.createElement('a');
        link.href = job.download_url;
        link.textContent = '↓ Tải Excel review';
        states[kind].append(link);
        if (notify) window.campaignToast?.('Đã tạo file Excel review.', 'success');
      } else {
        states[kind].textContent = job.message;
        if (notify) {
          try { sessionStorage.setItem('campaign-review-import-toast', JSON.stringify({path: location.pathname, message: job.message})); } catch (_) {}
          location.reload();
        }
      }
    } catch (error) {
      states[kind].textContent = 'Mất kết nối khi kiểm tra tiến độ — đang thử lại';
      setTimeout(() => poll(kind, id, notify, generation), 4000);
    }
  };
  const start = async (kind, file) => {
    const generation = ++generations[kind];
    buttons[kind].disabled = true;
    states[kind].textContent = 'Đang gửi yêu cầu…';
    const data = new FormData();
    data.append('kind', kind);
    if (file) data.append('file', file);
    try {
      const response = await fetch(base, {method: 'POST', headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value}, body: data});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Không gửi được yêu cầu.');
      poll(kind, payload.id, true, generation);
    } catch (error) {
      buttons[kind].disabled = false;
      showError(kind, error.message);
    }
  };
  buttons.export.addEventListener('click', () => start('export'));
  buttons.import.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.xlsx') || file.size > 20 * 1024 * 1024) {
      showError('import', 'Chọn file .xlsx tối đa 20 MB.');
      return;
    }
    start('import', file);
  });
  try {
    const stored = sessionStorage.getItem('campaign-review-import-toast');
    if (stored) {
      sessionStorage.removeItem('campaign-review-import-toast');
      const toast = JSON.parse(stored);
      if (toast.path === location.pathname) window.campaignToast?.(toast.message, 'success');
    }
  } catch (_) {}
  const jobs = JSON.parse(document.getElementById('review-excel-jobs').textContent);
  Object.entries(jobs).forEach(([kind, id]) => { if (id) poll(kind, id, false, generations[kind]); });
});
