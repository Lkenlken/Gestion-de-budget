from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import BudgetMensuel, Depense, PermissionUtilisateur, ProfilUtilisateur
from .forms import ProfilUtilisateurForm
from .telephone import normaliser_telephone


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


@admin.register(BudgetMensuel)
class BudgetMensuelAdmin(admin.ModelAdmin):
    list_display = ['mois', 'montant_initial', 'cree_par', 'created_at', 'total_depenses_display', 'reste_budget_display', 'est_en_alerte']
    list_filter = ['created_at', 'cree_par']
    search_fields = ['mois']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

    def total_depenses_display(self, obj):
        total = obj.total_depenses()
        return f"{total:,.2f} Ar".replace(',', ' ')
    total_depenses_display.short_description = 'Total Dépenses'

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
    reste_budget_display.short_description = 'Solde Restant'

    def est_en_alerte(self, obj):
        return obj.est_en_alerte()
    est_en_alerte.boolean = True
    est_en_alerte.short_description = 'Alerte (Solde < 0)'


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = ['designation', 'budget', 'utilisateur', 'date', 'prix_unitaire', 'quantite', 'montant_total_display', 'created_at']
    list_filter = ['budget', 'utilisateur', 'date', 'created_at']
    search_fields = ['designation', 'budget__mois', 'utilisateur__username', 'utilisateur__profil__telephone']
    readonly_fields = ['created_at']
    ordering = ['-date', '-created_at']
    date_hierarchy = 'date'

    def montant_total_display(self, obj):
        return format_html('<strong>{} Ar</strong>',
                           f"{obj.montant_total:,.2f}".replace(',', ' '))
    montant_total_display.short_description = 'Montant Total'