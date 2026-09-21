document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-response-monitor]");
  if (!root) return;
  const readJson = async response => {
    if (response.redirected || response.url.includes("/login")) {
      throw new Error("Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử lại.");
    }
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      const text = await response.text();
      const title = text.match(/<title[^>]*>([^<]+)<\/title>/i)?.[1]?.trim();
      throw new Error(title && !title.startsWith("Error")
        ? title
        : `Máy chủ trả về dữ liệu không hợp lệ (HTTP ${response.status}).`);
    }
    return response.json();
  };
  const filters = root.querySelector("[data-linked-filters]");
  const region = filters.elements.region, area = filters.elements.area, shop = filters.elements.shop;
  const linkFilters = () => {
    [...area.options].forEach(option => { option.hidden = !!option.value && !!region.value && option.dataset.region !== region.value; });
    if (area.selectedOptions[0]?.hidden) area.value = "";
    [...shop.options].forEach(option => { option.hidden = !!option.value && ((!!region.value && option.dataset.region !== region.value) || (!!area.value && option.dataset.area !== area.value)); });
    if (shop.selectedOptions[0]?.hidden) shop.value = "";
  };
  region.addEventListener("change", linkFilters); area.addEventListener("change", linkFilters); linkFilters();
  const commonDeadline = root.querySelector("[data-common-deadline-dialog]");
  if (commonDeadline) {
    const form = commonDeadline.querySelector("form"), errorBox = form.querySelector("[data-common-deadline-error]");
    root.querySelector("[data-open-common-deadline]").addEventListener("click", () => {errorBox.hidden = true; commonDeadline.showModal();});
    commonDeadline.querySelector("[data-close-common-deadline]").addEventListener("click", () => commonDeadline.close());
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]'); button.disabled = true; errorBox.hidden = true;
      try {
        const response = await fetch(form.action, {method:"POST", body:new FormData(form), headers:{"X-Requested-With":"XMLHttpRequest", "Accept":"application/json"}, credentials:"same-origin"});
        const data = await readJson(response);
        if (!response.ok || !data.ok) throw new Error(data.error || "Không thể cập nhật deadline.");
        window.location.reload();
      } catch (error) {errorBox.textContent = error.message; errorBox.hidden = false;}
      finally {button.disabled = false;}
    });
  }
  const pollEmail = async (url, feedback, attempt = 0) => {
    try {
      const response = await fetch(url, {credentials:"same-origin", cache:"no-store"});
      if (!response.ok) throw new Error("Không kiểm tra được kết quả gửi email.");
      const data = await response.json();
      root.querySelector("[data-area-emailed]").textContent = data.area_emailed;
      if (["sent", "failed", "skipped"].includes(data.status)) {
        feedback.textContent = data.message;
        feedback.classList.toggle("is-error", data.status !== "sent");
        window.campaignToast?.(data.message, data.status === "sent" ? "success" : "error");
        return;
      }
    } catch (error) {feedback.textContent = error.message;}
    if (attempt < 45) window.setTimeout(() => pollEmail(url, feedback, attempt + 1), 2000);
    else feedback.textContent = "Chưa có kết quả gửi email. Tải lại trang để cập nhật thống kê sau.";
  };
  root.querySelectorAll("[data-email-link]").forEach(form => form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!window.confirm("Gửi email sẽ tạo link mới, vô hiệu link cũ và CC các quản lý hiện tại. Tiếp tục?")) return;
    const button = form.querySelector("button"); button.disabled = true;
    const row = form.closest("[data-shop-link-row]");
    try {
      const response = await fetch(form.action, {method:"POST", body:new FormData(form), credentials:"same-origin"});
      const data = await response.json();
      if (data.url) { row.querySelector("[data-link-url]").value = data.url; row.querySelector("[data-link-result]").hidden = false; }
      if (!response.ok) throw new Error(data.error || "Không thể gửi email.");
      window.campaignToast?.(data.message, "success");
      if (data.status_url) {
        const feedback = row.querySelector("[data-link-feedback]");
        feedback.textContent = "Đang chờ kết quả gửi email…";
        pollEmail(data.status_url, feedback);
      }
    } catch (error) { window.campaignToast?.(error.message, "error"); }
    finally { button.disabled = false; }
  }));
  const dialog = root.querySelector("[data-extend-dialog]");
  if (dialog) {
    const form = dialog.querySelector("form");
    root.querySelectorAll("[data-extend-deadline]").forEach(button => button.addEventListener("click", () => {
      form.action = button.dataset.url;
      form.elements.deadline.value = button.dataset.deadline;
      dialog.querySelector("[data-extend-shop]").textContent = button.closest("[data-shop-link-row]").dataset.shopName;
      dialog.showModal();
    }));
    dialog.querySelector("[data-close-extend]").addEventListener("click", () => dialog.close());
    form.addEventListener("submit", async event => {
      event.preventDefault(); const button = form.querySelector('button:not([type="button"])'); button.disabled = true;
      try {
        const response = await fetch(form.action, {method:"POST", body:new FormData(form), credentials:"same-origin"});
        const data = await response.json(); if (!response.ok) throw new Error(data.error || "Không thể gia hạn.");
        window.location.reload();
      } catch (error) { window.campaignToast?.(error.message, "error"); }
      finally { button.disabled = false; }
    });
  }
  const flow = document.querySelector(".campaign-flow");
  const grid = root.querySelector("[data-freeze-grid]"), table = grid.querySelector("table"), head = table.tHead;
  const navbar = document.querySelector("nav.fixed");
  flow.classList.add("is-monitor-sticky");
  const frozen = document.createElement("div"); frozen.className = "crm-frozen-head"; frozen.hidden = true; frozen.setAttribute("aria-hidden", "true"); frozen.inert = true;
  const clone = document.createElement("table"); clone.className = "crm-table"; clone.appendChild(head.cloneNode(true)); frozen.appendChild(clone); document.body.appendChild(frozen);
  const layout = () => {
    const navBottom = navbar ? navbar.getBoundingClientRect().bottom : 0;
    flow.style.top = `${navBottom}px`;
    const top = Math.max(navBottom, flow.getBoundingClientRect().bottom);
    const rect = grid.getBoundingClientRect(), headRect = head.getBoundingClientRect();
    frozen.hidden = !(headRect.top < top && rect.bottom > top + headRect.height);
    frozen.style.top = `${top}px`; frozen.style.left = `${rect.left}px`; frozen.style.width = `${grid.clientWidth}px`; frozen.style.height = `${headRect.height}px`;
    clone.style.width = `${table.getBoundingClientRect().width}px`; clone.style.transform = `translateX(${-grid.scrollLeft}px)`;
    [...head.rows[0].cells].forEach((cell,index) => { const target = clone.tHead.rows[0].cells[index]; target.style.boxSizing = "border-box"; target.style.width = `${cell.getBoundingClientRect().width}px`; });
  };
  let frame = false;
  const schedule = () => { if (frame) return; frame = true; requestAnimationFrame(() => {frame = false; layout();}); };
  window.addEventListener("scroll", schedule, {passive:true}); window.addEventListener("resize", schedule); grid.addEventListener("scroll", schedule, {passive:true});
  new ResizeObserver(schedule).observe(flow); schedule();
});
