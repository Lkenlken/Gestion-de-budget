/**
 * Service worker de Kendevis.
 *
 * Objectif : permettre l'installation sur l'écran d'accueil (Android, Windows,
 * macOS) et l'affichage du tableau de bord même sans réseau.
 *
 * Stratégie :
 *   - fichiers statiques (CSS, JS, icônes) : cache d'abord, puis réseau.
 *     Ils changent rarement et permettent une ouverture instantanée ;
 *   - pages de l'application : réseau d'abord, cache en secours. Les données
 *     du budget doivent toujours être fraîches quand le réseau fonctionne.
 *
 * La version du cache est à incrémenter à chaque modification des fichiers
 * statiques : c'est elle qui déclenche la suppression des anciennes copies.
 */

const VERSION = 'kendevis-v1';
const CACHE = VERSION + '-statique';

// Ressources prises en cache à l'installation. La page de connexion est
// incluse pour que l'application s'ouvre même totalement hors ligne.
const PRECHARGE = [
    '/static/budget_app/css/style.css',
    '/static/budget_app/js/ui.js',
    '/static/budget_app/js/budget_realtime.js',
    '/static/budget_app/icons/icon-192.png',
    '/static/budget_app/icons/icon-512.png',
    '/login/',
];

self.addEventListener('install', (evenement) => {
    evenement.waitUntil(
        caches.open(CACHE)
            // `reload` évite de recopier une version HTTP en cache stale.
            .then((cache) => cache.addAll(
                PRECHARGE.map((url) => new Request(url, { cache: 'reload' }))
            ))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (evenement) => {
    evenement.waitUntil(
        caches.keys()
            .then((noms) => Promise.all(
                noms.filter((nom) => nom !== CACHE)
                    .map((nom) => caches.delete(nom))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (evenement) => {
    const requete = evenement.request;

    // Seules les requêtes HTTP(S) en GET sont interceptées.
    if (requete.method !== 'GET') return;

    const url = new URL(requete.url);
    if (url.origin !== self.location.origin) return;

    // Les formulaires d'administration et de suppression ne sont jamais
    // mis en cache : une réponse périmée y serait dangereuse.
    if (requete.mode === 'navigate' && !url.pathname.startsWith('/depense/')) {
        evenement.respondWith(reseauDAbord(requete));
        return;
    }

    if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/media/')) {
        evenement.respondWith(cacheDAbord(requete));
    }
});

/** Réseau d'abord : sert la version fraîche, garde une copie pour le hors ligne. */
async function reseauDAbord(requete) {
    const cache = await caches.open(CACHE);
    try {
        const reponse = await fetch(requete);
        // Une redirection vers la page de connexion n'est pas mise en cache :
        // la servirait hors ligne, elle laisserait croire à une session ouverte.
        if (reponse.ok && !requete.redirected) {
            cache.put(requete, reponse.clone());
        }
        return reponse;
    } catch (erreur) {
        const enCache = await cache.match(requete);
        if (enCache) return enCache;
        // Dernier recours : la page de connexion, toujours disponible.
        const connexion = await cache.match('/login/');
        if (connexion) return connexion;
        return new Response(
            '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width,initial-scale=1">'
            + '<title>Hors ligne</title></head><body style="font-family:sans-serif;'
            + 'padding:2rem;text-align:center"><h1>Hors ligne</h1>'
            + '<p>Connexion Internet nécessaire pour accéder au budget.</p></body></html>',
            { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
    }
}

/** Cache d'abord : instantané, et rafraîchi en arrière-plan si nécessaire. */
async function cacheDAbord(requete) {
    const cache = await caches.open(CACHE);
    const enCache = await cache.match(requete);
    if (enCache) return enCache;

    try {
        const reponse = await fetch(requete);
        if (reponse.ok) cache.put(requete, reponse.clone());
        return reponse;
    } catch (erreur) {
        return new Response('', { status: 504 });
    }
}