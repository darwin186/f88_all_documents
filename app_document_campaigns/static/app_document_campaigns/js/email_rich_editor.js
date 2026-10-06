document.addEventListener("DOMContentLoaded", () => {
  const allowedTags = new Set(["P", "BR", "DIV", "STRONG", "B", "EM", "I", "U", "S", "UL", "OL", "LI", "BLOCKQUOTE", "H2", "H3", "A"]);
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const safeHref = value => {
    const href = (value || "").trim();
    if (/\{\{[^{}]+}}/.test(href)) return href;
    try { return ["http:", "https:", "mailto:"].includes(new URL(href).protocol) ? href : ""; }
    catch (_) { return ""; }
  };
  const sanitize = html => {
    const template = document.createElement("template");
    template.innerHTML = html || "";
    const clean = node => {
      [...node.childNodes].forEach(child => {
        if (child.nodeType === Node.COMMENT_NODE) { child.remove(); return; }
        if (child.nodeType !== Node.ELEMENT_NODE) return;
        if (!allowedTags.has(child.tagName)) {
          child.replaceWith(...child.childNodes);
          return;
        }
        const href = child.tagName === "A" ? safeHref(child.getAttribute("href")) : "";
        [...child.attributes].forEach(attribute => child.removeAttribute(attribute.name));
        if (child.tagName === "A" && href) {
          child.setAttribute("href", href);
          child.setAttribute("target", "_blank");
          child.setAttribute("rel", "noopener noreferrer");
        }
        clean(child);
      });
    };
    clean(template.content);
    return template.innerHTML.trim();
  };
  const initialHtml = value => /<\/?[a-z][^>]*>/i.test(value || "")
    ? sanitize(value)
    : escapeHtml(value || "").replace(/\r\n?|\n/g, "<br>");
  const render = (template, context) => sanitize((template || "").replace(/{{\s*([a-z_]+)\s*}}/g, (token, key) => Object.hasOwn(context, key) ? escapeHtml(context[key]) : token));

  document.querySelectorAll("[data-rich-email-field]").forEach(wrapper => {
    const source = wrapper.querySelector("textarea");
    const editor = wrapper.querySelector("[data-rich-email-editor]");
    if (!source || !editor) return;
    editor.innerHTML = initialHtml(source.value);
    let savedRange = null;
    const rememberSelection = () => {
      const selection = window.getSelection();
      if (selection?.rangeCount && editor.contains(selection.anchorNode)) savedRange = selection.getRangeAt(0).cloneRange();
    };
    const sync = (notify = true) => {
      const cleaned = sanitize(editor.innerHTML);
      source.value = cleaned;
      if (notify) source.dispatchEvent(new Event("input", {bubbles: true}));
      return cleaned;
    };
    const restoreSelection = () => {
      editor.focus();
      if (!savedRange) return;
      const selection = window.getSelection();
      selection.removeAllRanges(); selection.addRange(savedRange);
    };
    editor.addEventListener("input", () => { rememberSelection(); sync(); });
    editor.addEventListener("keyup", rememberSelection);
    editor.addEventListener("mouseup", rememberSelection);
    editor.addEventListener("paste", () => setTimeout(() => { editor.innerHTML = sync(false); sync(); }, 0));
    wrapper.querySelectorAll("[data-rich-command]").forEach(button => {
      button.addEventListener("mousedown", event => event.preventDefault());
      button.addEventListener("click", () => {
        restoreSelection();
        const command = button.dataset.richCommand;
        if (command === "createLink") {
          const href = window.prompt("Nhập URL hoặc tham số link, ví dụ {{response_url}}:", "https://");
          if (!href) return;
          if (!safeHref(href)) { window.campaignToast?.("Liên kết không hợp lệ.", "error"); return; }
          document.execCommand("createLink", false, href);
        } else {
          document.execCommand(command, false, null);
        }
        rememberSelection(); sync();
      });
    });
    source._richEmail = {
      insert(token) { restoreSelection(); document.execCommand("insertText", false, token); rememberSelection(); sync(); },
      html() { return sync(false); },
    };
    source.closest("form")?.addEventListener("submit", () => sync(false));
  });

  window.campaignRichEmail = {
    sanitize,
    render,
    insert(source, token) { source?._richEmail?.insert(token); },
    html(source) { return source?._richEmail?.html() ?? sanitize(source?.value || ""); },
  };
});
