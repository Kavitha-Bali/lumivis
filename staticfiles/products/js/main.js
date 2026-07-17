/* ── Hamburger menu ── */
const hamburger = document.getElementById('hamburger');
const drawer    = document.getElementById('mobileDrawer');

if (hamburger && drawer) {
  hamburger.addEventListener('click', () => {
    const isOpen = drawer.classList.toggle('open');
    hamburger.classList.toggle('open', isOpen);
    hamburger.setAttribute('aria-expanded', isOpen);
    drawer.setAttribute('aria-hidden', !isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 800 && drawer.classList.contains('open')) {
      drawer.classList.remove('open');
      hamburger.classList.remove('open');
      hamburger.setAttribute('aria-expanded', false);
      drawer.setAttribute('aria-hidden', true);
      document.body.style.overflow = '';
    }
  });
}

/* ── Auto-dismiss alert messages after 4 s ── */
document.querySelectorAll('.alert').forEach(el => {
  setTimeout(() => el.remove(), 4000);
});
