/**
 * MCP Browser — Website Client Logic
 * Handles theme toggling, terminal snippet switching, copy actions,
 * and the accessible modal lightbox gallery.
 */

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initCardThemeToggles();
  initTerminalTabs();
  initCopyButtons();
  initLightbox();
});

/* --------------------------------------------------------------------------
   Theme Management (Light / Dark Mode)
   -------------------------------------------------------------------------- */
function setCardTheme(card, theme) {
  card.setAttribute('data-current-theme', theme);
  const titleEl = card.querySelector('.gallery-card-title');
  const baseTitle = titleEl ? titleEl.textContent.trim() : 'Screenshot';
  const themeLabel = theme === 'dark' ? 'Dark Mode' : 'Light Mode';
  card.setAttribute('aria-label', `Enlarge ${baseTitle} (${themeLabel})`);

  // Update tabs in segmented toggle
  const tabs = card.querySelectorAll('.card-theme-toggle [role="tab"]');
  tabs.forEach((tab) => {
    const isTarget = tab.getAttribute('data-theme') === theme;
    tab.classList.toggle('active', isTarget);
    tab.setAttribute('aria-selected', isTarget ? 'true' : 'false');
    tab.setAttribute('tabindex', isTarget ? '0' : '-1');
  });

  // Update image visibility with smooth cross-fade
  const lightImg = card.querySelector('.gallery-img-light');
  const darkImg = card.querySelector('.gallery-img-dark');
  if (lightImg) {
    lightImg.classList.toggle('active', theme === 'light');
  }
  if (darkImg) {
    darkImg.classList.toggle('active', theme === 'dark');
  }
}

function initTheme() {
  const toggleBtn = document.getElementById('theme-toggle');
  const heroImg = document.getElementById('hero-img');
  const storedTheme = localStorage.getItem('mcp-theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    if (toggleBtn) {
      toggleBtn.innerHTML = theme === 'dark' ? '☀️ <span class="sr-only">Switch to Light Theme</span>' : '🌙 <span class="sr-only">Switch to Dark Theme</span>';
      toggleBtn.setAttribute('aria-label', theme === 'dark' ? 'Switch to Light Theme' : 'Switch to Dark Theme');
    }
    if (heroImg) {
      heroImg.src = theme === 'dark' ? 'images/screenshots/server-list-dark.png' : 'images/screenshots/server-list.png';
    }
    // Synchronize gallery cards with global theme
    document.querySelectorAll('.gallery-card').forEach((card) => {
      if (card.querySelector('.card-theme-toggle')) {
        setCardTheme(card, theme);
      }
    });
  }

  // Initialize theme
  if (storedTheme) {
    applyTheme(storedTheme);
  } else {
    applyTheme(prefersDark.matches ? 'dark' : 'light');
  }

  // Listen to toggle clicks
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'light';
      const nextTheme = current === 'dark' ? 'light' : 'dark';
      localStorage.setItem('mcp-theme', nextTheme);
      applyTheme(nextTheme);
    });
  }

  // Listen for OS preference change
  prefersDark.addEventListener('change', (e) => {
    if (!localStorage.getItem('mcp-theme')) {
      applyTheme(e.matches ? 'dark' : 'light');
    }
  });
}

/* --------------------------------------------------------------------------
   Card-Level Theme Toggles
   -------------------------------------------------------------------------- */
function initCardThemeToggles() {
  const cards = document.querySelectorAll('.gallery-card');

  cards.forEach((card) => {
    const toggle = card.querySelector('.card-theme-toggle');
    if (!toggle) return;

    const tabs = Array.from(toggle.querySelectorAll('[role="tab"]'));

    tabs.forEach((tab) => {
      // Click toggle button
      tab.addEventListener('click', (e) => {
        e.stopPropagation();
        const theme = tab.getAttribute('data-theme');
        if (theme) {
          setCardTheme(card, theme);
          tab.focus();
        }
      });

      // Keyboard arrow navigation for tabs
      tab.addEventListener('keydown', (e) => {
        let targetTab = null;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          e.preventDefault();
          e.stopPropagation();
          const nextIndex = (tabs.indexOf(tab) + 1) % tabs.length;
          targetTab = tabs[nextIndex];
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          e.preventDefault();
          e.stopPropagation();
          const prevIndex = (tabs.indexOf(tab) - 1 + tabs.length) % tabs.length;
          targetTab = tabs[prevIndex];
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.stopPropagation();
          targetTab = tab;
        }

        if (targetTab) {
          const theme = targetTab.getAttribute('data-theme');
          if (theme) {
            setCardTheme(card, theme);
            targetTab.focus();
          }
        }
      });
    });
  });
}

/* --------------------------------------------------------------------------
   Terminal Snippets & Tabs
   -------------------------------------------------------------------------- */
const SNIPPETS = {
  uv: 'uv tool install mcp-browser && mcp-browser',
  pip: 'pip install mcp-browser && mcp-browser',
  source: 'git clone https://github.com/raisen/mcp-browser && cd mcp-browser && uv sync --all-packages && uv run mcp-browser'
};

function initTerminalTabs() {
  const tabs = Array.from(document.querySelectorAll('.terminal-tab'));
  const codeEl = document.getElementById('terminal-command');
  const copyBtn = document.getElementById('terminal-copy');

  function selectTab(tab) {
    const target = tab.getAttribute('data-target');
    if (!target || !SNIPPETS[target]) return;

    tabs.forEach((t) => {
      t.classList.remove('active');
      t.setAttribute('aria-selected', 'false');
      t.setAttribute('tabindex', '-1');
    });

    tab.classList.add('active');
    tab.setAttribute('aria-selected', 'true');
    tab.setAttribute('tabindex', '0');
    tab.focus();

    if (codeEl) {
      codeEl.textContent = SNIPPETS[target];
    }
    if (copyBtn) {
      copyBtn.setAttribute('data-copy-text', SNIPPETS[target]);
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));

    tab.addEventListener('keydown', (e) => {
      let nextIndex = null;
      if (e.key === 'ArrowRight') {
        nextIndex = (index + 1) % tabs.length;
      } else if (e.key === 'ArrowLeft') {
        nextIndex = (index - 1 + tabs.length) % tabs.length;
      } else if (e.key === 'Home') {
        nextIndex = 0;
      } else if (e.key === 'End') {
        nextIndex = tabs.length - 1;
      }

      if (nextIndex !== null) {
        e.preventDefault();
        selectTab(tabs[nextIndex]);
      }
    });
  });
}

/* --------------------------------------------------------------------------
   1-Click Copy Buttons
   -------------------------------------------------------------------------- */
function initCopyButtons() {
  const copyButtons = document.querySelectorAll('.copy-btn, [data-copy-text]');

  copyButtons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      const textToCopy = btn.getAttribute('data-copy-text') || (document.getElementById('terminal-command')?.textContent.trim());
      if (!textToCopy) return;

      try {
        await navigator.clipboard.writeText(textToCopy);
        triggerCopyFeedback(btn);
      } catch (err) {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = textToCopy;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
          document.execCommand('copy');
          triggerCopyFeedback(btn);
        } catch {
          // Quietly ignore
        }
        document.body.removeChild(textarea);
      }
    });
  });
}

function triggerCopyFeedback(button) {
  const originalHtml = button.innerHTML;
  button.classList.add('copied');
  button.innerHTML = '✓ Copied!';

  setTimeout(() => {
    button.classList.remove('copied');
    button.innerHTML = originalHtml;
  }, 2000);
}

/* --------------------------------------------------------------------------
   Accessible Lightbox Gallery
   -------------------------------------------------------------------------- */
const GALLERY_ITEMS = [
  {
    src: 'images/screenshots/server-list.png',
    title: 'Server Discovery Dashboard (Light Theme)',
    desc: 'Lists all MCP servers found on the machine across multiple client configurations.'
  },
  {
    src: 'images/screenshots/server-list-dark.png',
    title: 'Server Discovery Dashboard (Dark Theme)',
    desc: 'Clean dark mode overview with real-time health indicator and transport badges.'
  },
  {
    src: 'images/screenshots/server-detail.png',
    title: 'Interactive Tool Runner & Playground (Light Theme)',
    desc: 'Dynamically generated form from JSON Schema allowing direct browser tool execution.'
  },
  {
    src: 'images/screenshots/server-detail-dark.png',
    title: 'Interactive Tool Runner & Playground (Dark Theme)',
    desc: 'Dark theme interactive tool tester showing real-time execution results.'
  },
  {
    src: 'images/screenshots/add-server.png',
    title: 'Multi-Client Configuration',
    desc: 'Configure once and write to multiple clients simultaneously with atomic safety.'
  }
];

function initLightbox() {
  const modal = document.getElementById('lightbox-modal');
  const img = document.getElementById('lightbox-img');
  const caption = document.getElementById('lightbox-caption');
  const counter = document.getElementById('lightbox-counter');
  const closeBtn = document.getElementById('lightbox-close');
  const prevBtn = document.getElementById('lightbox-prev');
  const nextBtn = document.getElementById('lightbox-next');

  if (!modal || !img) return;

  let currentIndex = 0;
  let lastActiveElement = null;

  function showImage(index) {
    if (index < 0) index = GALLERY_ITEMS.length - 1;
    if (index >= GALLERY_ITEMS.length) index = 0;
    currentIndex = index;

    const item = GALLERY_ITEMS[currentIndex];
    img.src = item.src;
    img.alt = item.title;
    if (caption) caption.textContent = item.title;
    if (counter) counter.textContent = `${currentIndex + 1} of ${GALLERY_ITEMS.length}`;
  }

  function openModal(index) {
    lastActiveElement = document.activeElement;
    showImage(index);
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    closeBtn?.focus();
  }

  function closeModal() {
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (lastActiveElement && typeof lastActiveElement.focus === 'function') {
      lastActiveElement.focus();
    }
  }

  // Trigger from hero preview
  const heroPreview = document.getElementById('hero-preview');
  if (heroPreview) {
    const handleHeroTrigger = () => {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      openModal(isDark ? 1 : 0);
    };
    heroPreview.addEventListener('click', handleHeroTrigger);
    heroPreview.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleHeroTrigger();
      }
    });
  }

  // Trigger from gallery cards
  const galleryCards = document.querySelectorAll('.gallery-card');
  galleryCards.forEach((card) => {
    function openCardModal(e) {
      if (e.target.closest('.card-theme-toggle')) return;
      const currentTheme = card.getAttribute('data-current-theme') || 'light';
      const indexAttr = currentTheme === 'dark' ? card.getAttribute('data-dark-index') : card.getAttribute('data-light-index');
      const index = parseInt(indexAttr ?? card.getAttribute('data-index') ?? '0', 10);
      openModal(index);
    }

    card.addEventListener('click', openCardModal);
    card.addEventListener('keydown', (e) => {
      if (e.target.closest('.card-theme-toggle')) return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openCardModal(e);
      }
    });
  });

  // Controls
  closeBtn?.addEventListener('click', closeModal);
  prevBtn?.addEventListener('click', () => showImage(currentIndex - 1));
  nextBtn?.addEventListener('click', () => showImage(currentIndex + 1));

  // Click outside image to close
  modal.addEventListener('click', (e) => {
    if (e.target === modal || e.target.classList.contains('lightbox-content')) {
      closeModal();
    }
  });

  // Keyboard navigation & accessibility focus trap
  const focusableSelectors = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

  document.addEventListener('keydown', (e) => {
    if (!modal.classList.contains('active')) return;

    if (e.key === 'Escape') {
      closeModal();
    } else if (e.key === 'ArrowLeft') {
      showImage(currentIndex - 1);
    } else if (e.key === 'ArrowRight') {
      showImage(currentIndex + 1);
    } else if (e.key === 'Tab') {
      const focusableElements = Array.from(modal.querySelectorAll(focusableSelectors));
      if (!focusableElements.length) return;

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    }
  });
}
