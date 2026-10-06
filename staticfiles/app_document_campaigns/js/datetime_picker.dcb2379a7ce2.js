(function () {
  const instances = new WeakMap();
  const pad = value => String(value).padStart(2, "0");

  const init = root => {
    if (!root || instances.has(root) || !window.flatpickr) return;
    const source = root.querySelector("[data-datetime-source] input");
    const dateInput = root.querySelector("[data-datetime-date]");
    const timeSelect = root.querySelector("[data-datetime-time]");
    if (!source || !dateInput || !timeSelect) return;
    for (let minutes = 0; minutes < 24 * 60; minutes += 15) {
      const value = `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
      timeSelect.add(new Option(value, value));
    }
    const addTime = value => {
      if (!value || [...timeSelect.options].some(option => option.value === value)) return;
      const option = new Option(value, value);
      const next = [...timeSelect.options].find(item => item.value > value);
      timeSelect.add(option, next || null);
    };
    let dateValue = "";
    const writeSource = () => {
      source.value = dateValue && timeSelect.value ? `${dateValue}T${timeSelect.value}` : "";
      source.dispatchEvent(new Event("input", {bubbles: true}));
    };
    const calendarLocale = {...(window.flatpickr.l10ns?.vn || {}), firstDayOfWeek: 1};
    const picker = window.flatpickr(dateInput, {
      locale: calendarLocale,
      dateFormat: "d/m/Y",
      allowInput: false,
      disableMobile: true,
      static: true,
      onChange: selected => {
        if (!selected[0]) return;
        dateValue = picker.formatDate(selected[0], "Y-m-d");
        writeSource();
      },
    });
    const refresh = () => {
      const [date = "", rawTime = ""] = (source.value || "").split("T");
      const time = rawTime.slice(0, 5);
      dateValue = date;
      addTime(time);
      timeSelect.value = time || "00:00";
      picker.setDate(date, false, "Y-m-d");
    };
    timeSelect.addEventListener("change", writeSource);
    source.addEventListener("change", refresh);
    instances.set(root, {refresh, source});
    refresh();
  };

  const initAll = scope => (scope || document).querySelectorAll("[data-campaign-datetime]").forEach(init);
  window.campaignDateTimePicker = {
    initAll,
    refresh(scope) {
      (scope.matches?.("[data-campaign-datetime]") ? [scope] : scope.querySelectorAll("[data-campaign-datetime]"))
        .forEach(root => { init(root); instances.get(root)?.refresh(); });
    },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => initAll(document));
  else initAll(document);
})();
