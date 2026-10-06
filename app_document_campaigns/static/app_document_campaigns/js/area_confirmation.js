document.addEventListener("DOMContentLoaded", () => {
  if (window.__areaConfirmationInitialized) return;
  window.__areaConfirmationInitialized = true;

  const tableWrap = document.querySelector("[data-area-table-wrap]");
  const sourceTable = tableWrap?.querySelector("[data-area-table]");
  const sourceHead = sourceTable?.querySelector("thead");
  if (tableWrap && sourceTable && sourceHead) {
    const sticky = document.createElement("div");
    sticky.className = "am-sticky-head";
    sticky.hidden = true;
    const stickyTable = document.createElement("table");
    stickyTable.className = sourceTable.className;
    stickyTable.append(sourceHead.cloneNode(true));
    sticky.append(stickyTable);
    document.body.append(sticky);

    const syncSticky = () => {
      const navbar = document.querySelector(".am-head");
      const top = navbar?.getBoundingClientRect().bottom || 0;
      const wrapRect = tableWrap.getBoundingClientRect();
      const headHeight = sourceHead.getBoundingClientRect().height;
      const visible = wrapRect.top < top && wrapRect.bottom > top + headHeight;
      sticky.hidden = !visible;
      if (!visible) return;
      sticky.style.top = `${top}px`;
      sticky.style.left = `${wrapRect.left}px`;
      sticky.style.width = `${wrapRect.width}px`;
      sticky.style.height = `${headHeight}px`;
      stickyTable.style.width = `${sourceTable.scrollWidth}px`;
      stickyTable.style.transform = `translateX(${-tableWrap.scrollLeft}px)`;
      const sourceCells = sourceHead.querySelectorAll("th");
      stickyTable.querySelectorAll("th").forEach((cell, index) => {
        const width = sourceCells[index]?.getBoundingClientRect().width || 0;
        cell.style.width = `${width}px`;
        cell.style.minWidth = `${width}px`;
        cell.style.maxWidth = `${width}px`;
      });
    };
    window.addEventListener("scroll", syncSticky, {passive: true});
    window.addEventListener("resize", syncSticky);
    tableWrap.addEventListener("scroll", syncSticky, {passive: true});
    syncSticky();
  }

  const root = document.querySelector("[data-area-autosave-root]");
  if (!root) return;

  const csrf = document.querySelector("[data-csrf-token] input[name=csrfmiddlewaretoken]")?.value || "";
  const states = new WeakMap();
  const rows = [...document.querySelectorAll("[data-area-confirm]")];
  const notify = (message, type) => {
    if (window.campaignToast) window.campaignToast(message, type);
    else if (type === "error") window.alert(message);
  };

  const stateFor = (row) => {
    if (!states.has(row)) states.set(row, {timer: null, dirty: false, saving: false});
    return states.get(row);
  };

  const feedback = (row, text, className = "") => {
    const item = row.querySelector("[data-area-save-state]");
    item.textContent = text;
    item.className = className;
  };

  const selectedDecision = (row) => {
    const value = row.querySelector('input[type="radio"]:checked')?.value;
    return value === "true" ? true : value === "false" ? false : null;
  };

  const postJson = async (url, payload) => {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRFToken": csrf, "Accept": "application/json"},
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({ok: false, error: "Phản hồi máy chủ không hợp lệ."}));
    if (!response.ok || !data.ok) {
      const error = new Error(data.error || "Không lưu được xác nhận.");
      error.status = response.status;
      throw error;
    }
    return data;
  };

  const saveRow = async (row) => {
    const state = stateFor(row);
    if (state.saving || !state.dirty) return;
    const decision = selectedDecision(row);
    if (decision === null) {
      feedback(row, "Chọn Đồng thuận hoặc Không đồng thuận trước khi ghi chú.", "is-error");
      return;
    }
    state.dirty = false;
    state.saving = true;
    feedback(row, "Đang tự động lưu…", "is-saving");
    try {
      const data = await postJson(row.dataset.url, {
        decision,
        note: row.querySelector("textarea").value,
        expected_confirmation_id: row.dataset.confirmationId ? Number(row.dataset.confirmationId) : null,
      });
      row.dataset.confirmationId = String(data.confirmation_id);
      feedback(row, `Đã lưu · ${data.completed}/${data.total} dòng`, "is-saved");
    } catch (error) {
      state.dirty = ![409, 410].includes(error.status);
      feedback(row, error.status === 409 ? "Dữ liệu đã đổi ở cửa sổ khác. Hãy tải lại trang." : error.message, "is-error");
    } finally {
      state.saving = false;
      if (state.dirty) {
        clearTimeout(state.timer);
        state.timer = window.setTimeout(() => saveRow(row), 1200);
      }
    }
  };

  const queueRow = (row, delay) => {
    const state = stateFor(row);
    state.dirty = true;
    clearTimeout(state.timer);
    feedback(row, "Có thay đổi chưa lưu", "is-saving");
    state.timer = window.setTimeout(() => saveRow(row), delay);
  };

  const flush = async () => {
    rows.forEach((row) => clearTimeout(stateFor(row).timer));
    await Promise.all(rows.map(async (row) => {
      const state = stateFor(row);
      if (state.saving) {
        while (state.saving) await new Promise((resolve) => window.setTimeout(resolve, 60));
      }
      if (state.dirty) await saveRow(row);
    }));
  };

  rows.forEach((row) => {
    row.querySelectorAll('input[type="radio"]').forEach((input) => {
      input.addEventListener("change", () => queueRow(row, 150));
    });
    row.querySelector("textarea").addEventListener("input", () => queueRow(row, 800));
  });

  const bulkButton = document.querySelector("[data-agree-all]");
  bulkButton?.addEventListener("click", async () => {
    if (!window.confirm("Đồng thuận tất cả các dòng thuộc bộ lọc hiện tại? Các kết luận Không đồng thuận hiện có cũng sẽ được đổi.")) return;
    bulkButton.disabled = true;
    const original = bulkButton.textContent;
    bulkButton.textContent = "Đang cập nhật…";
    try {
      await flush();
      const params = new URLSearchParams(new FormData(document.querySelector(".am-filter")));
      const data = await postJson(root.dataset.bulkUrl, Object.fromEntries(params.entries()));
      notify(`Đã đồng thuận ${data.updated} dòng.`, "success");
      window.setTimeout(() => window.location.reload(), 500);
    } catch (error) {
      notify(error.message, "error");
      bulkButton.disabled = false;
      bulkButton.textContent = original;
    }
  });

  document.querySelector(".am-filter")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await flush();
      event.currentTarget.submit();
    } catch (error) {
      notify("Chưa lưu được thay đổi. Vui lòng thử lại trước khi lọc.", "error");
    }
  });
});
