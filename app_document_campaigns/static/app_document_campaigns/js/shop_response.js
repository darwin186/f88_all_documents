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
    const percentage = rows.length ? Math.round(completed * 100 / rows.length) : 0;
    if (progress) progress.style.width = `${percentage}%`;
    const progressPercent = document.querySelector('[data-progress-percent]');
    if (progressPercent) progressPercent.textContent = `${percentage}%`;
  };

  const setRowInvalid = (row, invalid) => {
    const select = row.querySelector('[data-answer]');
    const message = row.querySelector('[data-answer-error]');
    row.classList.toggle('dec-row-invalid', invalid);
    select.setAttribute('aria-invalid', invalid ? 'true' : 'false');
    if (message) message.hidden = !invalid;
  };

  const missingRows = () => [...document.querySelectorAll('[data-response-row]')]
    .filter((row) => !row.querySelector('[data-answer]').value);

  const showMissingRows = (rows) => {
    const missingIds = new Set(rows.map((row) => row.dataset.errorUid));
    document.querySelectorAll('[data-response-row]').forEach((row) => {
      setRowInvalid(row, missingIds.has(row.dataset.errorUid));
    });
    const first = rows[0];
    if (first) {
      first.scrollIntoView({behavior: 'smooth', block: 'center'});
      window.setTimeout(() => first.querySelector('[data-answer]').focus(), 350);
    }
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
      error.body = body;
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
    row.querySelector('[data-answer]').addEventListener('change', () => {
      setRowInvalid(row, !row.querySelector('[data-answer]').value);
      queueRow(row);
    });
    row.querySelector('[data-note]').addEventListener('input', () => queueRow(row));
  });

  submitButton?.addEventListener('click', async () => {
    const missing = missingRows();
    if (missing.length) {
      showMissingRows(missing);
      setIndicator('error', `Còn ${missing.length} dòng chưa chọn phản hồi`);
      updateProgress();
      return;
    }
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
      root.dataset.readOnly = 'true';
      document.querySelectorAll('[data-answer], [data-note]').forEach((field) => {
        field.disabled = true;
      });
      submitButton.disabled = true;
      submitButton.textContent = 'Đã gửi phản hồi';
      setIndicator('saved', 'Đã gửi phản hồi chính thức');
      window.location.reload();
    } catch (error) {
      if (Array.isArray(error.body?.missing_uids)) {
        const missingIds = new Set(error.body.missing_uids);
        showMissingRows(
          [...document.querySelectorAll('[data-response-row]')]
            .filter((row) => missingIds.has(row.dataset.errorUid))
        );
      }
      setIndicator('error', error.message);
      submitButton.disabled = false;
    }
  });

  updateProgress();

  window.addEventListener('beforeunload', (event) => {
    if (!pending.size && !inFlight) return;
    event.preventDefault();
    event.returnValue = '';
  });
})();
