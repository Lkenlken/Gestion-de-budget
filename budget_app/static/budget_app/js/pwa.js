/**
 * Installation de l'application sur l'écran d'accueil (PWA).
 *
 * Chrome et Edge émettent l'événement `beforeinstallprompt` quand toutes
 * les conditions sont réunies (manifeste valide, service worker, HTTPS).
 * Cet événement n'est pas standard : Firefox et Safari ne l'émettent pas,
 * d'où le repli sur un message expliquant la procédure manuelle.
 */
(function () {
    'use strict';

    var installer = null;              // événement capturé le temps de l'afficher
    var boutonExistant = null;

    function estInstallable() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    }

    // ------------------------------------------------------------------
    // Bouton « Installer l'application »
    // ------------------------------------------------------------------
    function creerBouton() {
        if (boutonExistant || estInstallable()) return;

        var hote = document.querySelector('[data-pwa-hote]');
        if (!hote) return;

        var bouton = document.createElement('button');
        bouton.type = 'button';
        bouton.className = 'pwa-install-btn';
        bouton.innerHTML = '<i class="bi bi-download"></i><span>Installer</span>';
        bouton.title = "Ajouter Kendevis à l'écran d'accueil";

        bouton.addEventListener('click', function () {
            if (installer) {
                installer.prompt();
                installer.userChoice.then(function (choix) {
                    if (choix.outcome === 'accepted') {
                        bouton.remove();
                        boutonExistant = null;
                    }
                    installer = null;
                });
                return;
            }
            // Aucun événement disponible : on explique la procédure manuelle.
            window.alert(
                "Pour installer Kendevis :\n\n"
                + "• Android / Chrome : menu ⋮ puis « Installer l'application »\n"
                + "• Ordinateur (Chrome, Edge) : icône d'installation dans la barre\n"
                + "  d'adresse, à droite\n"
                + "• iPhone / Safari : bouton Partager puis « Sur l'écran d'accueil »"
            );
        });

        hote.appendChild(bouton);
        boutonExistant = bouton;
    }

    window.addEventListener('beforeinstallprompt', function (evenement) {
        evenement.preventDefault();
        installer = evenement;
        creerBouton();
    });

    window.addEventListener('appinstalled', function () {
        if (boutonExistant) boutonExistant.remove();
        boutonExistant = null;
        installer = null;
    });

    // L'application installée n'a plus besoin d'être proposée.
    if (estInstallable()) return;

    // ------------------------------------------------------------------
    // Service worker : coquille applicative disponible hors ligne
    // ------------------------------------------------------------------
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            navigator.serviceWorker.register('/sw.js', { scope: '/' })
                .catch(function () {
                    // Pas de service worker : l'application fonctionne quand
                    // même, seulement sans mode hors ligne.
                });
        });
    }
})();