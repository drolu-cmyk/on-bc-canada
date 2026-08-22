(() => {
  const year = document.querySelector("[data-year]");
  if (year) year.textContent = new Date().getFullYear();

  const toggle = document.querySelector("[data-menu-toggle]");
  const nav = document.querySelector("[data-primary-nav]");

  if (!toggle || !nav) return;

  const setMenuState = (open, returnFocus = false) => {
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    nav.toggleAttribute("data-open", open);
    document.body.toggleAttribute("data-menu-open", open);
    if (!open && returnFocus) toggle.focus();
  };

  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    setMenuState(!open);
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => setMenuState(false));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      setMenuState(false, true);
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 760) setMenuState(false);
  });
})();
