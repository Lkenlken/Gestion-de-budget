"""
Fichiers de l'application installable (PWA).

Trois vues servent ces fichiers à la racine du site, ce qui est indispensable :

* `/manifest.webmanifest` — doit être à la racine, sinon la portée
  (`scope`) de l'application se limite au dossier où il est servi.
* `/sw.js` — un service worker servi depuis un sous-dossier ne peut
  contrôler que ce sous-dossier. Servi à la racine, il contrôle tout le site,
  ce qui permet le mode hors ligne.
* Les icônes sont des fichiers statiques ordinaires
  (`budget_app/static/budget_app/icons/`).
"""
from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static
from django.views.decorators.cache import never_cache

COULEUR_THEME = '#2563eb'
COULEUR_FOND = '#f8fafc'


@never_cache
def manifest(request):
    """Manifeste d'installation : icône, écran de démarrage, raccourcis."""
    contenu = {
        'name': 'Kendevis — Gestion de Budget',
        'short_name': 'Kendevis',
        'description': (
            'Gestion mensuelle assistée et automatique d\'un budget : '
            'saisie des dépenses et suivi du solde en temps réel.'
        ),
        'lang': 'fr',
        'dir': 'ltr',
        'start_url': '/',
        # Portée large : l'app installée couvre tout le site.
        'scope': '/',
        'display': 'standalone',
        'display_override': ['standalone', 'minimal-ui'],
        'orientation': 'any',
        'theme_color': COULEUR_THEME,
        'background_color': COULEUR_FOND,
        'categories': ['finance', 'productivity', 'utilities'],
        'icons': [
            {
                'src': static('budget_app/icons/icon-192.png'),
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': static('budget_app/icons/icon-512.png'),
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                # Icône sans coins arrondis et au centre : Android peut la
                # rogner jusqu'à 40 % lors de l'ajout à l'écran d'accueil.
                'src': static('budget_app/icons/icon-maskable-512.png'),
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ],
        # Raccourcis : appui long sur l'icône de l'écran d'accueil
        # (Android, Windows, macOS) pour ouvrir directement une section.
        'shortcuts': [
            {
                'name': 'Tableau de bord',
                'short_name': 'Budget',
                'url': '/',
                'icons': [{'src': static('budget_app/icons/icon-192.png'), 'sizes': '192x192'}],
            },
            {
                'name': 'Dépenses',
                'short_name': 'Dépenses',
                'url': '/depenses/',
                'icons': [{'src': static('budget_app/icons/icon-192.png'), 'sizes': '192x192'}],
            },
            {
                'name': 'Statistiques',
                'short_name': 'Stats',
                'url': '/statistiques/',
                'icons': [{'src': static('budget_app/icons/icon-192.png'), 'sizes': '192x192'}],
            },
        ],
    }
    reponse = JsonResponse(contenu, json_dumps_params={'ensure_ascii': False})
    reponse['Content-Type'] = 'application/manifest+json; charset=utf-8'
    return reponse


@never_cache
def service_worker(request):
    """
    Sert le service worker à la racine du domaine.

    `never_cache` est indispensable : un service worker reste enregistré
    longtemps, un navigateur qui le garde en cache garderait l'ancienne
    version et les nouvelles modifications ne prendraient jamais effet.
    """
    chemin = 'budget_app/js/sw.js'
    try:
        with open(staticfiles_abspath(chemin), 'rb') as fichier:
            contenu = fichier.read()
    except OSError:
        return HttpResponse('// Service worker introuvable.', status=404,
                            content_type='text/javascript')

    reponse = HttpResponse(contenu, content_type='text/javascript; charset=utf-8')
    # Autorise ce fichier à contrôler tout le site, y compris la racine.
    reponse['Service-Worker-Allowed'] = '/'
    return reponse


def staticfiles_abspath(chemin):
    """Chemin sur disque d'un fichier statique de l'application."""
    import os

    import budget_app

    dossier = os.path.join(os.path.dirname(budget_app.__file__), 'static')
    return os.path.join(dossier, *chemin.split('/'))