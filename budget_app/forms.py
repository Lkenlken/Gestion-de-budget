from django import forms
from django.contrib.auth.models import User
from .models import BudgetMensuel, Depense


class BudgetMensuelForm(forms.ModelForm):
    """
    Formulaire pour la création/modification d'un budget mensuel.
    Accessible uniquement aux administrateurs.
    """
    class Meta:
        model = BudgetMensuel
        fields = ['mois', 'montant_initial']
        widgets = {
            'mois': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Septembre 2026'
            }),
            'montant_initial': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
        }
        labels = {
            'mois': 'Mois du budget',
            'montant_initial': 'Montant initial (Ar)',
        }


class DepenseForm(forms.ModelForm):
    """
    Formulaire pour l'ajout d'une dépense.
    Accessible à tout utilisateur authentifié.
    Le champ 'budget' et 'utilisateur' sont définis automatiquement dans la vue.
    """
    class Meta:
        model = Depense
        fields = ['date', 'designation', 'prix_unitaire', 'quantite']
        widgets = {
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'designation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Courses, Transport, Facture électricité...'
            }),
            'prix_unitaire': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'id': 'id_prix_unitaire'
            }),
            'quantite': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'value': '1',
                'id': 'id_quantite'
            }),
        }
        labels = {
            'date': 'Date',
            'designation': 'Désignation',
            'prix_unitaire': 'Prix unitaire (Ar)',
            'quantite': 'Quantité',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Définir la date du jour par défaut
        from django.utils import timezone
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now().date()