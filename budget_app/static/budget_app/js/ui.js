/**
 * ui.js — Comportements d'interface de Kendevis
 *
 *  - Bascule de thème clair / sombre (persistée dans localStorage)
 *  - Taille de police A- / A / A+ (persistée)
 *  - Onde (ripple) au clic sur les boutons
 *  - Compteurs animés pour les montants du tableau de bord
 *  - Recherche instantanée dans le tableau des dépenses
 *  - Bouton "retour en haut"
 */
(function () {
    'use strict';

    var STORAGE_THEME = 'kd-theme';
    var STORAGE_FONT = 'kd-font-scale';

    // ---------------------------------------------------------------------
    // Utilitaires
    // ---------------------------------------------------------------------
    function readStorage(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    function writeStorage(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* mode privé */ }
    }

    function onReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback);
        } else {
            callback();
        }
    }

    // ---------------------------------------------------------------------
    // 1. Thème clair / sombre
    // ---------------------------------------------------------------------
    function initTheme() {
        var toggle = document.getElementById('theme-toggle');
        var icon = document.getElementById('theme-icon');
        var root = document.documentElement;

        function paint() {
            if (!icon) return;
            var dark = root.getAttribute('data-theme') === 'dark';
            icon.className = dark ? 'bi bi-sun' : 'bi bi-moon-stars';
            if (toggle) {
                toggle.title = dark ? 'Passer en thème clair' : 'Passer en thème sombre';
            }
        }

        paint();

        if (toggle) {
            toggle.addEventListener('click', function () {
                var dark = root.getAttribute('data-theme') === 'dark';
                var next = dark ? 'light' : 'dark';
                root.setAttribute('data-theme', next);
                writeStorage(STORAGE_THEME, next);
                paint();

                // Micro-animation du bouton
                toggle.animate(
                    [{ transform: 'rotate(0) scale(1)' },
                     { transform: 'rotate(180deg) scale(1.15)' },
                     { transform: 'rotate(360deg) scale(1)' }],
                    { duration: 420, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' }
                );
            });
        }
    }

    // ---------------------------------------------------------------------
    // 2. Taille de police
    // ---------------------------------------------------------------------
    function initFontScale() {
        var buttons = document.querySelectorAll('[data-font-scale]');
        if (!buttons.length) return;

        function apply(scale, save) {
            document.documentElement.style.setProperty('--font-scale', String(scale));
            buttons.forEach(function (btn) {
                btn.classList.toggle('is-active', parseFloat(btn.dataset.fontScale) === scale);
            });
            if (save) writeStorage(STORAGE_FONT, String(scale));
        }

        buttons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                apply(parseFloat(btn.dataset.fontScale), true);
            });
        });

        var stored = parseFloat(readStorage(STORAGE_FONT));
        if (!isNaN(stored)) { apply(stored, false); }
    }

    // ---------------------------------------------------------------------
    // 3. Onde (ripple) au clic
    // ---------------------------------------------------------------------
    function initRipple() {
        document.addEventListener('click', function (event) {
            var target = event.target.closest('.btn, .icon-btn, .dropdown-item');
            if (!target || target.disabled) return;

            var rect = target.getBoundingClientRect();
            var size = Math.max(rect.width, rect.height);
            var span = document.createElement('span');
            span.className = 'ripple';
            span.style.width = span.style.height = size + 'px';
            span.style.left = (event.clientX - rect.left - size / 2) + 'px';
            span.style.top = (event.clientY - rect.top - size / 2) + 'px';

            target.appendChild(span);
            setTimeout(function () { span.remove(); }, 650);
        });
    }

    // ---------------------------------------------------------------------
    // 4. Compteurs animés (montants du tableau de bord)
    // ---------------------------------------------------------------------
    function animateCounter(element) {
        var target = parseFloat(String(element.dataset.countTo || '0').replace(/\s/g, '').replace(',', '.'));
        if (isNaN(target)) return;

        var decimals = parseInt(element.dataset.countDecimals || '0', 10);
        var suffix = element.dataset.countSuffix || '';
        var duration = 900;
        var start = null;

        function frame(now) {
            if (start === null) start = now;
            var progress = Math.min((now - start) / duration, 1);
            // Décélération : ease-out
            var eased = 1 - Math.pow(1 - progress, 3);
            var value = target * eased;
            element.textContent = value.toLocaleString('fr-FR', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            }) + suffix;
            if (progress < 1) requestAnimationFrame(frame);
        }

        requestAnimationFrame(frame);
    }

    function initCounters() {
        var counters = document.querySelectorAll('[data-count-to]');
        if (!counters.length) return;

        var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduced) {
            counters.forEach(animateCounter); // rendu final immédiat
            return;
        }

        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    animateCounter(entry.target);
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.4 });

        counters.forEach(function (element) { observer.observe(element); });
    }

    // ---------------------------------------------------------------------
    // 5. Recherche dans le tableau des dépenses
    // ---------------------------------------------------------------------
    function initTableSearch() {
        var input = document.getElementById('depense-search');
        var table = document.getElementById('depenses-table');
        if (!input || !table) return;

        var counter = document.getElementById('depenses-count');
        var rows = Array.prototype.slice.call(table.querySelectorAll('tbody tr'));
        var emptyState = document.getElementById('search-empty');

        input.addEventListener('input', function () {
            var query = this.value.trim().toLowerCase();
            var visible = 0;

            rows.forEach(function (row) {
                var match = row.textContent.toLowerCase().indexOf(query) !== -1;
                row.style.display = match ? '' : 'none';
                if (match) visible++;
            });

            if (counter) {
                counter.textContent = visible + (visible > 1 ? ' dépenses' : ' dépense');
            }
            if (emptyState) {
                emptyState.classList.toggle('d-none', visible !== 0 || rows.length === 0);
            }
        });
    }

    // ---------------------------------------------------------------------
    // 6. Bouton retour en haut
    // ---------------------------------------------------------------------
    function initBackToTop() {
        var button = document.getElementById('back-to-top');
        if (!button) return;

        function update() {
            button.classList.toggle('is-visible', window.scrollY > 400);
        }

        window.addEventListener('scroll', update, { passive: true });
        update();

        button.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // ---------------------------------------------------------------------
    // Initialisation
    // ---------------------------------------------------------------------
    function init() {
        console.log('[Kendevis] Initialisation de l\'interface...');
        initTheme();
        initFontScale();
        initRipple();
        initCounters();
        initTableSearch();
        initBackToTop();
        console.log('[Kendevis] Interface prête.');
    }

    window.KendevisUI = { initTheme: initTheme, initFontScale: initFontScale, initCounters: initCounters };
    onReady(init);
})();
