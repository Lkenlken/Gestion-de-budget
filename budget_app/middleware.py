"""
Middlewares de sécurité ajoutés au projet.

SecurityHeadersMiddleware
-------------------------
Ajoute à chaque réponse les en-têtes HTTP durcis :
  * Content-Security-Policy : limite les sources de scripts/styles/images
    (le site charge Bootstrap et les icônes depuis cdn.jsdelivr.net et la
    police depuis fonts.googleapis.com).
  * Referrer-Policy, Permissions-Policy, Cross-Origin-Opener-Policy.
  * X-Content-Type-Options (le navigateur ne doit jamais "deviner" le type).

Ces en-têtes sont envoyés en développement comme en production : ils ne
dépendent pas de DEBUG et ne cassent donc jamais le comportement local.
"""

# Sources externes autorisées (CDN Bootstrap / icônes / polices Google).
CSP_DIRECTIVES = {
    'default-src': ["'self'"],
    'script-src': ["'self'", "'unsafe-inline'", 'https://cdn.jsdelivr.net'],
    'style-src': ["'self'", "'unsafe-inline'",
                  'https://cdn.jsdelivr.net', 'https://fonts.googleapis.com'],
    'font-src': ["'self'",
                 'https://cdn.jsdelivr.net', 'https://fonts.gstatic.com'],
    'img-src': ["'self'", 'data:'],
    'connect-src': ["'self'"],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'none'"],
}


def build_csp():
    """Construit la chaîne Content-Security-Policy à partir du dictionnaire."""
    return '; '.join(
        f"{directive} {' '.join(sources)}"
        for directive, sources in CSP_DIRECTIVES.items()
    )


class SecurityHeadersMiddleware:
    """Ajoute les en-têtes de sécurité à chaque réponse Django."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.csp = build_csp()

    def __call__(self, request):
        response = self.get_response(request)

        # En-têtes inconditionnels (y compris pour les réponses d'erreur)
        response.headers.setdefault('Content-Security-Policy', self.csp)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault(
            'Permissions-Policy',
            'geolocation=(), microphone=(), camera=(), payment=(), usb=()',
        )
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        # 0 et non "1" : la protection XSS obsolète du navigateur peut
        # introduire des failles, on préfère la CSP.
        response.headers.setdefault('X-XSS-Protection', '0')

        return response
