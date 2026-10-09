from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import (
    BudgetMensuel,
    CategorieBudget,
    Depense,
    PermissionUtilisateur,
    ProfilUtilisateur,
    RepartitionCategorie,
)
from .forms import CategorieBudgetForm, ProfilUtilisateurForm
from .telephone import normaliser_telephone


class RepartitionCategorieInline(admin.TabularInline):
    """
    Répartition du budget par catégorie, modifiable directement depuis la
    fiche d'un budget mensuel.
    """

    model = RepartitionCategorie
    extra = 1
    fields = ['categorie', 'montant', 'notes']
    autocomplete_fields = ['categorie']
    verbose_name = "Part allouée"
    verbose_name_plural = "Parts allouées par catégorie"


@admin.register(BudgetMensuel)
class BudgetMensuelAdmin(admin.ModelAdmin):
    inlines = [RepartitionCategorieInline]
    list_display = ['mois', 'montant_initial', 'total_alloue_display',
                    'cree_par', 'created_at', 'total_depenses_display',
                    'reste_budget_display', 'est_en_alerte']
    list_filter = ['created_at', 'cree_par']
    search_fields = ['mois']
    readonly_fields = ['created_at', 'total_alloue_display', 'ecart_display']
    fields = ['mois', 'montant_initial', 'total_alloue_display',
              'ecart_display', 'cree_par', 'created_at']
    ordering = ['-created_at']

    @admin.display(description="Total réparti")
    def total_alloue_display(self, obj):
        return f"{obj.total_repartition():,.2f} Ar".replace(',', ' ')

    @admin.display(description="Écart")
    def ecart_display(self, obj):
        if not obj.pk:
            return '—'
        ecart = obj.ecart_repartition()
        if ecart == 0:
            return format_html('<span style="color:#198754;">Répartition complète</span>')
        if not obj.repartitions.exists():
            return format_html('<span style="color:#dc3545;">Aucune répartition</span>')
        signe = 'manquant' if ecart > 0 else 'en trop'
        return format_html(
            '<span style="color:#dc3545;">{:.2f} Ar {}</span>',
            abs(ecart), signe,
        )

    def total_depenses_display(self, obj):
        total = obj.total_depenses()
        return f"{total:,.2f} Ar".replace(',', ' ')

    @admin.display(description='Solde Restant')
    def reste_budget_display(self, obj):
        reste = obj.reste_budget()
        color = '#198754' if reste >= 0 else '#dc3545'
        # format_html échappe les valeurs puis concatène : pas d'injection HTML.
        # Le montant est formaté avant d'être transmis (le ":.2f" ne s'applique
        # pas aux chaînes déjà échappées).
        return format_html(
            '<strong style="color: {};">{} Ar</strong>', color,
            f"{reste:,.2f}".replace(',', ' '),
        )

    @admin.display(boolean=True, description='Alerte (Solde < 0)')
    def est_en_alerte(self, obj):
        return obj.est_en_alerte()


class ProfilUtilisateurInline(admin.StackedInline):
    """
    Le numéro de téléphone est modifiable directement depuis la fiche d'un
    utilisateur, sans quitter l'administration Django.
    """

    model = ProfilUtilisateur
    form = ProfilUtilisateurForm
    can_delete = False
    verbose_name = "Téléphone (identifiant de connexion)"
    verbose_name_plural = "Téléphone (identifiant de connexion)"
    extra = 0
    fields = ['telephone', 'fonction']

    def has_add_permission(self, request, obj=None):
        # Un seul profil par utilisateur (OneToOne) : on ne propose le
        # formulaire d'ajout que si le profil n'existe pas encore.
        return obj is None or not hasattr(obj, 'profil')

    def has_change_permission(self, request, obj=None):
        return True


class UtilisateurAdmin(UserAdmin):
    """Administration des comptes, avec le numéro de téléphone en clair."""

    inlines = [ProfilUtilisateurInline]
    list_display = [
        'username', 'telephone_affiche', 'first_name', 'last_name',
        'email', 'is_staff', 'is_active',
    ]
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'profil__telephone']

    @admin.display(description='Téléphone', ordering='profil__telephone')
    def telephone_affiche(self, obj):
        return format_html('<strong>{}</strong>', obj.profil.telephone_affiche) \
            if hasattr(obj, 'profil') else '—'


admin.site.unregister(User)
admin.site.register(User, UtilisateurAdmin)


@admin.register(ProfilUtilisateur)
class ProfilUtilisateurAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'telephone', 'telephone_affiche', 'fonction', 'updated_at']
    search_fields = ['utilisateur__username', 'telephone']
    raw_id_fields = ['utilisateur']
    readonly_fields = ['created_at', 'updated_at']

    @admin.display(description='Téléphone formaté')
    def telephone_affiche(self, obj):
        return obj.telephone_affiche


@admin.register(CategorieBudget)
class CategorieBudgetAdmin(admin.ModelAdmin):
    """
    Postes de dépense : courses, provisions, transport...

    Les catégories sont définies une fois et réutilisées sur tous les mois.
    Leur suppression est protégée s'il y a déjà des données rattachées.
    """

    list_display = ['nom', 'icone', 'couleur_apercu', 'ordre', 'active',
                    'nombre_repartitions', 'nombre_depenses']
    list_editable = ['ordre', 'active']
    search_fields = ['nom']
    ordering = ['ordre', 'nom']
    form = CategorieBudgetForm
    change_form_template = 'admin/categoriebudget/change_form.html'

    @admin.display(description='Couleur')
    def couleur_apercu(self, obj):
        return format_html(
            '<span style="display:inline-block;width:2.2rem;height:1.1rem;'
            'border-radius:4px;border:1px solid rgba(128,128,128,.4);'
            'background:{};"></span> {}',
            obj.fond, obj.nom_couleur,
        )

    @admin.display(description='Répartitions')
    def nombre_repartitions(self, obj):
        return obj.repartitions.count()

    @admin.display(description='Dépenses')
    def nombre_depenses(self, obj):
        return obj.depenses.count()

    def has_delete_permission(self, request, obj=None):
        # Supprimer une catégorie Effacerait silencieusement l'historique :
        # on préfère renvoyer vers « Active = non ».
        if obj is not None and (obj.repartitions.exists() or obj.depenses.exists()):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(RepartitionCategorie)
class RepartitionCategorieAdmin(admin.ModelAdmin):
    list_display = ['budget', 'categorie', 'montant', 'total_depense_display',
                    'reste_display']
    list_filter = ['budget', 'categorie']
    search_fields = ['budget__mois', 'categorie__nom']
    autocomplete_fields = ['budget', 'categorie']

    @admin.display(description='Dépensé')
    def total_depense_display(self, obj):
        return f"{obj.total_depense():,.2f} Ar".replace(',', ' ')

    @admin.display(description='Reste')
    def reste_display(self, obj):
        reste = obj.reste()
        couleur = '#198754' if reste >= 0 else '#dc3545'
        return format_html(
            '<strong style="color: {};">{:.2f} Ar</strong>', couleur, reste,
        )


@admin.register(PermissionUtilisateur)
class PermissionUtilisateurAdmin(admin.ModelAdmin):
    """
    Autorisations lecture / écriture de chaque utilisateur, modifiables
    par un administrateur depuis cette page.
    """

    list_display = ['utilisateur', 'statut', 'peut_lire', 'peut_ecrire', 'modifie_par', 'updated_at']
    list_editable = ['peut_lire', 'peut_ecrire']
    list_filter = ['peut_lire', 'peut_ecrire']
    search_fields = ['utilisateur__username', 'utilisateur__profil__telephone']
    raw_id_fields = ['utilisateur', 'modifie_par']
    readonly_fields = ['updated_at']


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    autocomplete_fields = ['categorie']
    list_display = ['designation', 'budget', 'categorie', 'utilisateur', 'date',
                    'prix_unitaire', 'quantite', 'montant_total_display', 'created_at']
    list_filter = ['budget', 'categorie', 'utilisateur', 'date', 'created_at']
    search_fields = ['designation', 'budget__mois', 'utilisateur__username',
                     'utilisateur__profil__telephone', 'categorie__nom']
    readonly_fields = ['created_at']
    ordering = ['-date', '-created_at']
    date_hierarchy = 'date'

    def montant_total_display(self, obj):
        return format_html('<strong>{} Ar</strong>',
                           f"{obj.montant_total:,.2f}".replace(',', ' '))
    montant_total_display.short_description = 'Montant Total'