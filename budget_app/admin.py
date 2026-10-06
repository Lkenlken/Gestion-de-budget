from django.contrib import admin
from django.utils.html import format_html

from .models import BudgetMensuel, Depense


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
    search_fields = ['designation', 'budget__mois', 'utilisateur__username']
    readonly_fields = ['created_at']
    ordering = ['-date', '-created_at']
    date_hierarchy = 'date'

    def montant_total_display(self, obj):
        return format_html('<strong>{} Ar</strong>',
                           f"{obj.montant_total:,.2f}".replace(',', ' '))
    montant_total_display.short_description = 'Montant Total'