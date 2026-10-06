"""
Tests de sécurité de l'application Kendevis.

Vérifie :
  1. Les en-têtes HTTP durcis sont bien présents (CSP, nosniff, ...).
  2. La suppression de dépense n'accepte que POST (405 sur GET).
  3. Un utilisateur non administrateur ne peut pas supprimer (403).
  4. La connexion est bloquée après 5 échecs (HTTP 429).
  5. Un utilisateur non administrateur ne peut pas naviguer dans l'historique.

Usage : python smoke_security.py
"""
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar

BASE = 'http://127.0.0.1:8000'
RESULTS = []


def check(label, condition, detail=''):
    RESULTS.append((bool(condition), label, detail))
    print(f"[{'OK  ' if condition else 'FAIL'}] {label}" + (f" — {detail}" if detail else ''))


def flatten(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def new_opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def login(opener, username, password):
    page = opener.open(f'{BASE}/login/').read().decode('utf-8', 'replace')
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
    payload = urllib.parse.urlencode({
        'csrfmiddlewaretoken': token,
        'username': username,
        'password': password,
        'next': '/',
    }).encode()
    request = urllib.request.Request(
        f'{BASE}/login/', data=payload, headers={'Referer': f'{BASE}/login/'})
    try:
        response = opener.open(request)
        return response.geturl()
    except urllib.error.HTTPError as error:
        return f'HTTP {error.code}'


def post(opener, url, token):
    payload = urllib.parse.urlencode({'csrfmiddlewaretoken': token}).encode()
    request = urllib.request.Request(
        url, data=payload, headers={'Referer': f'{BASE}/'})
    try:
        response = opener.open(request)
        return response.status, response.geturl()
    except urllib.error.HTTPError as error:
        return error.code, url


def csrf_of(opener, url=f'{BASE}/'):
    page = opener.open(url).read().decode('utf-8', 'replace')
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)


def test_headers():
    response = urllib.request.urlopen(f'{BASE}/login/')
    headers = {k.lower(): v for k, v in response.headers.items()}
    check('Content-Security-Policy présente',
          'content-security-policy' in headers)
    check("CSP limite les sources (default-src 'self')",
          "default-src 'self'" in headers.get('content-security-policy', ''))
    check('X-Content-Type-Options: nosniff',
          headers.get('x-content-type-options') == 'nosniff')
    check('Referrer-Policy: same-origin',
          headers.get('referrer-policy') == 'same-origin')
    check('Permissions-Policy présente',
          'permissions-policy' in headers)
    check('Cookies de session inaccessibles au JS (HttpOnly)',
          'httponly' in headers.get('set-cookie', '').lower()
          or 'httponly' in ' '.join(response.headers.get_all('Set-Cookie') or []).lower())


def test_method_and_rights():
    admin = new_opener()
    login(admin, 'admin', 'admin123')

    # 1. GET interdit
    try:
        admin.open(f'{BASE}/depense/1/supprimer/')
        code = 200
    except urllib.error.HTTPError as error:
        code = error.code
    check('GET sur la suppression renvoie 405', code == 405, f'code={code}')

    # 2. Utilisateur non admin -> 403
    user = new_opener()
    login(user, 'utilisateur', 'user1234')
    page = user.open(f'{BASE}/').read().decode('utf-8', 'replace')
    depense_id = re.search(r'/depense/(\d+)/supprimer/', page)
    depense_id = depense_id.group(1) if depense_id else '1'
    code, _ = post(user, f'{BASE}/depense/{depense_id}/supprimer/', csrf_of(user))
    check('Un utilisateur classique reçoit 403', code == 403, f'code={code}')

    # 3. L'utilisateur classique ne voit ni bouton de suppression ni admin
    check("Pas de bouton de suppression pour un non-admin",
          '/supprimer/' not in page)
    check("Pas de lien administration pour un non-admin",
          '/admin/' not in page)
    check("Pas de navigation dans l'historique pour un non-admin",
          'history-nav' not in page)

    # 4. Non-admin ne peut pas forcer la navigation par mois
    other = new_opener()
    login(other, 'utilisateur', 'user1234')
    forced = other.open(f'{BASE}/?b=1').read().decode('utf-8', 'replace')
    check("Impossible de forcer un autre mois en tant qu'utilisateur",
          'Mois précédent' not in forced and 'Mois suivant' not in forced)


def test_login_throttle():
    # Compte inexistant et nom unique à chaque exécution : on ne verrouille
    # ni le vrai admin, ni un test précédent (clé = IP + nom d'utilisateur).
    username = f'compte-de-test-{int(time.time())}'
    opener = new_opener()
    codes = []
    for attempt in range(6):
        page = opener.open(f'{BASE}/login/').read().decode('utf-8', 'replace')
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        payload = urllib.parse.urlencode({
            'csrfmiddlewaretoken': token,
            'username': username,
            'password': f'mauvais-mdp-{attempt}',
            'next': '/',
        }).encode()
        request = urllib.request.Request(
            f'{BASE}/login/', data=payload, headers={'Referer': f'{BASE}/login/'})
        try:
            response = opener.open(request)
            codes.append(response.status)
        except urllib.error.HTTPError as error:
            codes.append(error.code)

    check('Les 5 premières tentatives échouées retournent 200',
          all(code == 200 for code in codes[:5]), f'codes={codes}')
    check('La 6e tentative est bloquée (HTTP 429)', codes[5] == 429, f'codes={codes}')


def test_admin_pages():
    """L'administration doit rester accessible et afficher les montants."""
    admin = new_opener()
    login(admin, 'admin', 'admin123')
    for url in ('/admin/', '/admin/budget_app/budgetmensuel/',
                '/admin/budget_app/depense/'):
        try:
            response = admin.open(f'{BASE}{url}')
            code, body = response.status, response.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as error:
            code, body = error.code, ''
        check(f'Administration {url}', code == 200, f'code={code}')

    try:
        page = admin.open(
            f'{BASE}/admin/budget_app/budgetmensuel/'
        ).read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        page = ''
        check("Liste des budgets dans l'administration", False, f'code={error.code}')
    else:
        check("Liste des budgets dans l'administration", True)
    check("Le solde restant s'affiche en clair (pas de HTML échappé)",
          'Solde Restant' in page and '&lt;strong' not in page)


def main():
    print('--- En-têtes HTTP ---')
    test_headers()
    print('\n--- Méthodes HTTP et droits ---')
    test_method_and_rights()
    print('\n--- Limitation des tentatives de connexion ---')
    test_login_throttle()
    print('\n--- Administration ---')
    test_admin_pages()

    failed = [item for item in RESULTS if not item[0]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} tests réussis.")
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
