/* ================================================================
   HOME PAGE — ENHANCED INTERACTIVITY
   ================================================================ */

(function () {
  'use strict';

  // ── Animated counters in hero stats ───────────────────────────
  function animateCounter(el) {
    const target  = parseInt(el.dataset.target, 10);
    if (!target) return;
    const duration = 1800;
    const start    = performance.now();
    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      // ease-out-quart
      const eased = 1 - Math.pow(1 - progress, 4);
      const value  = Math.floor(eased * target);
      el.textContent = target >= 1000
        ? (value >= 1000 ? (value / 1000).toFixed(1) + 'k+' : value.toString())
        : value.toString();
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = target >= 1000 ? (target / 1000).toFixed(1) + 'k+' : target.toString();
    }
    requestAnimationFrame(step);
  }

  if ('IntersectionObserver' in window) {
    const counterObs = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          animateCounter(e.target);
          counterObs.unobserve(e.target);
        }
      });
    }, { threshold: 0.5 });
    document.querySelectorAll('.counter[data-target]').forEach(el => counterObs.observe(el));
  } else {
    document.querySelectorAll('.counter[data-target]').forEach(animateCounter);
  }

  // ── Flash-sale countdown timer ─────────────────────────────────
  const cdH = document.getElementById('cd-h');
  const cdM = document.getElementById('cd-m');
  const cdS = document.getElementById('cd-s');

  if (cdH && cdM && cdS) {
    // Store expiry in sessionStorage so it persists on reload within tab
    const EXPIRY_KEY = 'lumivis_sale_expiry';
    let expiry = parseInt(sessionStorage.getItem(EXPIRY_KEY) || '0', 10);
    if (!expiry || expiry < Date.now()) {
      expiry = Date.now() + 12 * 3600 * 1000; // 12 hours from now
      sessionStorage.setItem(EXPIRY_KEY, expiry);
    }

    function pad(n) { return String(n).padStart(2, '0'); }
    function tick(el) {
      el.classList.add('tick');
      setTimeout(() => el.classList.remove('tick'), 120);
    }

    let prevS = -1;
    const timer = setInterval(() => {
      const diff = Math.max(0, expiry - Date.now());
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      if (s !== prevS) {
        cdS.textContent = pad(s);
        tick(cdS);
        if (s === 59) { cdM.textContent = pad(m); tick(cdM); }
        if (m === 59 && s === 59) { cdH.textContent = pad(h); tick(cdH); }
        cdH.textContent = pad(h);
        cdM.textContent = pad(m);
        prevS = s;
      }
      if (diff === 0) clearInterval(timer);
    }, 500);
  }

  // ── Featured carousel ──────────────────────────────────────────
  const carousel   = document.getElementById('featuredCarousel');
  const prevBtn    = document.getElementById('carouselPrev');
  const nextBtn    = document.getElementById('carouselNext');

  if (carousel && prevBtn && nextBtn) {
    const CARD_W   = 220; // card width + gap
    let offset     = 0;
    let isDragging = false;
    let startX     = 0;
    let startOff   = 0;

    function clampOffset(val) {
      const maxOff = Math.max(0, carousel.scrollWidth - carousel.parentElement.clientWidth);
      return Math.max(0, Math.min(val, maxOff));
    }
    function applyOffset(val, animated) {
      offset = clampOffset(val);
      carousel.style.transition = animated ? '' : 'none';
      carousel.style.transform  = `translateX(-${offset}px)`;
    }

    nextBtn.addEventListener('click', () => applyOffset(offset + CARD_W * 2, true));
    prevBtn.addEventListener('click', () => applyOffset(offset - CARD_W * 2, true));

    // Drag / swipe
    carousel.addEventListener('mousedown', e => { isDragging = true; startX = e.clientX; startOff = offset; carousel.classList.add('dragging'); });
    document.addEventListener('mousemove', e => { if (!isDragging) return; applyOffset(startOff - (e.clientX - startX), false); });
    document.addEventListener('mouseup',   () => { isDragging = false; carousel.classList.remove('dragging'); });
    carousel.addEventListener('touchstart', e => { startX = e.touches[0].clientX; startOff = offset; }, { passive: true });
    carousel.addEventListener('touchmove',  e => { applyOffset(startOff - (e.touches[0].clientX - startX), false); }, { passive: true });
  }

  // ── Category cards → jump to products and filter ──────────────
  window.jumpToProducts = function (type) {
    const section = document.getElementById('products-section');
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(() => {
      const targetPill = Array.from(document.querySelectorAll('.pill')).find(p => p.dataset.filter === type);
      if (targetPill) targetPill.click();
    }, 400);
  };

  // ── Category filter pills ──────────────────────────────────────
  const pills        = document.querySelectorAll('.pill');
  const grid         = document.getElementById('productsGrid');
  const filterEmpty  = document.getElementById('filterEmpty');
  const visibleCount = document.getElementById('visibleCount');

  function updateCount(cards) {
    const shown = cards.filter(c => !c.classList.contains('hidden')).length;
    if (visibleCount) visibleCount.textContent = shown;
    if (filterEmpty) filterEmpty.classList.toggle('hidden', shown > 0);
  }

  function filterCards(type) {
    const cards = Array.from(grid ? grid.querySelectorAll('.card') : []);
    cards.forEach(card => {
      const match = type === 'all' || card.dataset.type === type;
      card.classList.toggle('hidden', !match);
    });
    updateCount(cards);
  }

  pills.forEach(btn => {
    btn.addEventListener('click', () => {
      pills.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      filterCards(btn.dataset.filter);
      const sortSel = document.getElementById('sortSelect');
      if (sortSel) { sortSel.value = 'default'; sortCards('default'); }
    });
  });

  // ── Sort ───────────────────────────────────────────────────────
  function sortCards(mode) {
    if (!grid) return;
    const cards = Array.from(grid.querySelectorAll('.card'));
    cards.sort((a, b) => {
      if (mode === 'price-asc')  return parseFloat(a.dataset.price) - parseFloat(b.dataset.price);
      if (mode === 'price-desc') return parseFloat(b.dataset.price) - parseFloat(a.dataset.price);
      if (mode === 'name-asc')   return (a.dataset.name || '').localeCompare(b.dataset.name || '');
      return 0;
    });
    cards.forEach(c => grid.appendChild(c));
  }

  const sortSel = document.getElementById('sortSelect');
  if (sortSel) sortSel.addEventListener('change', () => sortCards(sortSel.value));

  // ── Card entrance reveal (IntersectionObserver) ────────────────
  if ('IntersectionObserver' in window) {
    const revealObs = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          revealObs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    document.querySelectorAll('.card.reveal').forEach((card, i) => {
      card.style.transitionDelay = (i % 8) * 55 + 'ms';
      revealObs.observe(card);
    });
  } else {
    document.querySelectorAll('.card.reveal').forEach(c => c.classList.add('visible'));
  }

  // ── 3D tilt effect on cards ────────────────────────────────────
  document.querySelectorAll('.tilt-card').forEach(card => {
    card.addEventListener('mousemove', e => {
      const rect   = card.getBoundingClientRect();
      const cx     = rect.left + rect.width  / 2;
      const cy     = rect.top  + rect.height / 2;
      const dx     = (e.clientX - cx) / (rect.width  / 2);
      const dy     = (e.clientY - cy) / (rect.height / 2);
      card.style.transform = `translateY(-5px) rotateY(${dx * 4}deg) rotateX(${-dy * 4}deg)`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
      card.style.transition = 'transform .4s ease';
    });
    card.addEventListener('mouseenter', () => {
      card.style.transition = 'transform .08s ease';
    });
  });

  // ── Quick View modal ───────────────────────────────────────────
  const qvBackdrop = document.getElementById('qvBackdrop');
  const qvModal    = document.getElementById('qvModal');
  const qvClose    = document.getElementById('qvClose');

  function openQuickView(card) {
    if (!qvModal || !qvBackdrop) return;
    const id    = card.dataset.id;
    const name  = card.dataset.name  || '';
    const price = card.dataset.price || '';
    const desc  = card.dataset.desc  || '';
    const img   = card.dataset.img   || '';
    const type  = card.dataset.type  || '';
    const size  = card.dataset.size  || '';

    document.getElementById('qvName').textContent  = name;
    document.getElementById('qvPrice').textContent = '$' + price;
    document.getElementById('qvDesc').textContent  = desc || 'No description available.';
    document.getElementById('qvType').textContent  = type;
    document.getElementById('qvSize').textContent  = size;

    const qvImg   = document.getElementById('qvImg');
    const qvImgPh = document.getElementById('qvImgPh');
    if (img) {
      qvImg.src = img;
      qvImg.classList.remove('hidden');
      qvImgPh.classList.add('hidden');
    } else {
      qvImg.classList.add('hidden');
      qvImgPh.classList.remove('hidden');
    }

    const qvViewBtn = document.getElementById('qvViewBtn');
    if (qvViewBtn && id) qvViewBtn.href = '/product/' + id + '/';

    qvBackdrop.classList.remove('hidden');
    qvModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }

  function closeQuickView() {
    if (!qvModal || !qvBackdrop) return;
    qvBackdrop.classList.add('hidden');
    qvModal.classList.add('hidden');
    document.body.style.overflow = '';
  }

  document.addEventListener('click', e => {
    const btn = e.target.closest('.quick-view-btn');
    if (btn) {
      const card = btn.closest('.card');
      if (card) openQuickView(card);
    }
  });

  if (qvClose)    qvClose.addEventListener('click', closeQuickView);
  if (qvBackdrop) qvBackdrop.addEventListener('click', closeQuickView);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeQuickView(); });

  // ── Wishlist (server-side forms used; this syncs visual state) ─
  function syncWishlistButtons() {
    // Actual wishlist state comes from server via .wishlisted class
    // This just ensures title attributes are correct
    document.querySelectorAll('.wishlist-btn').forEach(btn => {
      const wishlisted = btn.classList.contains('wishlisted');
      btn.title = wishlisted ? 'Remove from wishlist' : 'Add to wishlist';
      btn.setAttribute('aria-label', btn.title);
    });
  }
  syncWishlistButtons();

  // ── Add-to-cart button feedback ────────────────────────────────
  document.addEventListener('click', e => {
    const btn = e.target.closest('.btn-cart, .overlay-btn, .feat-cart-btn');
    if (!btn) return;
    const form = btn.closest('form');
    if (!form) return;
    const orig = btn.innerHTML;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg> Added!';
    btn.style.background = '#16a34a';
    btn.style.color      = '#fff';
    btn.style.borderColor = '#16a34a';
    setTimeout(() => {
      btn.innerHTML     = orig;
      btn.style.background  = '';
      btn.style.color       = '';
      btn.style.borderColor = '';
    }, 1500);
  });

  // ── Scroll-to-top button ───────────────────────────────────────
  const scrollBtn = document.getElementById('scrollTop');
  if (scrollBtn) {
    window.addEventListener('scroll', () => {
      scrollBtn.classList.toggle('visible', window.scrollY > 400);
    }, { passive: true });
    scrollBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  }

  // ── Newsletter handler ─────────────────────────────────────────
  window.handleNewsletter = function (e) {
    e.preventDefault();
    const input  = e.target.querySelector('input[type="email"]');
    const button = e.target.querySelector('button');
    button.textContent = '✓ Subscribed!';
    button.style.background = '#16a34a';
    input.value = '';
    setTimeout(() => {
      button.textContent = 'Subscribe';
      button.style.background = '';
    }, 3000);
  };

  // ── Toast notification ─────────────────────────────────────────
  function showToast(msg, type) {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.cssText = 'position:fixed;bottom:80px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.textContent = msg;
    const bg = type === 'error' ? '#ef4444' : '#1e1b4b';
    toast.style.cssText = [
      'background:' + bg, 'color:#fff', 'padding:12px 20px',
      'border-radius:10px', 'font-size:.85rem', 'font-weight:600',
      'box-shadow:0 6px 24px rgba(0,0,0,.25)',
      'animation:slideInToast .25s ease',
      'max-width:260px'
    ].join(';');
    container.appendChild(toast);
    if (!document.getElementById('toastKf')) {
      const style = document.createElement('style');
      style.id = 'toastKf';
      style.textContent = '@keyframes slideInToast{from{opacity:0;transform:translateX(30px)}to{opacity:1;transform:translateX(0)}}';
      document.head.appendChild(style);
    }
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity .3s';
      setTimeout(() => toast.remove(), 300);
    }, 2200);
  }

  // Expose for external use
  window.showToast = showToast;

})();
