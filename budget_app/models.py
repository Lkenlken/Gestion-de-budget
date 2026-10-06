from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class BudgetMensuel(models.Model):
    """
    Modèle représentant un budget mensuel.
    Seul un administrateur (is_staff=True) peut créer, modifier ou supprimer un budget.
    """
    mois = models.CharField(
        max_length=50,
        verbose_name="Mois",
        help_text="Ex: Septembre 2026"
    )
    montant_initial = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Montant initial du budget",
        help_text="Montant total alloué pour le mois"
    )
    cree_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='budgets_crees',
        verbose_name="Créé par"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )

    class Meta:
        verbose_name = "Budget Mensuel"
        verbose_name_plural = "Budgets Mensuels"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['mois'],
                name='unique_budget_per_month'
            )
        ]

    def __str__(self):
        return f"{self.mois} - {self.montant_initial:,.2f} Ar".replace(',', ' ')

    def total_depenses(self):
        """
        Retourne la somme totale des dépenses associées à ce budget.
        """
        total = self.depenses.aggregate(
            total=models.Sum(
                models.F('prix_unitaire') * models.F('quantite'),
                output_field=models.DecimalField(max_digits=12, decimal_places=2)
            )
        )['total']
        return total if total else 0

    def reste_budget(self):
        """
        Retourne le solde restant (montant_initial - total_dépenses).
        """
        return self.montant_initial - self.total_depenses()

    def est_en_alerte(self):
        """
        Retourne True si le solde restant est négatif.
        """
        return self.reste_budget() < 0


class Depense(models.Model):
    """
    Modèle représentant une dépense individuelle.
    Chaque utilisateur authentifié peut ajouter une dépense.
    Seul un administrateur peut modifier ou supprimer une dépense.
    """
    budget = models.ForeignKey(
        BudgetMensuel,
        on_delete=models.CASCADE,
        related_name='depenses',
        verbose_name="Budget mensuel"
    )
    utilisateur = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='depenses',
        verbose_name="Utilisateur"
    )
    date = models.DateField(
        default=timezone.now,
        verbose_name="Date de la dépense"
    )
    designation = models.CharField(
        max_length=255,
        verbose_name="Désignation",
        help_text="Description de la dépense"
    )
    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix unitaire",
        help_text="Prix à l'unité"
    )
    quantite = models.PositiveIntegerField(
        default=1,
        verbose_name="Quantité"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'enregistrement"
    )

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.designation} - {self.montant_total:,.2f} Ar".replace(',', ' ')

    @property
    def montant_total(self):
        """
        Retourne le montant total de la ligne (prix_unitaire * quantite).
        """
        return self.prix_unitaire * self.quantite


class PermissionUtilisateur(models.Model):
    """
    Autorisations d'accès d'un utilisateur de l'application.

    Deux cases à cocher, modifiables par l'administrateur depuis le tableau
    de l'administration :

      * « Lecture »  : peut consulter le tableau de bord et l'historique.
      * « Écriture » : en plus, peut ajouter de nouvelles dépenses.

    Un utilisateur ne peut JAMAIS modifier ni supprimer une dépense déjà
    enregistrée : seule la suppression par un administrateur est possible.
    """
    utilisateur = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='permission_budget',
        verbose_name="Utilisateur",
    )
    peut_lire = models.BooleanField(
        default=True,
        verbose_name="Lecture",
        help_text="Peut consulter le tableau de bord et les dépenses.",
    )
    peut_ecrire = models.BooleanField(
        default=False,
        verbose_name="Écriture",
        help_text="Peut ajouter de nouvelles dépenses (aucune modification possible).",
    )
    modifie_par = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='permissions_accordees',
        verbose_name="Accordée par",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière modification",
    )

    class Meta:
        verbose_name = "Autorisation d'accès"
        verbose_name_plural = "Autorisations d'accès (lecture / écriture)"
        ordering = ['utilisateur__username']

    def __str__(self):
        return f"{self.utilisateur.username} — {'lecture+écriture' if self.peut_ecrire else 'lecture seule' if self.peut_lire else 'aucun accès'}"

    @property
    def statut(self):
        """Libellé court du niveau d'accès, utilisé dans les tableaux."""
        if self.peut_ecrire:
            return "Lecture + écriture"
        if self.peut_lire:
            return "Lecture seule"
        return "Aucun accès"


def permission_de(utilisateur):
    """
    Retourne (en la créant si nécessaire) l'autorisation d'un utilisateur.

    Par défaut : un utilisateur classique a le droit de lecture, un
    administrateur (is_staff) a lecture + écriture.
    """
    if not utilisateur or not utilisateur.is_authenticated:
        return None
    permission, _ = PermissionUtilisateur.objects.get_or_create(
        utilisateur=utilisateur,
        defaults={
            'peut_lire': True,
            'peut_ecrire': utilisateur.is_staff,
        },
    )
    return permission