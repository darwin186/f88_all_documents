(() => {
  if (window.adminDocumentNotify) return;
  // Thông báo dùng chung của bộ kit (static/js/ui-toast.js). Giữ API cũ để mã hiện có không phải sửa.
  window.adminDocumentNotify = options => window.uiToast(options);
  const notify = window.adminDocumentNotify;
  let invalidFields = new Map(), validationTimer;
  document.addEventListener('invalid', event => {
    const input = event.target;
    event.preventDefault();
    const fieldLabels = {doc_type: 'Loại văn bản', issuing_company: 'Công ty ban hành', issuing_department: 'Phòng ban', signer_role: 'Người ký', content_type: 'Loại nội dung', title: 'Tên văn bản', status: 'Trạng thái', issue_date: 'Ngày ban hành', effective_date: 'Ngày hiệu lực', expiry_date: 'Ngày hết hiệu lực', attachment: 'Tệp đính kèm', attachment_link: 'Link đính kèm', receiving_company: 'Công ty nhận'};
    const label = input.labels?.[0]?.textContent.replace(/\s*\*\s*$/, '').trim() || fieldLabels[input.name] || input.getAttribute('aria-label') || input.placeholder || 'Trường bắt buộc';
    const detail = input.validity.valueMissing ? 'Vui lòng nhập hoặc chọn giá trị.' : input.validity.typeMismatch && input.type === 'url' ? 'Link không hợp lệ. Vui lòng nhập địa chỉ đầy đủ (https://...).': input.validationMessage;
    invalidFields.set(input, `${label}: ${detail}`);
    clearTimeout(validationTimer);
    validationTimer = setTimeout(() => {
      notify({type: 'error', title: 'Vui lòng kiểm tra thông tin', message: [...invalidFields.values()].join('\n')});
      const first = invalidFields.keys().next().value;
      if (first?.getClientRects().length && !first.classList.contains('sr-only')) first.focus();
      invalidFields.clear();
    }, 0);
  }, true);
})();
