/**
 * ui.js — Comportements d'interface de Kendevis
 *
 *  - Bascule de thème clair / sombre (persistée dans localStorage)
 *  - Taille de police A- / A / A+ (persistée)
 *  - Onde (ripple) au clic sur les boutons
 *  - Compteurs animés pour les montants du tableau de bord
 *  - Historique des dépenses : repli à cinq lignes et recherche
 *  - Bouton "retour en haut"
 *  - Décalage des barres collantes (barre d'onglets sous la barre de navigation)
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
    // 5. Historique des dépenses : repli et recherche
    // ---------------------------------------------------------------------
    /* Une ligne du tableau peut être masquée pour deux raisons
       indépendantes : elle est repliée (au-delà des cinq premières lignes),
       ou elle ne correspond pas à la recherche. Les deux états sont notés à
       part (`data-replie`, `data-filtre`) et l'affichage est recalculé à
       chaque changement, sinon le compteur annoncerait des résultats que
       l'utilisateur ne voit pas.

       Une recherche déplie le tableau si elle trouve quelque chose dans la
       partie repliée : sinon taper le nom d'une dépense ancienne afficherait
       « aucun résultat » alors qu'elle est précisément sous la table. */
    function initHistorique() {
        var table = document.getElementById('depenses-table');
        var input = document.getElementById('depense-search');
        var bouton = document.getElementById('btn-voir-plus');
        if (!table) return;

        var counter = document.getElementById('depenses-count');
        var emptyState = document.getElementById('search-empty');
        var lignes = Array.prototype.slice.call(table.querySelectorAll('tbody tr'))
            .filter(function (ligne) { return ligne.id !== 'search-empty'; });
        var repliees = lignes.filter(function (ligne) {
            return ligne.dataset.replie === '1';
        });

        function depliees() {
            return repliees.some(function (ligne) {
                return ligne.dataset.replie !== '1';
            });
        }

        function rafraichirBouton() {
            if (!bouton || !repliees.length) return;
            var ouvert = depliees();
            bouton.innerHTML = '';
            var icone = document.createElement('i');
            icone.className = 'bi ' + (ouvert ? 'bi-chevron-up' : 'bi-chevron-down');
            icone.setAttribute('aria-hidden', 'true');
            bouton.appendChild(icone);
            bouton.appendChild(document.createTextNode(
                ' ' + (ouvert ? 'Voir moins' : 'Voir plus (' + repliees.length + ')')
            ));
            bouton.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
        }

        function appliquer() {
            var visibles = 0;
            lignes.forEach(function (ligne) {
                var cachee = ligne.dataset.replie === '1' || ligne.dataset.filtre === '1';
                ligne.hidden = cachee;
                if (!cachee) visibles++;
            });

            if (counter) {
                counter.textContent = visibles + (visibles > 1 ? ' dépenses' : ' dépense');
            }
            if (emptyState) {
                emptyState.classList.toggle('d-none', visibles !== 0 || lignes.length === 0);
            }
        }

        function rechercher() {
            var query = input ? input.value.trim().toLowerCase() : '';
            var trouveeReplie = false;

            lignes.forEach(function (ligne) {
                var match = query === '' ||
                    ligne.textContent.toLowerCase().indexOf(query) !== -1;
                ligne.dataset.filtre = match ? '0' : '1';
                if (match && ligne.dataset.replie === '1') trouveeReplie = true;
            });

            if (trouveeReplie) {
                repliees.forEach(function (ligne) { ligne.dataset.replie = '0'; });
                rafraichirBouton();
            }
            appliquer();
        }

        if (input) input.addEventListener('input', rechercher);

        if (bouton && repliees.length) {
            bouton.addEventListener('click', function () {
                var replier = depliees();
                repliees.forEach(function (ligne) {
                    ligne.dataset.replie = replier ? '1' : '0';
                });
                rafraichirBouton();
                appliquer();
            });
        }

        rafraichirBouton();
        appliquer();
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
    // 7. Décalage des barres collantes
    // ---------------------------------------------------------------------
    /* La barre d'onglets est collante : pour qu'elle s'arrête sous la barre de
       navigation au lieu de la recouvrir, elle a besoin de connaître la
       hauteur de celle-ci. Cette hauteur n'est pas une constante CSS — elle
       dépend de la largeur de l'écran (barre repliée ou déployée), de la
       taille de police choisie et du menu mobile ouvert ou fermé. On la
       mesure donc, et on la publie dans `--navbar-hauteur`. */
    function initStickyOffset() {
        var navbar = document.querySelector('.navbar');
        if (!navbar) return;

        var dernier = -1;

        function mesurer() {
            // getBoundingClientRect reflects la hauteur réelle, margins
            // comprises, et suit automatiquement le redimensionnement.
            var hauteur = Math.round(navbar.getBoundingClientRect().height);
            if (!hauteur || hauteur === dernier) return;
            dernier = hauteur;
            document.documentElement.style.setProperty('--navbar-hauteur', hauteur + 'px');
        }

        mesurer();

        window.addEventListener('resize', mesurer, { passive: true });
        window.addEventListener('load', mesurer);

        // Ouverture / fermeture du menu mobile : Bootstrap émet ces
        // évènements sur le conteneur repliable.
        var collapse = document.querySelector('.navbar-collapse');
        if (collapse) {
            collapse.addEventListener('shown.bs.collapse', mesurer);
            collapse.addEventListener('hidden.bs.collapse', mesurer);
        }

        // La taille de police change la hauteur de la barre : on
        // réévalue juste après le clic sur A- / A / A+.
        document.querySelectorAll('[data-font-scale]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                setTimeout(mesurer, 0);
            });
        });

        // Sécurité : si la mesure est impossible (police pas encore
        // chargée, script bloqué…), on réévalue un peu plus tard.
        setTimeout(mesurer, 300);
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
        initHistorique();
        initBackToTop();
        initStickyOffset();
        console.log('[Kendevis] Interface prête.');
    }

    window.KendevisUI = { initTheme: initTheme, initFontScale: initFontScale, initCounters: initCounters };
    onReady(init);
})();
