(function () {
  const initPickers = () => {
    if (!window.flatpickr) return;
    if (window.flatpickr.l10ns?.vn) {
      window.flatpickr.localize(window.flatpickr.l10ns.vn);
    }

    const monthInput = document.querySelector("[data-campaign-month]");
    const calendarLocale = { ...(window.flatpickr.l10ns?.vn || {}), firstDayOfWeek: 1 };
    const typeSelect = document.querySelector("select[name='campaign_type']");
    const codePreview = document.querySelector("[data-campaign-code-preview]");
    const updateCodePreview = () => {
      if (!codePreview) return;
      const prefix = typeSelect?.selectedOptions?.[0]?.dataset?.codePrefix || "";
      const period = (monthInput?.value || "").replace("-", "");
      codePreview.textContent = prefix && period
        ? `${prefix.toUpperCase()}-${period}`
        : "Chọn loại và tháng chứng từ";
    };
    if (monthInput && window.monthSelectPlugin) {
      window.flatpickr(monthInput, {
        locale: calendarLocale,
        allowInput: false,
        disableMobile: true,
        dateFormat: "Y-m",
        altInput: true,
        altFormat: "m/Y",
        monthSelectorType: "static",
        plugins: [
          new window.monthSelectPlugin({
            shorthand: true,
            dateFormat: "Y-m",
            altFormat: "m/Y",
            theme: "light",
          }),
        ],
        onChange: updateCodePreview,
        onValueUpdate: updateCodePreview,
      });
    }
    typeSelect?.addEventListener("change", updateCodePreview);
    updateCodePreview();

    const deadlineInput = document.querySelector("[data-campaign-deadline]");
    if (deadlineInput) {
      window.flatpickr(deadlineInput, {
        allowInput: false,
        disableMobile: true,
        enableTime: true,
        time_24hr: true,
        minuteIncrement: 15,
        dateFormat: "Y-m-d\\TH:i",
        altInput: true,
        altFormat: "d/m/Y H:i",
        monthSelectorType: "static",
        locale: calendarLocale,
      });
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPickers);
  } else {
    initPickers();
  }
})();
