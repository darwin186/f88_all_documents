document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.getElementById('document-attachment-dialog');
  if (!dialog) return;
  const form = dialog.querySelector('form');
  const submit = form.querySelector('[data-attachment-submit]');
  let opener, section, documentNumber, submitting = false;
  const notify = options => window.adminDocumentNotify?.(options);
  const refresh = async current => {
    if (!current?.isConnected) return null;
    const response = await fetch(current.dataset.refreshUrl, {headers: {'X-Requested-With': 'XMLHttpRequest'}});
    if (!response.ok || response.redirected) throw new Error('Không tải lại được danh sách phiên bản.');
    const template = document.createElement('template'); template.innerHTML = await response.text();
    const updated = template.content.querySelector('[data-preview-attachments]');
    if (!updated) throw new Error('Phản hồi không có danh sách đính kèm.');
    if (!current.isConnected) return null;
    current.replaceWith(updated);
    const tab = document.querySelector('#docDrawer [data-preview-tab="attachments"] span');
    if (tab) tab.textContent = updated.querySelectorAll('.adm-attachment-card').length;
    return updated;
  };
  window.adminDocumentAttachments = {refresh};
  const syncMode = () => form.querySelectorAll('[data-attachment-input]').forEach(panel => {
    panel.hidden = panel.dataset.attachmentInput !== form.elements.attachment_mode.value;
    panel.querySelector('input').disabled = panel.hidden;
  });
  const close = () => {
    if (submitting) return;
    dialog.close();
    if (opener?.isConnected) opener.focus();
    else document.querySelector('#docDrawer [data-preview-tab="attachments"]')?.focus();
  };
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-document-attach]');
    if (!trigger || event.button !== 0) return;
    event.preventDefault();
    if (submitting) return;
    opener = trigger; documentNumber = trigger.dataset.documentNumber;
    section = document.querySelector(`#docDrawer [data-preview-attachments][data-document-id="${trigger.dataset.documentId}"]`);
    form.action = trigger.dataset.uploadUrl; form.reset(); syncMode();
    dialog.querySelector('[data-attachment-document]').textContent = `Văn bản: ${documentNumber}`;
    if (!dialog.open) dialog.showModal();
  });
  dialog.querySelectorAll('[data-attachment-close]').forEach(button => button.addEventListener('click', close));
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  form.addEventListener('change', event => { if (event.target.name === 'attachment_mode') syncMode(); });
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (submitting || !form.reportValidity()) return;
    submitting = true; submit.disabled = true; submit.textContent = 'Đang thêm…';
    const file = form.elements.attachment.files[0];
    const name = form.elements.attachment_mode.value === 'file' ? file.name : form.elements.attachment_link.value.trim();
    const body = new FormData(form);
    let saved = false;
    try {
      const response = await fetch(form.action, {method: 'POST', body, headers: {'X-Requested-With': 'XMLHttpRequest'}});
      const result = response.headers.get('Content-Type')?.includes('application/json') ? await response.json() : null;
      if (!response.ok || !result?.ok) throw new Error(result?.error || 'Không thể thêm đính kèm. Vui lòng thử lại.');
      saved = true;
      const updated = await refresh(section);
      const version = updated?.querySelector('.adm-attachment-card strong')?.textContent;
      notify({type: 'success', title: 'Đã thêm đính kèm', message: `Văn bản: ${documentNumber}\n${version ? `Phiên bản: ${version}\n` : ''}Tệp / Link: ${name}`});
    } catch (failure) {
      notify({type: saved ? 'warning' : 'error', title: saved ? 'Đã lưu đính kèm' : 'Không thể thêm đính kèm', message: `Văn bản: ${documentNumber}\nTệp / Link: ${name}\n${saved ? 'Đã lưu thành công nhưng chưa tải lại được danh sách. Mở lại Xem nhanh để xem phiên bản mới; không cần gửi lại.' : failure.message}`});
    } finally {
      submitting = false; submit.disabled = false; submit.textContent = 'Thêm đính kèm';
      if (saved) { form.reset(); close(); }
    }
  });
});
