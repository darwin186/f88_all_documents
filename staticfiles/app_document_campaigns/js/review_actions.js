document.addEventListener('DOMContentLoaded', () => {
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]').value;
  const updateStats = (stats, percent) => {
    document.querySelectorAll('[data-metric]').forEach(element => element.textContent = stats[element.dataset.metric]);
    const track = document.querySelector('[data-review-progress]');
    const value = document.querySelector('[data-review-progress-value]');
    if (track) track.setAttribute('aria-valuenow', percent);
    if (value) { value.style.width = `${percent}%`; value.style.backgroundColor = `hsl(${percent * 1.2},65%,43%)`; }
    document.querySelectorAll('[data-review-progress-label]').forEach(element => element.textContent = `${percent}%`);
  };
  const post = async (url, data) => {
    const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf()}, body:JSON.stringify(data)});
    let payload;
    try { payload = await response.json(); } catch (_) { throw new Error('Phản hồi máy chủ không hợp lệ.'); }
    if (!response.ok) throw new Error(payload.error || 'Không lưu được review.');
    return payload;
  };
  const refreshReceipt = async (row, notify = false) => {
    if (!row.dataset.receiptUrl) return;
    const response = await fetch(row.dataset.receiptUrl, {cache:'no-store'});
    if (!response.ok) throw new Error('Không kiểm tra được trạng thái nhận quyển. Vui lòng thử lại.');
    const receipt = await response.json();
    const label = row.querySelector('[data-receipt-label]');
    label.textContent = receipt.label;
    label.classList.toggle('review-received', receipt.received);
    row.querySelector('[data-receipt-date]').textContent = receipt.date || '—';
    if (notify && receipt.received) window.campaignToast?.(`Quyển này đã nhận${receipt.date ? ' ngày '+receipt.date : ''}. Hãy đối chiếu trước khi kết luận.`, 'warning');
  };
  document.querySelectorAll('[data-review-row][data-receipt-url] [data-decision]').forEach(select => select.addEventListener('focus', () => {
    refreshReceipt(select.closest('[data-review-row]'), true).catch(error => window.campaignToast?.(error.message,'error'));
  }));
  document.querySelectorAll('[data-save-review]').forEach(button => button.addEventListener('click', async () => {
    const row = button.closest('[data-review-row]'), decision = row.querySelector('[data-decision]'), note = row.querySelector('[data-note]'), feedback = row.querySelector('[data-feedback]');
    feedback.className = 'review-feedback';
    if (!decision.value) { window.campaignToast?.('Vui lòng chọn kết luận trước khi lưu.','warning'); decision.focus(); return; }
    button.disabled = decision.disabled = note.disabled = true;
    feedback.textContent = 'Đang lưu…';
    try {
      await refreshReceipt(row);
      const data = await post(row.dataset.url, {decision:decision.value,note:note.value,expected_review_id:row.dataset.reviewId ? Number(row.dataset.reviewId) : null});
      row.dataset.reviewId = data.review_id;
      feedback.textContent = `Đã lưu · ${data.reviewer}`;
      updateStats(data.stats, data.percent);
      window.campaignToast?.('Đã lưu kết luận book lỗi.','success');
    } catch (error) { feedback.textContent = error.message; feedback.classList.add('error'); window.campaignToast?.(error.message,'error'); }
    finally { button.disabled = decision.disabled = note.disabled = false; }
  }));
  const boxes = [...document.querySelectorAll('[data-review-select]:not(:disabled)')];
  const all = document.querySelector('[data-review-select-all]');
  const updateCount = () => {
    const count = boxes.filter(box => box.checked).length;
    document.querySelectorAll('[data-bulk-count]').forEach(element => element.textContent = count);
    if (all) { all.checked = boxes.length > 0 && count === boxes.length; all.indeterminate = count > 0 && count < boxes.length; }
  };
  boxes.forEach(box => box.addEventListener('change', updateCount));
  all?.addEventListener('change', () => { boxes.forEach(box => box.checked = all.checked); updateCount(); });
  const form = document.querySelector('[data-review-bulk]');
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    const selected = boxes.filter(box => box.checked).map(box => box.closest('[data-review-row]'));
    if (!selected.length) { window.campaignToast?.('Tick các dòng cần cập nhật trước.','warning'); return; }
    const note = form.querySelector('[data-bulk-note]').value.trim();
    const decision = form.querySelector('[data-bulk-decision]').value;
    if (!note && !decision) { window.campaignToast?.('Nhập nhận xét chung hoặc chọn kết luận.','warning'); return; }
    if (!confirm(`Áp dụng cho ${selected.length} dòng đã chọn?`)) return;
    const button = form.querySelector('button');
    button.disabled = true;
    form.querySelector('[data-bulk-feedback]').textContent = 'Đang cập nhật…';
    try {
      const data = await post(form.dataset.url, {note,decision,mode:form.querySelector('[data-bulk-mode]').value,rows:selected.map(row=>({id:Number(row.dataset.errorId),expected_review_id:row.dataset.reviewId ? Number(row.dataset.reviewId) : null}))});
      try { sessionStorage.setItem('campaign-review-import-toast',JSON.stringify({path:location.pathname,message:`Đã cập nhật ${data.updated} dòng review.`})); } catch (_) {}
      location.reload();
    } catch (error) { form.querySelector('[data-bulk-feedback]').textContent=error.message; window.campaignToast?.(error.message,'error'); button.disabled=false; }
  });
});
