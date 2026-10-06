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

# Données de démonstration (budget Octobre 2026 + 6 dépenses)
python seed_demo.py

# Lancer le serveur
python manage.py runserver
```

L'application est ensuite accessible sur <http://127.0.0.1:8000/>.

### Comptes de démonstration

| Compte       | Identifiant    | Mot de passe | Rôle                                  |
|--------------|----------------|--------------|---------------------------------------|
| Admin        | `admin`        | `admin123`   | Crée/supprime les budgets, supprime les dépenses |
| Utilisateur  | `utilisateur`  | `user1234`   | Consulte et ajoute des dépenses       |

> ⚠️ En production : changez ces mots de passe, générez une vraie `SECRET_KEY`
> dans `.env`, passez `DEBUG=False` et servez l'application en HTTPS.

---

## 2. Fonctionnalités

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

Tests automatisés :

```bash
python smoke_test.py       # parcours complet : connexion → dépense → suppression → déconnexion
python smoke_security.py   # en-têtes, droits, 405/403, blocage 429, administration
```

---

## 4. Structure du projet

```
gestion_budget/
├── gestion_budget/          # Projet Django (settings, urls)
├── budget_app/
│   ├── models.py            # BudgetMensuel, Depense
│   ├── views.py             # dashboard, suppression, ThrottledLoginView
│   ├── forms.py             # BudgetMensuelForm, DepenseForm
│   ├── middleware.py        # En-têtes de sécurité (CSP, etc.)
│   ├── templatetags/        # math_extras (div, mul, abs, ar)
│   ├── templates/           # base, dashboard, login
│   └── static/budget_app/   # style.css, ui.js, budget_realtime.js
├── seed_demo.py             # Données de démonstration
├── smoke_test.py            # Tests de parcours
├── smoke_security.py        # Tests de sécurité
└── manage.py
```

---

## 5. Pistes à venir

- Budgets par catégorie (marché, outils, transport…) comme dans le devis.
- Édition d'une dépense existante.
- Multi-langue : français / anglais / malagasy (i18n Django).
- Changer de mot de passe / mot de passe oublié / changer de pseudo.
- Export CSV et graphiques de répartition.
- Envoi de SMS ou appel direct depuis le pied de page.
