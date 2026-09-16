(() => {
  const root = document.querySelector('[data-response-root]');
  if (!root || root.dataset.readOnly === 'true') return;

  const indicator = document.getElementById('save-indicator');
  const submitButton = document.getElementById('submit-responses');
  const pending = new Map();
  let timer = null;
  let inFlight = null;

  const csrfToken = () => {
    const item = document.cookie.split('; ').find((value) => value.startsWith('csrftoken='));
    return item ? decodeURIComponent(item.split('=').slice(1).join('=')) : '';
  };

  const setIndicator = (state, text) => {
    indicator.textContent = text;
    indicator.className = 'rounded-full px-3 py-2 text-xs font-semibold';
    const classes = {
      idle: ' bg-gray-100 text-gray-600',
      waiting: ' bg-amber-50 text-amber-700',
      saving: ' bg-blue-50 text-blue-700',
      saved: ' bg-emerald-50 text-emerald-700',
      error: ' bg-red-50 text-red-700',
    };
    indicator.className += classes[state] || classes.idle;
  };

  const payloadForRow = (row) => ({
    error_uid: row.dataset.errorUid,
    version_no: Number(row.dataset.version || 0),
    answer_code: row.querySelector('[data-answer]').value,
    note: row.querySelector('[data-note]').value,
  });

  const updateProgress = () => {
    const rows = [...document.querySelectorAll('[data-response-row]')];
    const completed = rows.filter((row) => row.querySelector('[data-answer]').value).length;
    document.querySelector('[data-completed]').textContent = String(completed);
    const progress = document.querySelector('[data-progress]');
    if (progress) progress.style.width = `${rows.length ? completed * 100 / rows.length : 0}%`;
  };

  const queueRow = (row) => {
    pending.set(row.dataset.errorUid, row);
    setIndicator('waiting', 'Có thay đổi chưa lưu');
    clearTimeout(timer);
    timer = setTimeout(() => flush(), 1000);
    updateProgress();
  };

  const postJson = async (url, payload) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({ok: false, error: 'Phản hồi máy chủ không hợp lệ.'}));
    if (!response.ok) {
      const error = new Error(body.error || 'Không thể lưu dữ liệu.');
      error.status = response.status;
      throw error;
    }
    return body;
  };

  const sendBatch = async () => {
    const rows = [...pending.values()].slice(0, 50);
    if (!rows.length) return;
    rows.forEach((row) => pending.delete(row.dataset.errorUid));
    setIndicator('saving', `Đang lưu ${rows.length} thay đổi…`);
    try {
      const body = await postJson(root.dataset.autosaveUrl, {changes: rows.map(payloadForRow)});
      body.saved.forEach((item) => {
        const row = document.querySelector(`[data-error-uid="${item.error_uid}"]`);
        if (!row) return;
        row.dataset.version = String(item.version_no);
        row.classList.remove('dec-row-saved');
        void row.offsetWidth;
        row.classList.add('dec-row-saved');
      });
      setIndicator('saved', `Đã lưu lúc ${new Date().toLocaleTimeString('vi-VN')}`);
    } catch (error) {
      rows.forEach((row) => pending.set(row.dataset.errorUid, row));
      setIndicator('error', error.status === 409 ? 'Dữ liệu đã thay đổi ở cửa sổ khác' : 'Chưa thể lưu, sẽ thử lại');
      if (error.status !== 409 && error.status !== 423) {
        clearTimeout(timer);
        timer = setTimeout(() => flush(), 3000);
      }
      throw error;
    }
  };

  const flush = async () => {
    clearTimeout(timer);
    if (inFlight) await inFlight;
    while (pending.size) {
      inFlight = sendBatch();
      try { await inFlight; } finally { inFlight = null; }
    }
  };

  document.querySelectorAll('[data-response-row]').forEach((row) => {
    row.querySelector('[data-answer]').addEventListener('change', () => queueRow(row));
    row.querySelector('[data-note]').addEventListener('input', () => queueRow(row));
  });

  submitButton?.addEventListener('click', async () => {
    submitButton.disabled = true;
    try {
      await flush();
      const storageKey = root.dataset.submissionKey;
      let idempotencyKey = localStorage.getItem(storageKey);
      if (!idempotencyKey) {
        idempotencyKey = self.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
        localStorage.setItem(storageKey, idempotencyKey);
      }
      await postJson(root.dataset.submitUrl, {idempotency_key: idempotencyKey});
      setIndicator('saved', 'Đã gửi phản hồi chính thức');
      window.location.reload();
    } catch (error) {
      setIndicator('error', error.message);
      submitButton.disabled = false;
    }
  });

  window.addEventListener('beforeunload', (event) => {
    if (!pending.size && !inFlight) return;
    event.preventDefault();
    event.returnValue = '';
  });
})();
