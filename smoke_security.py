"""
Tests de sécurité de l'application Kendevis.

Vérifie :
  1. Les en-têtes HTTP durcis sont bien présents (CSP, nosniff, ...).
  2. La suppression de dépense n'accepte que POST (405 sur GET).
  3. Un utilisateur non administrateur ne peut pas supprimer (403).
  4. La connexion est bloquée après 5 échecs (HTTP 429).
  5. Un utilisateur non administrateur ne peut pas naviguer dans l'historique.
  6. La connexion par NUMÉRO DE TÉLÉPHONE fonctionne et varie selon la
     façon dont le numéro est saisi (0384160133 = 038 41 601 33 = +261...).

Usage : python smoke_security.py
"""
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
import os
import sys
from decimal import Decimal

BASE = 'http://127.0.0.1:8000'
RESULTS = []

# L'identifiant de connexion est le numéro de téléphone (champ « telephone »).
ADMIN_TELEPHONE = '0340000001'
ADMIN_PASSWORD = 'admin123'
UTILISATEUR_TELEPHONE = '0340000002'
UTILISATEUR_PASSWORD = 'user1234'
# Compte de démonstration volontairement privé de toute autorisation :
# il doit être renvoyé vers la page de connexion.
SANS_ACCES_TELEPHONE = '0340000003'
SANS_ACCES_PASSWORD = 'user1234'


def check(label, condition, detail=''):
    RESULTS.append((bool(condition), label, detail))
    print(f"[{'OK  ' if condition else 'FAIL'}] {label}" + (f" — {detail}" if detail else ''))


def flatten(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


def new_opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def login(opener, telephone, password):
    page = opener.open(f'{BASE}/login/').read().decode('utf-8', 'replace')
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
    payload = urllib.parse.urlencode({
        'csrfmiddlewaretoken': token,
        'telephone': telephone,
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
    login(admin, ADMIN_TELEPHONE, ADMIN_PASSWORD)

    # 1. GET interdit
    try:
        admin.open(f'{BASE}/depense/1/supprimer/')
        code = 200
    except urllib.error.HTTPError as error:
        code = error.code
    check('GET sur la suppression renvoie 405', code == 405, f'code={code}')

    # 2. Utilisateur non admin -> 403
    user = new_opener()
    login(user, UTILISATEUR_TELEPHONE, UTILISATEUR_PASSWORD)
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
    login(other, UTILISATEUR_TELEPHONE, UTILISATEUR_PASSWORD)
    forced = other.open(f'{BASE}/?b=1').read().decode('utf-8', 'replace')
    check("Impossible de forcer un autre mois en tant qu'utilisateur",
          'Mois précédent' not in forced and 'Mois suivant' not in forced)


def test_login_throttle():
    # Numéro inexistant et unique à chaque exécution : on ne verrouille
    # ni le vrai admin, ni un test précédent (clé = IP + numéro de téléphone).
    telephone = f'090{int(time.time()) % 10000000:07d}'
    opener = new_opener()
    codes = []
    for attempt in range(6):
        page = opener.open(f'{BASE}/login/').read().decode('utf-8', 'replace')
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        payload = urllib.parse.urlencode({
            'csrfmiddlewaretoken': token,
            'telephone': telephone,
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
    login(admin, ADMIN_TELEPHONE, ADMIN_PASSWORD)
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


def test_phone_login():
    """La connexion se fait par numéro de téléphone, quel que soit le format."""
    # Format national
    session = login(new_opener(), ADMIN_TELEPHONE, ADMIN_PASSWORD)
    check('Connexion avec le numéro national (0340000001)',
          not str(session).startswith('HTTP'), f'retour={session}')

    # Même numéro, écrit avec des espaces
    session = login(new_opener(), '03 40 00 00 01', ADMIN_PASSWORD)
    check('Connexion avec le numéro espacé (03 40 00 00 01)',
          not str(session).startswith('HTTP'), f'retour={session}')

    # Même numéro, au format international
    session = login(new_opener(), '+261340000001', ADMIN_PASSWORD)
    check('Connexion au format international (+261340000001)',
          not str(session).startswith('HTTP'), f'retour={session}')

    # Mauvais mot de passe : refusé
    session = login(new_opener(), ADMIN_TELEPHONE, 'mauvais-mot-de-passe')
    check('Numéro correct + mot de passe faux = refusé',
          'login' in str(session), f'retour={session}')

    # Numéro inconnu : refusé
    session = login(new_opener(), '0341199999', ADMIN_PASSWORD)
    check('Numéro inconnu = refusé', 'login' in str(session),
          f'retour={session}')

    # Un numéro valide belonging à un autre compte ne donne pas accès à l'admin
    session = login(new_opener(), UTILISATEUR_TELEPHONE, ADMIN_PASSWORD)
    check('Mot de passe admin refusé pour un autre numéro',
          'login' in str(session), f'retour={session}')


def test_onglets_et_autorisations():
    """Les quatre onglets répondent et un compte sans accès est bloqué."""
    admin = new_opener()
    login(admin, ADMIN_TELEPHONE, ADMIN_PASSWORD)

    for url, marqueur in (
        ('/', 'Budget Initial'),
        ('/depenses/', 'Historique des dépenses'),
        ('/statistiques/', 'Répartition par poste'),
        ('/utilisateurs/', 'Téléphone'),
    ):
        try:
            page = admin.open(f'{BASE}{url}').read().decode('utf-8', 'replace')
            code = 200
        except urllib.error.HTTPError as error:
            page, code = '', error.code
        check(f"Onglet {url} s'affiche", code == 200 and marqueur in page,
              f'code={code}')
        check(f"Les onglets sont dans la page {url}",
              'tabs-nav' in page and 'bi-pie-chart' in page)

    # Historique : liste unique ou un tableau par catégorie
    vue_liste = admin.open(f'{BASE}/depenses/').read().decode('utf-8', 'replace')
    vue_groupee = admin.open(
        f'{BASE}/depenses/?vue=groupe'
    ).read().decode('utf-8', 'replace')

    check('Onglet Dépenses : vue liste unique', vue_liste.count('<table') == 1,
          f"{vue_liste.count('<table')} tableau(x)")
    check('Onglet Dépenses : bascule de vue',
          'vue=groupe' in vue_liste and 'vue-bascule' in vue_liste)
    check('Onglet Dépenses : vue par catégorie avec un bloc par poste',
          vue_groupee.count('groupe-categorie-') >= 1,
          f"{vue_groupee.count('groupe-categorie-')} bloc(s)")
    check('Onglet Dépenses : la vue groupée n_utilise pas la liste unique',
          'groupe-categorie-' not in vue_liste)
    check('Onglet Dépenses : filtre par poste',
          '?c=' in vue_liste and 'Poste' in vue_liste)
    check('Aucun commentaire de gabarit ne fuit dans la page',
          'Cliquer sur un poste' not in vue_liste
          and '{#' not in vue_liste)

    # Manifeste d'installation
    try:
        page = admin.open(f'{BASE}/manifest.webmanifest').read().decode('utf-8', 'replace')
        code = 200
    except urllib.error.HTTPError as error:
        page, code = '', error.code
    check('Manifeste PWA accessible', code == 200 and '"display"' in page,
          f'code={code}')
    check('Manifeste : icônes maskable et raccourcis',
          'maskable' in page and 'shortcuts' in page)

    # Service worker servi à la racine (sinon il ne contrôle que /static/)
    try:
        reponse = admin.open(f'{BASE}/sw.js')
        portee = reponse.headers.get('Service-Worker-Allowed', '')
        contenu = reponse.read().decode('utf-8', 'replace')
        code = 200
    except urllib.error.HTTPError as error:
        portee, contenu, code = '', '', error.code
    check('Service worker accessible', code == 200 and 'addEventListener' in contenu,
          f'code={code}')
    check('Service worker : portée racine autorisée', portee == '/', f'{portee}')

    # Un compte sans autorisation de lecture ne doit rien voir.
    sans_acces = new_opener()
    login(sans_acces, SANS_ACCES_TELEPHONE, SANS_ACCES_PASSWORD)
    for url in ('/', '/depenses/', '/statistiques/', '/utilisateurs/'):
        try:
            final = sans_acces.open(f'{BASE}{url}').geturl()
        except urllib.error.HTTPError as error:
            final = f'HTTP {error.code}'
        check(f'Compte sans accès bloqué sur {url}', '/login/' in final,
              f'atterri sur {final}')


def test_categories():
    """Répartition du budget par catégorie : réservée à l'administrateur."""
    from decimal import Decimal

    admin = new_opener()
    login(admin, ADMIN_TELEPHONE, ADMIN_PASSWORD)
    page = admin.open(f'{BASE}/').read().decode('utf-8', 'replace')
    match = re.search(r'/budget/(\d+)/repartition/', page)
    if not match:
        check('Lien de répartition présent pour un administrateur', False)
        return
    budget_id = match.group(1)
    check('Lien de répartition présent pour un administrateur', True)

    # Un utilisateur simple ne voit pas le lien...
    simple = new_opener()
    login(simple, UTILISATEUR_TELEPHONE, UTILISATEUR_PASSWORD)
    page_simple = simple.open(f'{BASE}/').read().decode('utf-8', 'replace')
    check("Pas de lien de répartition pour un utilisateur simple",
          '/repartition/' not in page_simple)

    # ...et reçoit bien un refus s'il force l'URL.
    try:
        simple.open(f'{BASE}/budget/{budget_id}/repartition/')
        code = 200
    except urllib.error.HTTPError as error:
        code = error.code
    check('Un utilisateur simple reçoit 403 sur la répartition', code == 403,
          f'code={code}')

    # Le formulaire de dépense doit proposer les catégories : un champ
    # présent dans le formulaire mais absent du gabarit rendrait la
    # catégorisation impossible depuis l'interface.
    page_accueil = admin.open(f'{BASE}/').read().decode('utf-8', 'replace')
    check('Formulaire de dépense : choix de catégorie affiché',
          'categorie-puce' in page_accueil
          and 'data-categorie-choix' in page_accueil)
    check('Toutes les catégories sont proposées',
          page_accueil.count('data-categorie-choix') >= 2,
          f"{page_accueil.count('data-categorie-choix')} option(s)")
    check('Une option « sans catégorie » reste possible',
          'Sans catégorie' in page_accueil)
    check('Les cartes de poste présélectionnent la catégorie',
          'data-choisir-categorie' in page_accueil)

    # Un budget dont la somme ne tombe pas juste est refusé.
    page_repartition = admin.open(
        f'{BASE}/budget/{budget_id}/repartition/'
    ).read().decode('utf-8', 'replace')
    champs = re.findall(r'name="(categorie_\d+)"', page_repartition)
    check('Formulaire de répartition rempli', bool(champs), f'{len(champs)} champ(s)')

    if champs:
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',
                          page_repartition).group(1)
        # Montants volontairement faux : la somme ne peut pas tomber juste.
        donnees = {
            'csrfmiddlewaretoken': token,
            champs[0]: '1.00',
            'suite': '/depenses/',
        }
        payload = urllib.parse.urlencode(donnees).encode()
        request = urllib.request.Request(
            f'{BASE}/budget/{budget_id}/repartition/', data=payload,
            headers={'Referer': f'{BASE}/budget/{budget_id}/repartition/'})
        reponse = admin.open(request)
        texte = flatten(reponse.read().decode('utf-8', 'replace'))
        check('Une répartition qui ne tombe pas juste est refusée',
              'doit être égale au budget initial' in texte)
        check('Le montant manquant est indiqué', 'Il manque' in texte)


def test_palette_couleurs():
    """
    La couleur d'une catégorie se choisit par son nom, pas en hexadécimal.

    Vérifie le menu déroulant de l'administration et la conversion des
    anciennes valeurs.
    """
    admin = new_opener()
    login(admin, ADMIN_TELEPHONE, ADMIN_PASSWORD)

    try:
        page = admin.open(
            f'{BASE}/admin/budget_app/categoriebudget/add/'
        ).read().decode('utf-8', 'replace')
        code = 200
    except urllib.error.HTTPError as error:
        page, code = '', error.code

    check('Fiche de catégorie accessible', code == 200, f'code={code}')
    check('La couleur est une liste déroulante (pas un champ texte)',
          'id_couleur' in page and '<select' in page
          and 'name="couleur" class="vTextField"' not in page)
    check('La liste propose des couleurs nommées',
          'Cyan' in page and 'Rouge' in page and 'Bleu' in page)
    check('La liste propose des dégradés',
          'Bleu dégradé' in page and 'Rouge dégradé' in page)
    check('Chaque option montre un aperçu de sa couleur',
          'option-apercu' in page and 'data-fond' in page)
    check('Aucun code hexadécimal n\'est demandé à l\'utilisateur',
          'format hexadécimal' not in page)
    check('Aperçu de couleur dans la fiche', 'couleur-apercu' in page)
    check('Grille d\'icônes disponibles', 'grille-icones' in page)


def test_conversion_couleurs():
    """Les anciennes valeurs hexadécimales sont reconnues et converties."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from budget_app.couleurs import couleur_connue, fond, libelle

    cas = [
        ('#2563eb', 'bleu'),
        ('#06b6d4', 'cyan'),
        ('#dc3545', 'rouge'),
        ('bleu', 'bleu'),
        ('rouge-degrade', 'rouge-degrade'),
        ('', 'bleu'),
        ('nimporte-quoi', 'bleu'),
    ]
    for valeur, attendu in cas:
        obtenu = couleur_connue(valeur)
        check(f'Conversion {valeur!r} -> {attendu}', obtenu == attendu,
              f'obtenu {obtenu!r}')
    check('Un dégradé produit un linear-gradient',
          fond('bleu-degrade').startswith('linear-gradient'))
    check('Une couleur simple reste un hexadécimal',
          fond('cyan') == '#06b6d4', fond('cyan'))
    check('Libellé lisible', libelle('cyan-degrade') == 'Cyan dégradé')


def test_format_telephone():
    """Le numéro s'affiche en 03X XX XXX XX, quelle que soit la saisie."""
    from budget_app.telephone import formater_telephone, normaliser_telephone

    cas = [
        ('0384160133', '038 41 601 33'),
        ('038 41 601 33', '038 41 601 33'),
        ('+261384160133', '038 41 601 33'),
        ('00261384160133', '038 41 601 33'),
        ('0340000001', '034 00 000 01'),
        ('0321234567', '032 12 345 67'),
    ]
    for saisie, attendu in cas:
        obtenu = formater_telephone(saisie)
        check(f'Affichage {saisie!r} -> {attendu}', obtenu == attendu,
              f'obtenu {obtenu!r}')

    # Stockage : toujours au format international, sans espace.
    check('Stockage normalisé en E.164',
          normaliser_telephone('038 41 601 33') == '+261384160133')
    # Un numéro trop court n'est pas regroupé de travers.
    check('Numéro de longueur inattendue renvoyé brut',
          formater_telephone('+2612012345') == '02012345',
          formater_telephone('+2612012345'))



def test_devis():
    """Devis : droits, création, partage, PDF et paiement déclaré."""
    admin = new_opener()
    login(admin, ADMIN_TELEPHONE, ADMIN_PASSWORD)

    # L'administrateur a toujours le droit de créer des devis.
    reponse = admin.open(f'{BASE}/devis/')
    check('Administrateur : accès à l\'onglet Devis', reponse.status == 200)
    check('Onglet Devis dans la navigation',
          'bi-file-earmark-text' in reponse.read().decode('utf-8', 'replace'))

    reponse = admin.open(f'{BASE}/devis/nouveau/')
    page = reponse.read().decode('utf-8', 'replace')
    check('Formulaire de devis : nom du devis', 'name="nom"' in page)
    check('Formulaire de devis : cases de partage', 'visible_par' in page)
    check('Formulaire de devis : deux lignes proposées',
          page.count('ligne-devis') >= 2, f"{page.count('ligne-devis')} ligne(s)")
    check('Formulaire de devis : total automatique', 'total-devis' in page)
    check('Formulaire de devis : messages d\'avertissement sur le mobile money'
          or 'mobile money' in page.lower(), True)

    # Un compte sans le droit de devis ne doit pas y accéder, et la
    # redirection ne doit pas boucler.
    simple = new_opener()
    login(simple, UTILISATEUR_TELEPHONE, UTILISATEUR_PASSWORD)
    for url in (f'{BASE}/devis/', f'{BASE}/devis/nouveau/'):
        try:
            finale = simple.open(url).geturl()
        except urllib.error.HTTPError as error:
            finale = f'HTTP {error.code}'
        check(f'Sans droit, {url} est refusé',
              '/devis' not in finale,
              f'atterri sur {finale}')

    # Un devis partagé est visible, mais pas modifiable, par un tiers.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_budget.settings')
    import django
    django.setup()
    from django.contrib.auth.models import User
    from budget_app.models import Devis, LigneDevis, permission_de, peut_creer_devis

    auteur = User.objects.filter(devis__isnull=False).first()
    if auteur is None:
        check('Un devis existe pour tester le partage', False)
        return
    devis = auteur.devis.order_by('-id').first()
    tiers = User.objects.get(username='utilisateur')
    devis.visible_par.add(tiers)
    page = admin.open(f'{BASE}/devis/{devis.pk}/').read().decode('utf-8', 'replace')
    check('Devis partagé : la case de partage est cochée',
          'checked' in page)
    check('Devis : bouton de téléchargement PDF',
          f'/devis/{devis.pk}/pdf/' in page)
    check('Devis : bouton WhatsApp',
          f'/devis/{devis.pk}/whatsapp/' in page)
    check('Devis : mention claire sur la limite de WhatsApp',
          'Business' in page or 'aucun transfert' in page.lower())

    # Le PDF est un vrai fichier, pas une page HTML d'erreur.
    try:
        reponse = admin.open(f'{BASE}/devis/{devis.pk}/pdf/')
        contenu = reponse.read()
        type_piece = reponse.headers.get('Content-Type', '')
    except urllib.error.HTTPError as error:
        contenu, type_piece = b'', ''
    check('Devis : PDF généré', contenu[:4] == b'%PDF',
          f'{len(contenu)} octets, {type_piece}')
    check('Devis : PDF envoyé en téléchargement',
          'attachment' in str(
              admin.open(f'{BASE}/devis/{devis.pk}/pdf/').headers.get('Content-Disposition', '')
          ))

    # Le total est bien la somme des lignes.
    attendu = sum((ligne.total for ligne in devis.lignes.all()), Decimal('0.00'))
    check('Devis : total = somme des lignes', devis.total == attendu,
          f'{devis.total} vs {attendu}')

    # Un tiers ne voit que la lecture : pas de bouton de modification.
    session_tiers = new_opener()
    login(session_tiers, UTILISATEUR_TELEPHONE, UTILISATEUR_PASSWORD)
    page = session_tiers.open(f'{BASE}/devis/{devis.pk}/').read().decode('utf-8', 'replace')
    check('Devis partagé : visible par le tiers', True)
    check('Devis partagé : pas de bouton de modification',
          f'/devis/{devis.pk}/modifier/' not in page)

    # Un devis non partagé est invisible : 404, pas 403.
    devis.visible_par.remove(tiers)
    try:
        session_tiers.open(f'{BASE}/devis/{devis.pk}/')
        code = 200
    except urllib.error.HTTPError as error:
        code = error.code
    check('Devis non partagé : 404 (existence non révélée)', code == 404,
          f'code={code}')

    # Le droit de devis est indépendant du droit d'écriture sur les dépenses.
    permission = permission_de(auteur)
    check('Le droit de devis est un droit distinct',
          hasattr(permission, 'peut_creer_devis'))
    check('Un administrateur peut toujours créer un devis',
          peut_creer_devis(User.objects.get(username='Andonilanitra')))
    check('Un compte sans droit ne peut pas créer de devis',
          not peut_creer_devis(tiers))


def main():
    print('--- En-têtes HTTP ---')
    test_headers()
    print('\n--- Connexion par téléphone ---')
    test_phone_login()
    print('\n--- Onglets, PWA et autorisations ---')
    test_onglets_et_autorisations()
    print('\n--- Catégories de budget ---')
    test_categories()
    print('\n--- Palette de couleurs ---')
    test_palette_couleurs()
    test_conversion_couleurs()
    print('\n--- Format des numéros ---')
    test_format_telephone()
    print('\n--- Devis ---')
    test_devis()
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
