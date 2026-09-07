/**
 * Yojana Sentinel — Frontend JS
 * Micro-interactions, animations, counters, and UX polish.
 * Vanilla JS — no framework dependency.
 */

'use strict';

/* ── Utility ─────────────────────────────────────────────────── */
const qs  = (sel, ctx = document) => ctx.querySelector(sel);
const qsa = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/* ── Animated counter ────────────────────────────────────────── */
function animateCounter(el) {
  const target = parseInt(el.dataset.target || el.textContent, 10);
  if (isNaN(target)) return;
  const duration = 900;
  const start    = performance.now();
  el.textContent = '0';

  function step(now) {
    const elapsed  = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const ease     = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
    el.textContent = Math.round(ease * target).toLocaleString();
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function initCounters() {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateCounter(entry.target);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.3 });

  qsa('.stat-value[data-target], .counter').forEach(el => observer.observe(el));
}

/* ── Match score rings ───────────────────────────────────────── */
function initScoreRings() {
  const CIRCUMFERENCE = 220; // matches stroke-dasharray in CSS

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const ring = entry.target;
      const fill = ring.querySelector('.fill');
      if (!fill) return;

      const score   = parseFloat(ring.dataset.score || 0);
      const offset  = CIRCUMFERENCE - (score / 100) * CIRCUMFERENCE;
      fill.style.strokeDashoffset = offset;
      observer.unobserve(ring);
    });
  }, { threshold: 0.2 });

  qsa('.score-ring[data-score]').forEach(ring => observer.observe(ring));
}

/* ── Score bar fills ─────────────────────────────────────────── */
function initScoreBars() {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const bar = entry.target;
      const score = parseFloat(bar.dataset.score || 0);
      bar.style.width = score + '%';
      observer.unobserve(bar);
    });
  }, { threshold: 0.3 });

  qsa('.score-bar-fill[data-score]').forEach(el => observer.observe(el));
}

/* ── Card stagger entrance ───────────────────────────────────── */
function initCardStagger() {
  const observer = new IntersectionObserver(entries => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        entry.target.style.animationDelay = (i * 0.06) + 's';
        entry.target.classList.add('anim-slide');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

  qsa('.match-item, .event-item, .audit-item').forEach(el => observer.observe(el));
}

/* ── Subtle card tilt on hover ───────────────────────────────── */
function initCardTilt() {
  qsa('.draft-card, .stat-card').forEach(card => {
    card.addEventListener('mousemove', e => {
      const rect = card.getBoundingClientRect();
      const x    = (e.clientX - rect.left) / rect.width  - 0.5;
      const y    = (e.clientY - rect.top)  / rect.height - 0.5;
      card.style.transform = `translateY(-2px) rotateY(${x * 3}deg) rotateX(${-y * 3}deg)`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
    });
  });
}

/* ── Flash banner auto-dismiss ───────────────────────────────── */
function initFlashDismiss() {
  qsa('.flash-banner').forEach(banner => {
    const close = banner.querySelector('.flash-close');
    if (close) {
      close.addEventListener('click', () => {
        banner.style.opacity = '0';
        banner.style.transform = 'translateY(-8px)';
        banner.style.transition = 'all 0.3s ease';
        setTimeout(() => banner.remove(), 300);
      });
    }
    // Auto-dismiss after 6 seconds
    setTimeout(() => {
      if (banner.isConnected) {
        banner.style.opacity = '0';
        banner.style.transition = 'opacity 0.5s ease';
        setTimeout(() => banner.remove(), 500);
      }
    }, 6000);
  });
}

/* ── Approval confirmation modal ─────────────────────────────── */
function initApprovalModal() {
  const overlay = qs('#approve-modal');
  if (!overlay) return;

  let pendingForm = null;

  qsa('.approve-trigger').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      pendingForm = btn.closest('form');
      overlay.classList.add('open');
    });
  });

  const confirmBtn = qs('#approve-confirm', overlay);
  const cancelBtn  = qs('#approve-cancel',  overlay);

  if (confirmBtn) {
    confirmBtn.addEventListener('click', () => {
      if (pendingForm) {
        overlay.classList.remove('open');
        pendingForm.submit();
      }
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      overlay.classList.remove('open');
      pendingForm = null;
    });
  }

  overlay.addEventListener('click', e => {
    if (e.target === overlay) {
      overlay.classList.remove('open');
      pendingForm = null;
    }
  });
}

/* ── Filter tabs (matching page) ─────────────────────────────── */
function initFilterTabs() {
  qsa('.filter-tab[data-filter]').forEach(tab => {
    tab.addEventListener('click', () => {
      // Update active tab
      qsa('.filter-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const filter = tab.dataset.filter;

      qsa('.match-item[data-status]').forEach(item => {
        if (filter === 'all' || item.dataset.status === filter) {
          item.style.display = '';
          item.style.animation = 'cardEntrance 0.25s ease both';
        } else {
          item.style.display = 'none';
        }
      });
    });
  });
}

/* ── Copy draft text to clipboard ────────────────────────────── */
function initCopyButtons() {
  qsa('.copy-draft-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = qs(btn.dataset.target);
      if (!target) return;
      navigator.clipboard.writeText(target.textContent).then(() => {
        const original = btn.textContent;
        btn.textContent = '✓ Copied!';
        btn.style.color = '#6ee7b7';
        setTimeout(() => {
          btn.textContent = original;
          btn.style.color = '';
        }, 2000);
      });
    });
  });
}

/* ── Sidebar active link highlight ──────────────────────────────*/
function initSidebarHighlight() {
  const current = window.location.pathname;
  qsa('.nav-link').forEach(link => {
    const href = link.getAttribute('href');
    if (href === current || (href !== '/' && current.startsWith(href))) {
      link.classList.add('active');
    }
  });
}

/* ── Reject character counter ────────────────────────────────── */
function initCharCounter() {
  qsa('textarea[data-maxlength]').forEach(ta => {
    const max     = parseInt(ta.dataset.maxlength, 10);
    const counter = document.createElement('div');
    counter.className = 'text-muted';
    counter.style.cssText = 'font-size:0.72rem;text-align:right;margin-top:4px;';
    ta.parentNode.appendChild(counter);

    function update() {
      const remaining = max - ta.value.length;
      counter.textContent = `${ta.value.length} / ${max}`;
      counter.style.color = remaining < 50 ? 'var(--amber)' : '';
    }
    ta.addEventListener('input', update);
    update();
  });
}

/* ── Live monitoring heartbeat (visual only) ─────────────────── */
function initMonitoringHeartbeat() {
  const dots = qsa('.pulse-dot');
  if (!dots.length) return;
  // Dots already animate via CSS; just ensure they exist.
}

/* ── Form UX: prevent double-submit ─────────────────────────── */
function initFormGuards() {
  qsa('form[data-once]').forEach(form => {
    form.addEventListener('submit', () => {
      qsa('button[type="submit"]', form).forEach(btn => {
        btn.disabled = true;
        const orig = btn.innerHTML;
        btn.innerHTML = '⏳ Processing...';
        setTimeout(() => {
          btn.disabled = false;
          btn.innerHTML = orig;
        }, 8000);
      });
    });
  });
}

/* ── Page transition fade ────────────────────────────────────── */
function initPageTransition() {
  document.body.style.opacity = '0';
  document.body.style.transition = 'opacity 0.2s ease';
  requestAnimationFrame(() => {
    document.body.style.opacity = '1';
  });

  qsa('a[href]:not([target]):not([data-no-transition])').forEach(link => {
    const href = link.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('http') || href.startsWith('mailto')) return;
    link.addEventListener('click', e => {
      e.preventDefault();
      document.body.style.opacity = '0';
      setTimeout(() => window.location.assign(href), 180);
    });
  });
}

/* ── Init all ────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initPageTransition();
  initCounters();
  initScoreRings();
  initScoreBars();
  initCardStagger();
  initCardTilt();
  initFlashDismiss();
  initApprovalModal();
  initFilterTabs();
  initCopyButtons();
  initSidebarHighlight();
  initCharCounter();
  initMonitoringHeartbeat();
  initFormGuards();
});
