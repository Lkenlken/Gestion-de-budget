"""
Test de fumée : connexion + rendu du tableau de bord.
Usage : python smoke_test.py
"""
import re
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar

BASE = 'http://127.0.0.1:8000'

# L'identifiant de connexion est le NUMÉRO DE TÉLÉPHONE de l'administrateur
# (champ « telephone » du formulaire de connexion).
ADMIN_TELEPHONE = '0340000001'
ADMIN_PASSWORD = 'admin123'


def flatten(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def nombre_depenses(texte):
    """
    Nombre de dépenses annoncé dans le tableau,lu dans le texte rendu.

    On ne dépend pas d'un nombre en dur : le compteur est relu à chaque étape
    et l'on vérifie qu'il augmente puis revient à sa valeur de départ.
    """
    trouve = re.search(r'(\d+)\s+d[ée]penses', texte)
    return int(trouve.group(1)) if trouve else -1


def main():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    login_page = opener.open(f'{BASE}/login/').read().decode('utf-8', 'replace')
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_page).group(1)

    payload = urllib.parse.urlencode({
        'csrfmiddlewaretoken': csrf,
        'telephone': ADMIN_TELEPHONE,
        'password': ADMIN_PASSWORD,
        'next': '/',
    }).encode()
    req = urllib.request.Request(f'{BASE}/login/', data=payload, headers={'Referer': f'{BASE}/login/'})
    try:
        response = opener.open(req)
        print('POST /login/ ->', response.status, response.geturl())
    except urllib.error.HTTPError as error:
        print('POST /login/ ->', error.code)
        print(flatten(error.read().decode('utf-8', 'replace'))[:2000])
        return

    try:
        page = opener.open(f'{BASE}/').read().decode('utf-8', 'replace')
        print('GET / -> 200, taille', len(page))
    except urllib.error.HTTPError as error:
        print('GET / ->', error.code)
        print(flatten(error.read().decode('utf-8', 'replace'))[:2000])
        return

    text = flatten(page)
    for keyword in ['Budget Initial', 'Total Dépensé', 'Solde Restant',
                    'Historique des Dépenses', 'Invalid filter', 'TemplateSyntax',
                    'NoReverseMatch', 'Object at 0x']:
        index = text.find(keyword)
        print(f'{keyword!r}:', text[max(0, index - 60):index + 160] if index >= 0 else 'ABSENT')

    # Vérifie que les pourcentages sont bien calculés
    print('Pourcentages trouvés :', re.findall(r'\d+(?:\.\d+)?%', text)[:10])
    print('Barres de progression :', re.findall(r'width:\s*\d+%;', page))
    return opener, csrf


def fresh_csrf(opener):
    """Récupère un jeton CSRF neuf (Django le fait tourner après la connexion)."""
    page = opener.open(f'{BASE}/').read().decode('utf-8', 'replace')
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)


def add_expense(opener, csrf, designation='Dépense de test smoke'):
    payload = urllib.parse.urlencode({
        'csrfmiddlewaretoken': fresh_csrf(opener),
        'date': '2026-10-06',
        'designation': designation,
        'prix_unitaire': '1000.00',
        'quantite': '3',
    }).encode()
    req = urllib.request.Request(f'{BASE}/', data=payload, headers={'Referer': f'{BASE}/'})
    response = opener.open(req)
    print('POST / (ajout) ->', response.status, response.geturl())
    return response.read().decode('utf-8', 'replace')


def delete_expense(opener, csrf, designation):
    page = opener.open(f'{BASE}/').read().decode('utf-8', 'replace')
    depense_id = None
    for row in re.findall(r'<tr>.*?</tr>', page, re.S):
        if designation in row:
            found = re.search(r'action="/depense/(\d+)/supprimer/"', row)
            if found:
                depense_id = found.group(1)
                break
    if depense_id is None:
        print('Aucune ligne à supprimer trouvée pour :', designation)
        return None
    payload = urllib.parse.urlencode({'csrfmiddlewaretoken': fresh_csrf(opener)}).encode()
    req = urllib.request.Request(
        f'{BASE}/depense/{depense_id}/supprimer/',
        data=payload, headers={'Referer': f'{BASE}/'})
    response = opener.open(req)
    print(f'POST /depense/{depense_id}/supprimer/ ->', response.status, response.geturl())
    return response.read().decode('utf-8', 'replace')


def logout(opener):
    token = fresh_csrf(opener)
    payload = urllib.parse.urlencode({'csrfmiddlewaretoken': token}).encode()
    req = urllib.request.Request(f'{BASE}/logout/', data=payload, headers={'Referer': f'{BASE}/'})
    response = opener.open(req)
    print('POST /logout/ ->', response.status, response.geturl())
    # Après déconnexion, l'accès au tableau de bord doit rediriger vers /login/
    request = urllib.request.Request(f'{BASE}/', method='GET')
    final = opener.open(request)
    print('GET / après déconnexion ->', final.status, final.geturl())


if __name__ == '__main__':
    session = main()
    if session:
        opener, csrf = session
        avant = nombre_depenses(flatten(opener.open(f'{BASE}/').read().decode('utf-8', 'replace')))

        after_add = add_expense(opener, csrf)
        text_add = flatten(after_add)
        print(f'Après ajout : montant affiché =',
              '3000,00 Ar' in text_add or '3 000,00' in text_add,
              f'| dépenses : {avant} -> {nombre_depenses(text_add)}')
        after_del = delete_expense(opener, csrf, 'Dépense de test smoke')
        if after_del:
            text_del = flatten(after_del)
            print('Après suppression :', nombre_depenses(text_del) == avant,
                  f"| message de confirmation présent :",
                  'a été supprimée' in text_del)
        logout(opener)
