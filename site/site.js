(() => {
  const year = document.querySelector("[data-year]");
  if (year) year.textContent = new Date().getFullYear();

  const toggle = document.querySelector("[data-menu-toggle]");
  const nav = document.querySelector("[data-primary-nav]");

  if (!toggle || !nav) return;

  const closeMenu = () => {
    toggle.setAttribute("aria-expanded", "false");
    nav.removeAttribute("data-open");
    document.body.removeAttribute("data-menu-open");
  };

  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    nav.toggleAttribute("data-open", !open);
    document.body.toggleAttribute("data-menu-open", !open);
  });

  nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  window.addEventListener("resize", () => {
    if (window.innerWidth > 760) closeMenu();
  });
})();
