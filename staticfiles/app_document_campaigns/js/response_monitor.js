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
    root.querySelector("[data-open-common-deadline]")?.addEventListener("click", () => {
      errorBox.hidden = true;
      window.campaignDateTimePicker?.refresh(commonDeadline);
      commonDeadline.showModal();
    });
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
  const closeEmailDialog = event => event.currentTarget.closest("dialog")?.close();
  root.querySelectorAll("[data-close-email-dialog]").forEach(button => button.addEventListener("click", closeEmailDialog));
  const configDialog = root.querySelector("[data-email-config-dialog]");
  const configForm = root.querySelector("[data-email-config-form]");
  let emailPreviewSample = null;
  const splitEmails = value => [...new Set((value || "").split(/[;,\n]+/).map(item => item.trim()).filter(Boolean).map(item => item.toLowerCase()))];
  const renderEmailTemplate = (template, context) => (template || "").replace(/{{\s*([a-z_]+)\s*}}/g, (token, key) => Object.hasOwn(context, key) ? context[key] : token);
  const updateEmailPreview = () => {
    if (!configForm || !emailPreviewSample) return;
    const context = {...emailPreviewSample.context, support_email: configForm.elements.support_email.value.trim()};
    const to = emailPreviewSample.to[0] || "—";
    const cc = splitEmails(configForm.elements.cc_emails_text.value);
    if (configForm.elements.cc_area_manager.checked && emailPreviewSample.area_email) cc.unshift(emailPreviewSample.area_email.toLowerCase());
    const uniqueCc = [...new Set(cc)].filter(email => email !== to.toLowerCase());
    const bcc = splitEmails(configForm.elements.bcc_emails_text.value).filter(email => email !== to.toLowerCase() && !uniqueCc.includes(email));
    const fromAddress = configForm.querySelector("[data-email-from-address]").value;
    const fromName = configForm.elements.from_name.value.trim();
    configDialog.querySelector("[data-live-preview-shop]").textContent = emailPreviewSample.shop;
    configDialog.querySelector("[data-live-preview-from]").textContent = fromName ? `${fromName} <${fromAddress}>` : fromAddress;
    configDialog.querySelector("[data-live-preview-to]").textContent = to;
    configDialog.querySelector("[data-live-preview-cc]").textContent = uniqueCc.join(", ") || "—";
    configDialog.querySelector("[data-live-preview-bcc]").textContent = bcc.join(", ") || "—";
    configDialog.querySelector("[data-live-preview-subject]").textContent = renderEmailTemplate(configForm.elements.subject_template.value, context) || "—";
    const bodyTemplate = window.campaignRichEmail?.html(configForm.elements.body_template) || configForm.elements.body_template.value;
    const bodyPreview = configDialog.querySelector("[data-live-preview-body]");
    if (window.campaignRichEmail) bodyPreview.innerHTML = window.campaignRichEmail.render(bodyTemplate, context) || "—";
    else bodyPreview.textContent = renderEmailTemplate(bodyTemplate, context) || "—";
  };
  const loadEmailPreview = async () => {
    const errorBox = configDialog.querySelector("[data-live-preview-error]");
    errorBox.hidden = true;
    try {
      const response = await fetch(configDialog.dataset.previewUrl, {credentials:"same-origin", cache:"no-store"});
      const data = await readJson(response);
      if (!response.ok || !data.ok) throw new Error(data.error || "Không thể tải dữ liệu xem trước.");
      emailPreviewSample = data;
      updateEmailPreview();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
    }
  };
  root.querySelector("[data-open-email-config]")?.addEventListener("click", () => {
    configDialog?.showModal();
    loadEmailPreview();
  });
  if (configForm) {
    let activeTemplateField = configForm.elements.body_template;
    [configForm.elements.subject_template, configForm.elements.body_template].forEach(field => {
      field?.addEventListener("focus", () => { activeTemplateField = field; });
    });
    configForm.querySelector("[data-rich-email-editor]")?.addEventListener("focus", () => { activeTemplateField = configForm.elements.body_template; });
    configForm.querySelectorAll("[data-email-variable]").forEach(button => button.addEventListener("click", () => {
      const field = activeTemplateField || configForm.elements.body_template;
      const token = `{{${button.dataset.emailVariable}}}`;
      if (field === configForm.elements.body_template && window.campaignRichEmail) {
        window.campaignRichEmail.insert(field, token);
      } else {
        const start = field.selectionStart ?? field.value.length, end = field.selectionEnd ?? start;
        field.setRangeText(token, start, end, "end"); field.focus();
      }
      updateEmailPreview();
    }));
    configForm.addEventListener("input", updateEmailPreview);
    configForm.addEventListener("change", updateEmailPreview);
    configForm.addEventListener("submit", async event => {
      event.preventDefault();
      const button = configForm.querySelector('[type="submit"]'), errorBox = configForm.querySelector("[data-email-config-error]");
      const originalLabel = button.textContent;
      button.disabled = true; button.classList.add("is-loading"); button.textContent = "Đang lưu…"; errorBox.hidden = true;
      try {
        const response = await fetch(configForm.action, {method:"POST", body:new FormData(configForm), credentials:"same-origin", headers:{"Accept":"application/json"}});
        const data = await readJson(response);
        if (!response.ok || !data.ok) {
          const details = data.errors ? Object.values(data.errors).flat().join(" ") : data.error;
          throw new Error(details || "Không thể lưu cấu hình email.");
        }
        configDialog.close(); window.campaignToast?.("Đã lưu cấu hình email chiến dịch.", "success");
      } catch (error) { errorBox.textContent = error.message; errorBox.hidden = false; }
      finally { button.disabled = false; button.classList.remove("is-loading"); button.textContent = originalLabel; }
    });
  }
  const preflightDialog = root.querySelector("[data-email-preflight-dialog]");
  root.querySelector("[data-open-email-preflight]")?.addEventListener("click", async () => {
    const content=preflightDialog.querySelector("[data-email-preflight-content]");content.replaceChildren(Object.assign(document.createElement("p"),{textContent:"Đang kiểm tra dữ liệu…"}));preflightDialog.showModal();
    try {
      const response=await fetch(preflightDialog.dataset.url,{credentials:"same-origin",cache:"no-store"}),data=await readJson(response);if(!response.ok||!data.ok)throw new Error(data.error||"Không thể kiểm tra người nhận.");
      const metrics=document.createElement("div");metrics.className="crm-preflight-metrics";[["Tổng PGD",data.total],["Có thể gửi",data.valid],["Email PGD lỗi",data.invalid],["Thiếu email QLKV",data.missing_area]].forEach(([label,value])=>{const card=document.createElement("article"),span=document.createElement("span"),strong=document.createElement("strong");span.textContent=label;strong.textContent=value;card.append(span,strong);metrics.append(card);});
      const list=document.createElement("ul");data.issues.forEach(item=>{const li=document.createElement("li"),shop=document.createElement("span"),issue=document.createElement("span");shop.textContent=item.shop;issue.textContent=item.issue;li.append(shop,issue);list.append(li);});if(!data.issues.length){const li=document.createElement("li");li.textContent="Không phát hiện lỗi người nhận.";list.append(li);}content.replaceChildren(metrics,list);
    } catch(error){content.replaceChildren(Object.assign(document.createElement("p"),{className:"crm-dialog-error",textContent:error.message}));}
  });
  const testDialog=root.querySelector("[data-email-test-dialog]"),testForm=root.querySelector("[data-email-test-form]");
  root.querySelector("[data-open-email-test]")?.addEventListener("click",()=>testDialog?.showModal());
  testForm?.addEventListener("submit",async event=>{event.preventDefault();const button=event.submitter||testForm.querySelector('button[type="submit"]'),errorBox=testForm.querySelector("[data-email-test-error]");if(button)button.disabled=true;errorBox.hidden=true;try{const response=await fetch(testForm.action,{method:"POST",body:new FormData(testForm),credentials:"same-origin",headers:{"Accept":"application/json"}}),data=await readJson(response);if(!response.ok||!data.ok)throw new Error(data.error||"Không thể gửi email thử.");testDialog.close();window.campaignToast?.(data.message,"success");}catch(error){errorBox.textContent=error.message;errorBox.hidden=false;}finally{if(button)button.disabled=false;}});
  const pollEmail = async (url, feedback, attempt = 0) => {
    try {
      const response = await fetch(url, {credentials:"same-origin", cache:"no-store"});
      if (!response.ok) throw new Error("Không kiểm tra được kết quả gửi email.");
      const data = await response.json();
      root.querySelector("[data-area-emailed]").textContent = new Intl.NumberFormat('en-US').format(data.area_emailed || 0);
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
      window.campaignDateTimePicker?.refresh(dialog);
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
