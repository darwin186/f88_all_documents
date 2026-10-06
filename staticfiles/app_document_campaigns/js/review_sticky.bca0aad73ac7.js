document.addEventListener("DOMContentLoaded", () => {
  const flow = document.querySelector(".campaign-flow");
  const grid = document.querySelector("[data-review-grid]");
  const table = grid?.querySelector("table");
  const head = table?.tHead;
  if (!flow || !grid || !table || !head) return;
  const navbar = document.querySelector("nav.fixed");
  flow.classList.add("is-review-sticky");
  const frozen = document.createElement("div");
  frozen.className = "review-frozen-head";
  frozen.hidden = true;
  frozen.setAttribute("aria-hidden", "true");
  frozen.inert = true;
  const clone = document.createElement("table");
  clone.className = "review-table";
  clone.appendChild(head.cloneNode(true));
  frozen.appendChild(clone);
  document.body.appendChild(frozen);
  const layout = () => {
    const navBottom = navbar ? navbar.getBoundingClientRect().bottom : 0;
    flow.style.top = `${navBottom}px`;
    const stickyBottom = Math.max(navBottom, flow.getBoundingClientRect().bottom);
    const rect = grid.getBoundingClientRect(), headRect = head.getBoundingClientRect();
    frozen.hidden = !(headRect.top < stickyBottom && rect.bottom > stickyBottom + headRect.height);
    frozen.style.top = `${stickyBottom}px`;
    frozen.style.left = `${rect.left}px`;
    frozen.style.width = `${grid.clientWidth}px`;
    frozen.style.height = `${headRect.height}px`;
    clone.style.width = `${table.getBoundingClientRect().width}px`;
    clone.style.transform = `translateX(${-grid.scrollLeft}px)`;
    [...head.rows[0].cells].forEach((cell, index) => {
      const target = clone.tHead.rows[0].cells[index];
      target.style.boxSizing = "border-box";
      target.style.width = `${cell.getBoundingClientRect().width}px`;
    });
  };
  let frame = false;
  const schedule = () => {
    if (frame) return;
    frame = true;
    requestAnimationFrame(() => { frame = false; layout(); });
  };
  window.addEventListener("scroll", schedule, {passive: true});
  window.addEventListener("resize", schedule);
  grid.addEventListener("scroll", schedule, {passive: true});
  new ResizeObserver(schedule).observe(flow);
  schedule();
});
