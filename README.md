# Kendevis — Gestion de Budget Mensuel

Application web Django pour la gestion mensuelle assistée et automatique d'un
budget : création de budgets par mois, saisie des dépenses, suivi du solde en
temps réel.

---

## 1. Installation

```bash
# Dépendances
pip install -r requirements.txt

# Base de données (SQLite en développement)
python manage.py migrate

# Créer le compte administrateur (connexion par téléphone)
python manage.py creer_admin

# Données de démonstration facultatives (budget + dépenses fictives)
python seed_demo.py

# Lancer le serveur
python manage.py runserver
```

L'application est ensuite accessible sur <http://127.0.0.1:8000/>.

### Comptes et connexion par téléphone

L'identifiant de connexion est le **numéro de téléphone** du compte, pas un
nom d'utilisateur. Les trois écritures suivantes désignent le même compte :

```
0384160133      038 41 601 33      +261384160133
```

Les numéros sont stockés au format international (`+261384160133`) quel que
soit le format saisi : impossible d'avoir deux comptes pour le même numéro.

**Créer un administrateur** (le mot de passe est saisi en caché) :

```bash
python manage.py creer_admin
# Nom du compte (ex : Andonilanitra) : Andonilanitra
# Téléphone (ex : 0384160133)      : 0384160133
# Mot de passe de « Andonilanitra » : ********
```

La commande crée aussi le profil et les droits (lecture + écriture). Elle est
idempotente : relancer avec les mêmes valeurs met à jour le compte existant
au lieu d'en créer un second.

**Rattacher des dépenses existantes à une catégorie** (après la mise en place
des postes, sur un budget saisi auparavant) :

```bash
# Voir l'état actuel, sans rien modifier
python manage.py categoriser_depenses --statistiques

# Rattacher les dépenses non catégorisées à « Courses »
python manage.py categoriser_depenses --categorie "Courses"

# Sur un mois précis, en confirmant automatiquement
python manage.py categoriser_depenses --categorie "Courses" --mois "Octobre 2026" --oui

# Revenir en arrière
python manage.py categoriser_depenses --categorie "Courses" --retirer
```

La commande affiche toujours un aperçu (nombre de lignes, montants, par mois)
et demande confirmation, sauf avec `--oui`. Sans `--remplacer`, seules les
dépenses **non encore** catégorisées sont touchées : des dépenses déjà
correctement classées ne bougent pas.

**Changer le mot de passe d'un compte existant** :

```bash
python manage.py changer_mot_de_passe --nom Andonilanitra
```

Le compte est identifié par son nom ou par son numéro de téléphone. Le mot de
passe est saisi en caché, jamais en argument de ligne de commande, et toutes
les sessions ouvertes avec l'ancien mot de passe sont déconnectées.

> ⚠️ En production : utilisez un mot de passe long et unique, générez une vraie
> `SECRET_KEY` dans `.env`, passez `DEBUG=False` et servez l'application en HTTPS.

### Répartir le budget par catégorie

1. **Définir les postes** (une seule fois) : administration →
   *Gestion de Budget → Catégories de budget*. Pour chaque poste on choisit
   une **couleur par son nom** dans une liste (bleu, cyan, rouge, ambre,
   violet…) ou un **dégradé** (bleu dégradé, cyan dégradé…), avec un aperçu
   visuel ; et une icône en cliquant dessus. Une catégorie déjà utilisée ne
   peut plus être supprimée — la désactiver suffit.
2. **Répartir le mois** : onglet *Statistiques* → *Répartir le budget*, ou
   directement dans la fiche du budget mensuel (administration).

Exemple : budget initial de 250 000 Ar → courses 100 000 Ar + provisions
150 000 Ar. La somme doit être **exactement** égale au budget initial, sinon
l'enregistrement est refusé et le montant manquant est indiqué.

3. **Saisir les dépenses** : dans le bloc *Nouvelle Dépense*, la catégorie se
   choisit parmi des puces colorées — un clic sur un poste du bloc *Suivi par
   catégorie* la préselectionne et amène le curseur dans le champ
   *Désignation*. Le tableau de bord affiche alors la consommation de chaque
   poste et signale les dépassements.

---

## 2. Fonctionnalités

- **Historique par poste** : l'onglet Dépenses propose une vue « liste unique »
  ou une vue « par catégorie » qui sépare complètement chaque poste avec son
  sous-total, plus un filtre rapide sur un poste donné.
- **Navigation par onglets** : Tableau de bord, Dépenses, Statistiques,
  Utilisateurs, Administration.
- **Sous-budgets par catégorie** : l'administrateur répartit le budget initial
  en postes (courses, provisions, transport…) ; chaque dépense est rattachée à
  un poste, ce qui affiche « Courses : 50 000 / 100 000 Ar » et le solde
  restant de chaque poste. La somme des parts doit être exactement égale au
  budget initial.
- **Application installable** (PWA) : une icône sur l'écran d'accueil du
  téléphone ou de l'ordinateur, ouverture en plein écran, raccourcis vers
  Budget / Dépenses / Stats, et ouverture du tableau de bord sans connexion.
- **Tableau de bord** : budget initial, total dépensé, solde restant, barre de
  progression, compteurs animés et historique des dépenses.
- **Ajout de dépense** : calcul du montant total en temps réel (prix unitaire ×
  quantité), validation côté client et côté serveur.
- **Navigation dans l'historique** : boutons « mois précédent / mois suivant »
  (réservés aux administrateurs), sélecteur via `?b=<id>`.
- **Recherche instantanée** dans le tableau des dépenses.
- **Thème clair / sombre** et **taille de police** (A- / A / A+) mémorisés dans
  le navigateur.
- **Interface** : palette de couleurs unifiée, cartes animées au survol, onde au
  clic, ombres et dégradés, animations d'apparition, `prefers-reduced-motion`
  respecté, responsive mobile, styles d'impression.
- **Administration Django** : listes, filtres, recherche, montants colorés.

---

## 3. Sécurité

| Mesure                                   | Où                                              |
|------------------------------------------|-------------------------------------------------|
| CSP stricte + en-têtes durcis            | `budget_app/middleware.py`                      |
| Cookies de session/CSRF `HttpOnly`       | `gestion_budget/settings.py`                    |
| Limitation des tentatives de connexion (5 échecs → 429 pendant 5 min) | `budget_app/views.ThrottledLoginView` |
| Suppression en `POST` uniquement (405 sur GET)         | `@require_POST` dans `views.py`  |
| Droits : suppression réservée aux administrateurs (403) | `views.supprimer_depense`        |
| Échappement HTML systématique dans l'admin | `format_html` (jamais de HTML brut)             |
| HSTS / cookies sécurisés en production   | `settings.py` (`if not DEBUG`)                  |
| Autorisations réellement appliquées       | `views.permission_requise` (session fermée si refus) |
| Répartition du budget : administrateurs seulement | `views.repartition` (403 explicite)      |
| Numéro de téléphone unique et normalisé  | `budget_app/telephone.py`, `models.ProfilUtilisateur` |
| Mot de passe haché (PBKDF2) + coût constant | `TelephoneBackend` (hérité du `ModelBackend`) |

Tests automatisés :

```bash
python smoke_test.py       # parcours complet : connexion → dépense → suppression → déconnexion
python smoke_security.py   # en-têtes, téléphone, onglets, PWA, autorisations, 405/403, 429
```

---

## 4. Mise en ligne sur un serveur (Oracle Cloud Always Free)

Le déploiement cible une machine Linux (Ubuntu) : le code reste sur GitHub, le
serveur et la base de données n'existent que sur le serveur. **Rien à
installer sur le poste de travail** : un `git push` suffit.

### Première installation

Sur le serveur, une fois le dépôt récupéré :

```bash
cd ~/kendevis
cp .env.example .env
# Renseigner au minimum : SECRET_KEY (nouveau), DEBUG=False, ALLOWED_HOSTS

DOMAINE=ton.domaine.com NOM_UTILISATEUR=ubuntu bash deploy/install.sh
```

Le script installe Python, PostgreSQL, nginx, gunicorn et le certificat HTTPS
gratuit (Let's Encrypt), puis crée la base et l'utilisateur PostgreSQL.

### Créer le compte administrateur en ligne

```bash
cd ~/kendevis
sudo -u ubuntu ./venv/bin/python manage.py creer_admin
```

### Mettre à jour après une modification du code

```bash
git push
ssh ubuntu@ton.ip "cd /home/ubuntu/kendevis && bash deploy/update.sh"
```

`update.sh` sauvegarde la base avant toute migration, applique les migrations,
collecte les fichiers statiques et redémarre le service.

### ⚠️ Sur PythonAnywhere : cliquer sur « Reload »

`deploy/update.sh` redémarre gunicorn, donc rien n'est oublié. Sur
PythonAnywhere, le redémarrage est **manuel** : après un `git pull`, il faut
cliquer sur le bouton vert **Reload** de l'onglet *Web app setup*.

Ce n'est pas une précaution théorique. Avec `DEBUG=False`, Django met les
gabarits en cache dans les processus : un `git pull` seul met bien les
nouveaux fichiers sur le disque, mais les workers servent encore l'ancien
HTML. Symptôme : le code Python est à jour (une commande de gestion
fonctionne), mais l'affichage ne l'est pas.

```bash
# Après un git pull, vérifier que la version servie est bien à jour
git log --oneline -1
grep -c "tabs-nav" budget_app/templates/budget_app/base.html
```

### Sauvegardes

- `deploy/update.sh` dépose une sauvegarde horodatée dans `sauvegardes/`
  avant chaque mise à jour et supprime celles de plus de 30 jours.
- Pour une sauvegarde manuelle :

```bash
cd ~/kendevis
./venv/bin/python manage.py dumpdata --indent 2 > donnees.json
./venv/bin/python manage.py loaddata donnees.json   # restauration
```

---

## 5. Structure du projet

```
gestion_budget/
├── gestion_budget/          # Projet Django (settings, urls)
├── budget_app/
│   ├── models.py            # BudgetMensuel, Depense, CategorieBudget, RepartitionCategorie…
│   ├── views.py             # dashboard, suppression, ThrottledLoginView
│   ├── forms.py             # ConnexionForm (téléphone), DepenseForm, RepartitionForm
│   ├── backends.py          # TelephoneBackend (connexion par téléphone)
│   ├── telephone.py         # Normalisation des numéros
│   ├── couleurs.py          # Palette nommée des catégories (couleurs + dégradés)
│   ├── pwa.py               # Manifeste et service worker
│   ├── middleware.py        # En-têtes de sécurité (CSP, etc.)
│   ├── management/commands/ # creer_admin, changer_mot_de_passe, categoriser_depenses
│   ├── templatetags/        # math_extras (div, mul, abs, ar)
│   ├── templates/           # base, dashboard, depenses, statistiques, repartition, utilisateurs, login
│   └── static/budget_app/   # style.css, pwa_onglets.css, ui.js, pwa.js, sw.js, icons/
├── deploy/                  # install.sh, update.sh (serveur Linux)
├── .env.example             # Modèle de configuration
├── seed_demo.py             # Données de démonstration
├── smoke_test.py            # Tests de parcours
├── smoke_security.py        # Tests de sécurité
└── manage.py
```

---

## 6. Pistes à venir

- Budgets par catégorie (marché, outils, transport…) comme dans le devis.
- Édition d'une dépense existante.
- Multi-langue : français / anglais / malagasy (i18n Django).
- Changer de mot de passe / mot de passe oublié / changer de pseudo.
- Export CSV et graphiques de répartition.
- Envoi de SMS ou appel direct depuis le pied de page.

---

## 7. Installer l'application

Kendevis est une PWA : elle s'installe sur l'écran d'accueil sans passer par
un magasin d'applications.

| Appareil | Procédure |
|---|---|
| Android (Chrome) | menu ⋮ puis **Installer l'application** |
| Ordinateur (Chrome, Edge) | icône d'installation à droite dans la barre d'adresse |
| iPhone (Safari) | bouton **Partager** puis **Sur l'écran d'accueil** |

Un bouton « Installer » apparaît aussi dans la barre de navigation quand le
navigateur juge l'installation possible.

Les icônes sont générées par `tools/generer_icones.py` (encodeur PNG maison,
sans dépendance). Après modification du dessin :

```bash
python tools/generer_icones.py
python manage.py collectstatic --noinput
```
