// Poll each [data-poll] box that shows a running job and swap in its fresh HTML; the rest of the page stays put.
// Buttons marked data-busy inside the box's [data-scope] (or the page) are re-enabled when its job ends.
document.querySelectorAll("[data-poll]").forEach(box => {
  if (!box.querySelector(".job-running")) return;
  const tick = async () => {
    try {
      const r = await fetch(box.dataset.poll);
      if (r.redirected) return;  // Logged out: the login page came back, not the panel.
      if (r.ok) box.innerHTML = await r.text();
    } catch (e) {}  // Network blip: try again next tick.
    if (box.querySelector(".job-running")) return setTimeout(tick, 3000);
    (box.closest("[data-scope]") || document).querySelectorAll("button[data-busy]").forEach(b => b.disabled = false);
    box.firstElementChild?.insertAdjacentHTML("beforeend", '<a href="">Reload to see the new results</a>');
  };
  setTimeout(tick, 3000);
});
