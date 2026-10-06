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

from budget_app.models import BudgetMensuel, Depense  # noqa: E402

ADMIN_USER, ADMIN_PWD = 'admin', 'admin123'
DEMO_USER, DEMO_PWD = 'utilisateur', 'user1234'


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


def main():
    admin = get_or_create_user(ADMIN_USER, ADMIN_PWD, is_staff=True)
    user = get_or_create_user(DEMO_USER, DEMO_PWD)

    budget, created = BudgetMensuel.objects.get_or_create(
        mois='Octobre 2026',
        defaults={
            'montant_initial': Decimal('3000000.00'),
            'cree_par': admin,
        },
    )
    print(f"Budget {'créé' if created else 'existant'} : {budget}")

    if created:
        lignes = [
            ('Courses au marché', Decimal('45000.00'), 4, user),
            ('Transport - taxi', Decimal('12000.00'), 10, user),
            ('Facture électricité JIRAMA', Decimal('180000.00'), 1, admin),
            ('Loyer', Decimal('800000.00'), 1, admin),
            ('Forfait internet', Decimal('30000.00'), 2, user),
            ('Café et petit-déjeuner', Decimal('8000.00'), 12, user),
        ]
        for designation, prix, quantite, auteur in lignes:
            Depense.objects.create(
                budget=budget,
                utilisateur=auteur,
                date=timezone.now().date(),
                designation=designation,
                prix_unitaire=prix,
                quantite=quantite,
            )
        print(f"{len(lignes)} dépenses de démonstration créées.")

    print(f"\nTotal dépensé : {budget.total_depenses()} Ar")
    print(f"Solde restant : {budget.reste_budget()} Ar")


if __name__ == '__main__':
    main()
