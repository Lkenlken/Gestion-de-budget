from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import BudgetMensuel, Depense, ProfilUtilisateur
from .telephone import normaliser_telephone


class ConnexionForm(AuthenticationForm):
    """
    Formulaire de connexion de l'application.

    L'identifiant est le **numéro de téléphone** de l'utilisateur ; le champ
    `username` du formulaire Django standard est donc retiré. Le reste du
    comportement de sécurité est inchangé (vérification du mot de passe avec
    PBKDF2, contrôle d'activité du compte, etc.) : on s'appuie sur
    `AuthenticationForm` plutôt que sur un formulaire maison.
    """

    telephone = forms.CharField(
        label="Téléphone",
        max_length=25,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex : 0384160133',
            'autocomplete': 'username',
            'inputmode': 'tel',
            'autofocus': True,
        }),
    )
    # Champ technique : `AuthenticationForm.__init__` règle sa longueur sur
    # le champ « username » du modèle. Il doit donc exister le temps de
    # l'initialisation, puis il est retiré (voir `__init__`). Il n'est jamais
    # lu ni enregistré : seul le numéro de téléphone compte.
    username = forms.CharField(required=False, widget=forms.HiddenInput)

    error_messages = {
        'invalid_login': "Numéro de téléphone ou mot de passe incorrect.",
        'inactive': "Ce compte est désactivé.",
    }

    def __init__(self, request=None, *args, **kwargs):
        # `AuthenticationForm.__init__` règle `max_length` sur le champ
        # `username` du modèle : ce champ n'existe plus ici. On supprime donc
        # le réglage de longueur et on applique la nôtre au téléphone.
        super().__init__(request, *args, **kwargs)
        if 'username' in self.fields:  # prudence (Django peut l'ajouter)
            del self.fields['username']
        self.fields['telephone'].max_length = 25

    def clean_telephone(self):
        numero = normaliser_telephone(self.cleaned_data.get('telephone'))
        if not numero:
            raise forms.ValidationError("Saisissez un numéro de téléphone valide.")
        return numero

    def clean(self):
        numero = self.cleaned_data.get('telephone')
        mot_de_passe = self.cleaned_data.get('password')

        if numero and mot_de_passe:
            self.user_cache = authenticate(
                self.request, telephone=numero, password=mot_de_passe
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            # Refuse les comptes désactivés ou explicitement exclus.
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class ProfilUtilisateurForm(forms.ModelForm):
    """
    Formulaire d'édition du profil (numéro de téléphone) d'un utilisateur.
    Utilisé par l'administration Django.
    """

    class Meta:
        model = ProfilUtilisateur
        fields = ['telephone', 'fonction']
        widgets = {
            'telephone': forms.TextInput(attrs={
                'class': 'vTextField',
                'placeholder': 'Ex : 0384160133',
                'inputmode': 'tel',
            }),
            'fonction': forms.TextInput(attrs={'class': 'vTextField'}),
        }
        labels = {
            'telephone': 'Téléphone',
            'fonction': 'Fonction',
        }


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