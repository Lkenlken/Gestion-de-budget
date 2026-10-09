"""
Script de création de données de démonstration.

Usage :
    python seed_demo.py
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_budget.settings')
django.setup()

from decimal import Decimal  # noqa: E402

from django.contrib.auth.models import User  # noqa: E402
from django.utils import timezone  # noqa: E402

from budget_app.models import BudgetMensuel, CategorieBudget, Depense, RepartitionCategorie

ADMIN_USER, ADMIN_PWD = 'admin', 'admin123'
DEMO_USER, DEMO_PWD = 'utilisateur', 'user1234'

# Catégories de démonstration : les postes proposés à l'administrateur.
CATEGORIES_DEMO = [
    ('Courses', 'bi-basket2', '#16a34a', 1),
    ('Provisions', 'bi-box-seam', '#f59e0b', 2),
    ('Transport', 'bi-bus-front', '#0ea5e9', 3),
]

# Répartition du budget de démonstration (250 000 Ar au total).
REPARTITION_DEMO = {
    'Courses': Decimal('100000.00'),
    'Provisions': Decimal('110000.00'),
    'Transport': Decimal('40000.00'),
}


def get_or_create_user(username, password, is_staff=False):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'is_staff': is_staff, 'is_superuser': is_staff},
    )
    if created:
        user.set_password(password)
        user.save()
        print(f"Utilisateur créé : {username} / {password}")
    else:
        print(f"Utilisateur existant : {username}")
    return user


def creer_categories():
    """Crée les catégories de démonstration si elles n'existent pas encore."""
    categories = {}
    for nom, icone, couleur, ordre in CATEGORIES_DEMO:
        categorie, created = CategorieBudget.objects.get_or_create(
            nom=nom,
            defaults={'icone': icone, 'couleur': couleur, 'ordre': ordre},
        )
        categories[nom] = categorie
        if created:
            print(f"Catégorie créée : {nom}")
    return categories


def main():
    admin = get_or_create_user(ADMIN_USER, ADMIN_PWD, is_staff=True)
    user = get_or_create_user(DEMO_USER, DEMO_PWD)

    categories = creer_categories()

    budget, created = BudgetMensuel.objects.get_or_create(
        mois='Octobre 2026',
        defaults={
            'montant_initial': Decimal('250000.00'),
            'cree_par': admin,
        },
    )
    print(f"Budget {'créé' if created else 'existant'} : {budget}")

    if created:
        # Répartition : la somme doit être exactement le budget initial.
        for nom, montant in REPARTITION_DEMO.items():
            RepartitionCategorie.objects.update_or_create(
                budget=budget,
                categorie=categories[nom],
                defaults={'montant': montant},
            )
        print(f"Répartition : {budget.total_repartition():,.2f} Ar".replace(',', ' '))

        lignes = [
            ('Courses au marché', Decimal('45000.00'), 4, user, 'Courses'),
            ('Transport - taxi', Decimal('12000.00'), 10, user, 'Transport'),
            ('Facture électricité JIRAMA', Decimal('180000.00'), 1, admin, 'Provisions'),
            ('Loyer', Decimal('800000.00'), 1, admin, 'Provisions'),
            ('Forfait internet', Decimal('30000.00'), 2, user, 'Provisions'),
            ('Café et petit-déjeuner', Decimal('8000.00'), 12, user, 'Courses'),
        ]
        for designation, prix, quantite, auteur, poste in lignes:
            Depense.objects.create(
                budget=budget,
                utilisateur=auteur,
                categorie=categories[poste],
                date=timezone.now().date(),
                designation=designation,
                prix_unitaire=prix,
                quantite=quantite,
            )
        print(f"{len(lignes)} dépenses de démonstration créées.")

    print(f"\nTotal dépensé : {budget.total_depenses():,.2f} Ar".replace(',', ' '))
    print(f"Solde restant : {budget.reste_budget():,.2f} Ar".replace(',', ' '))
    print("\nSuivi par catégorie :")
    for ligne in budget.resume_categories():
        etat = 'OK' if ligne['reste'] >= 0 else 'DÉPASSÉ'
        print(
            f"  {ligne['categorie'].nom:14} "
            f"{ligne['depense']:>12,.2f} / {ligne['alloue']:>12,.2f} Ar  {etat}".replace(',', ' ')
        )


if __name__ == '__main__':
    main()
