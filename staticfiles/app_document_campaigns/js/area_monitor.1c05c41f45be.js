document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-area-monitor]");
  if (!root) return;
  const request = async form => {
    const response = await fetch(form.action, {method:"POST", body:new FormData(form), headers:{"X-Requested-With":"XMLHttpRequest", "Accept":"application/json"}, credentials:"same-origin"});
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) throw new Error(`Máy chủ trả dữ liệu không hợp lệ (HTTP ${response.status}).`);
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "Không thể thực hiện thao tác.");
    return data;
  };
  const showLink = (row, data, message) => {
    const result = row.querySelector("[data-area-link-result]");
    result.querySelector("input").value = data.url;
    result.hidden = false;
    row.querySelector(".dec-link-feedback").textContent = message;
    row.querySelector("[data-area-extend]").disabled = false;
  };
  root.querySelectorAll("[data-area-issue]").forEach(form => form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!confirm("Tạo link mới sẽ làm link QLKV cũ hết hiệu lực. Tiếp tục?")) return;
    const button=form.querySelector("button"); button.disabled=true;
    try { const data=await request(form); showLink(form.closest("[data-area-row]"),data,"Link chỉ hiện lần này. Hãy copy trước khi tải lại trang."); window.campaignToast?.("Đã tạo link QLKV.","success"); }
    catch(error){ window.campaignToast?.(error.message,"error"); }
    finally{button.disabled=false;}
  }));
  root.querySelectorAll("[data-area-email]").forEach(form => form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!confirm("Gửi email sẽ tạo link QLKV mới và vô hiệu link cũ. Tiếp tục?")) return;
    const button=form.querySelector("button"); button.disabled=true;
    try { const data=await request(form); showLink(form.closest("[data-area-row]"),data,data.message); window.campaignToast?.(data.message,"success"); }
    catch(error){ window.campaignToast?.(error.message,"error"); }
    finally{button.disabled=false;}
  }));
  root.querySelectorAll("[data-area-copy]").forEach(button => button.addEventListener("click", async () => {
    const input=button.parentElement.querySelector("input");
    try{await navigator.clipboard.writeText(input.value);}catch(_){input.select();document.execCommand("copy");}
    button.textContent="Đã copy"; setTimeout(()=>button.textContent="Copy",1500);
  }));
  const dialog=root.querySelector("[data-area-extend-dialog]");
  if(dialog){
    const form=dialog.querySelector("form"), errorBox=form.querySelector(".is-error");
    root.querySelectorAll("[data-area-extend]").forEach(button=>button.addEventListener("click",()=>{form.action=button.dataset.url;form.elements.expires_at.value=button.dataset.expires;dialog.querySelector("[data-area-extend-name]").textContent=button.closest("[data-area-row]").dataset.areaName;errorBox.hidden=true;dialog.showModal();}));
    dialog.querySelector("[data-area-extend-close]").addEventListener("click",()=>dialog.close());
    form.addEventListener("submit",async event=>{event.preventDefault();try{await request(form);location.reload();}catch(error){errorBox.textContent=error.message;errorBox.hidden=false;}});
  }
});
