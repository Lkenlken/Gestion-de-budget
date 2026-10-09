from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal

from .couleurs import (
    DEGRADES,
    COULEURS,
    COULEUR_PAR_DEFAUT,
    couleur_connue,
    fond as fond_css,
    libelle as libelle_couleur,
    rgba as rgba_couleur,
    texte_lisible,
    teinte_debut,
)

from .telephone import formater_telephone, normaliser_telephone


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

    # --- Répartition par catégorie -------------------------------------

    def total_repartition(self):
        """Somme des montants répartis par catégorie pour ce budget."""
        return self.repartitions.aggregate(
            total=models.Sum('montant')
        )['total'] or Decimal('0.00')

    def repartition_incomplete(self):
        """
        Retourne True si le budget n'est pas (encore) réparti, ou si la
        répartition ne tombe pas juste sur le montant initial.

        Tant que c'est le cas, les indicateurs par catégorie n'ont pas de sens :
        l'interface affiche alors une invitation à les renseigner.
        """
        if not self.repartitions.exists():
            return True
        return self.total_repartition() != self.montant_initial

    def ecart_repartition(self):
        """Différence entre le montant initial et la somme des répartitions."""
        return self.montant_initial - self.total_repartition()

    def categorie_depense(self, categorie):
        """Montant dépensé dans une catégorie donnée pour ce budget."""
        total = self.depenses.filter(categorie=categorie).aggregate(
            total=models.Sum(
                models.F('prix_unitaire') * models.F('quantite'),
                output_field=models.DecimalField(max_digits=14, decimal_places=2),
            )
        )['total']
        return total if total is not None else Decimal('0.00')

    def resume_categories(self):
        """
        Renvoie la liste des catégories actives avec, pour chacune, le montant
        alloué, le montant dépensé et le solde restant. Une catégorie sans
        répartition est tout de même présente (montant alloué à zéro) afin que
        l'utilisateur voie qu'il peut l'utiliser.
        """
        alloue = {
            ligne.categorie_id: ligne
            for ligne in self.repartitions.select_related('categorie')
        }
        depense = dict(
            self.depenses
            .exclude(categorie=None)
            .values_list('categorie_id')
            .annotate(total=models.Sum(
                models.F('prix_unitaire') * models.F('quantite'),
                output_field=models.DecimalField(max_digits=14, decimal_places=2),
            ))
        )

        resume = []
        for categorie in CategorieBudget.objects.filter(active=True):
            ligne = alloue.get(categorie.pk)
            montant_alloue = ligne.montant if ligne else Decimal('0.00')
            montant_depense = depense.get(categorie.pk) or Decimal('0.00')
            resume.append({
                'categorie': categorie,
                'ligne': ligne,
                'alloue': montant_alloue,
                'depense': montant_depense,
                'reste': montant_alloue - montant_depense,
                'pourcentage': (
                    (montant_depense / montant_alloue * 100)
                    if montant_alloue else Decimal('0.00')
                ),
                'taux': (
                    min(100, float(montant_depense / montant_alloue * 100))
                    if montant_alloue else 0.0
                ),
            })
        return resume


class CategorieBudget(models.Model):
    """
    Un poste de dépense (« Courses », « Provisions », « Transport »...).

    Les catégories sont transversales : elles sont définies une seule fois par
    l'administrateur puis réutilisées sur tous les mois. Elles servent à la
    fois à répartir le budget initial et à rattacher les dépenses réelles.
    """

    nom = models.CharField(max_length=80, unique=True, verbose_name="Nom de la catégorie")
    icone = models.CharField(
        max_length=40, default='bi-tag', blank=True,
        verbose_name="Icône",
        help_text="Nom d'icône Bootstrap Icons, ex : bi-basket2, bi-box-seam.",
    )
    couleur = models.CharField(
        max_length=30, default=COULEUR_PAR_DEFAUT,
        verbose_name="Couleur",
        help_text="Choisir une couleur ou un dégradé dans la liste.",
    )
    ordre = models.PositiveSmallIntegerField(
        default=0, verbose_name="Ordre d'affichage",
        help_text="Les valeurs les plus basses apparaissent en premier.",
    )
    active = models.BooleanField(
        default=True, verbose_name="Active",
        help_text="Décochez pour masquer la catégorie sans effacer l'historique.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Catégorie de budget"
        verbose_name_plural = "Catégories de budget"
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        # La valeur enregistrée est toujours un nom connu de la palette :
        # une saisie hors liste ne peut pas rendre une catégorie invisible.
        self.couleur = couleur_connue(self.couleur)
        return super().save(*args, **kwargs)

    # --- Couleur ------------------------------------------------------
    # Ces quatre propriétés traduisent le nom stocké (« bleu-degrade ») en
    # ce que les gabarins savent manipuler : un libellé lisible, un aplat CSS,
    # une version translucide et une couleur de texte contrastée.

    @property
    def nom_couleur(self):
        return libelle_couleur(self.couleur)

    @property
    def fond(self):
        return fond_css(self.couleur)

    @property
    def teinte(self):
        return teinte_debut(self.couleur)

    @property
    def fond_doux(self):
        return rgba_couleur(self.couleur, 0.14)

    @property
    def texte_sur_fond(self):
        return texte_lisible(self.couleur)

    @property
    def est_degrade(self):
        return couleur_connue(self.couleur) in DEGRADES

    @property
    def total_alloue(self):
        """Somme des montants alloués à cette catégorie, tous mois confondus."""
        return sum((ligne.montant for ligne in self.repartitions.all()), Decimal('0.00'))


class RepartitionCategorie(models.Model):
    """
    Part d'un budget mensuel fixée à une catégorie.

    Exemple : pour Octobre 2026 et un budget initial de 250 000 Ar,
        Courses     → 100 000 Ar
        Provisions  → 150 000 Ar

    La somme des lignes doit être égale au montant initial du budget : c'est
    vérifié par `BudgetMensuel.verifier_repartition()`.
    """

    budget = models.ForeignKey(
        BudgetMensuel,
        on_delete=models.CASCADE,
        related_name='repartitions',
        verbose_name="Budget mensuel",
    )
    categorie = models.ForeignKey(
        CategorieBudget,
        on_delete=models.CASCADE,
        related_name='repartitions',
        verbose_name="Catégorie",
    )
    montant = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Montant alloué (Ar)",
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name="Précision")

    class Meta:
        verbose_name = "Répartition par catégorie"
        verbose_name_plural = "Répartition par catégorie"
        ordering = ['categorie__ordre', 'categorie__nom']
        constraints = [
            models.UniqueConstraint(
                fields=['budget', 'categorie'],
                name='unique_repartition_par_categorie',
            )
        ]

    def __str__(self):
        return f"{self.categorie.nom} — {self.montant:,.2f} Ar".replace(',', ' ')

    def total_depense(self):
        """Montant réellement dépensé dans cette catégorie pour ce budget."""
        total = self.budget.depenses.filter(categorie=self.categorie).aggregate(
            total=models.Sum(
                models.F('prix_unitaire') * models.F('quantite'),
                output_field=models.DecimalField(max_digits=14, decimal_places=2),
            )
        )['total']
        return total if total is not None else Decimal('0.00')

    def reste(self):
        return self.montant - self.total_depense()


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
    categorie = models.ForeignKey(
        CategorieBudget,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='depenses',
        verbose_name="Catégorie",
        help_text="Poste de rattachement (courses, provisions...).",
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


class ProfilUtilisateur(models.Model):
    """
    Informations complémentaires d'un compte : son numéro de téléphone.

    Le numéro est l'identifiant de connexion de l'application (à la place
    du nom d'utilisateur). Il est stocké au format E.164 — `0384160133`
    devient `+261384160133` — quel que soit la façon dont il a été saisi,
    ce qui garantit qu'un même utilisateur ne peut pas être dupliqué.

    Related name : `user.profil`
    """

    utilisateur = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profil',
        verbose_name="Utilisateur",
    )
    telephone = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Téléphone",
        help_text="Numéro utilisé pour se connecter. Ex : 0384160133",
    )
    fonction = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Fonction",
        help_text="Facultatif : rôle dans l'association.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"
        ordering = ['utilisateur__username']

    def __str__(self):
        return f"{self.utilisateur} — {self.telephone_affiche}"

    def clean(self):
        from django.core.exceptions import ValidationError

        numero = normaliser_telephone(self.telephone)
        if not numero:
            raise ValidationError({'telephone': "Le numéro de téléphone est obligatoire."})

        doublon = (
            ProfilUtilisateur.objects.filter(telephone=numero)
            .exclude(pk=self.pk)
            .first()
        )
        if doublon:
            raise ValidationError({
                'telephone': f"Ce numéro est déjà utilisé par « {doublon.utilisateur} »."
            })
        self.telephone = numero

    def save(self, *args, **kwargs):
        # La normalisation est appliquée à l'écriture : impossible de
        # enregistrer le même numéro sous deux écritures différentes.
        self.telephone = normaliser_telephone(self.telephone)
        return super().save(*args, **kwargs)

    @property
    def telephone_affiche(self):
        """Numéro formaté pour la lecture : `038 41 601 33`."""
        return formater_telephone(self.telephone)


def creer_profil(utilisateur, telephone, fonction=''):
    """
    Crée (ou met à jour) le profil téléphonique d'un utilisateur et
    retourne le `ProfilUtilisateur` correspondant.
    """
    numero = normaliser_telephone(telephone)
    if not numero:
        raise ValueError("Numéro de téléphone vide.")

    profil, created = ProfilUtilisateur.objects.update_or_create(
        utilisateur=utilisateur,
        defaults={'telephone': numero, 'fonction': fonction or ''},
    )
    return profil, created


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


def telephone_de(utilisateur):
    """
    Retourne le numéro de téléphone d'un utilisateur, formaté pour la
    lecture (`038 41 601 33`), ou une chaîne vide s'il n'a pas encore de
    profil renseigné.
    """
    profil = getattr(utilisateur, 'profil', None)
    return profil.telephone_affiche if profil else ''


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