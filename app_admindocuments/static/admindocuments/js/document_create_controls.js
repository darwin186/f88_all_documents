/* Form "Tạo văn bản hành chính": các quan hệ giữa các droplist (ui-select). */
(() => {
  const form = document.querySelector('[data-adm-create-form]');
  if (!form) return;
  const fire = select => select.dispatchEvent(new Event('change', {bubbles: true}));

  // Phòng ban chỉ hiện các phòng thuộc công ty đang chọn (option[hidden] bị ui-select bỏ qua).
  const department = form.querySelector('select[data-company-filtered-by]');
  const company = department && document.getElementById(department.dataset.companyFilteredBy);
  const filterDepartments = () => {
    const companyId = company?.value || '';
    [...department.options].forEach(option => { if (option.value) option.hidden = Boolean(companyId) && option.dataset.company !== companyId; });
    if (department.selectedOptions[0]?.hidden) { department.value = ''; fire(department); }
  };
  if (department && company) { company.addEventListener('change', filterDepartments); filterDepartments(); }

  // Chọn văn bản tham chiếu: điền số hiệu nếu đang trống; bỏ chọn thì xóa số hiệu và bỏ cờ tham chiếu.
  const reference = form.querySelector('[data-reference-select]');
  const referenceNumber = document.getElementById('referenceNumberInput');
  const referenceFlag = form.querySelector('input[name="is_reference_document"]');
  reference?.addEventListener('change', () => {
    if (reference.value) {
      const number = reference.selectedOptions[0]?.dataset.number;
      if (referenceNumber && !referenceNumber.value.trim() && number) referenceNumber.value = number;
    } else {
      if (referenceNumber) referenceNumber.value = '';
      if (referenceFlag) referenceFlag.checked = false;
    }
  });
  // Mở form sẵn khi đi vào từ liên kết "tạo văn bản tham chiếu" (?ref=<id>).
  if (reference?.value) {
    if (referenceFlag) referenceFlag.checked = true;
    const opener = document.querySelector('[data-modal-target="docModal"]');
    if (opener) window.addEventListener('load', () => opener.click(), {once: true});
  }
})();
