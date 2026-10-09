from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from decimal import Decimal

from .couleurs import (
    COULEURS,
    COULEUR_PAR_DEFAUT,
    DEGRADES,
    ORDRE_COULEURS,
    ORDRE_DEGRADES,
    fond as fond_css,
    teinte_debut,
)
from .models import (
    BudgetMensuel,
    CategorieBudget,
    Depense,
    ProfilUtilisateur,
)
from .telephone import normaliser_telephone


class CouleurSelect(forms.Select):
    """
    Liste déroulante de couleurs, choisie par son nom.

    Chaque option affiche un carré de la couleur réelle : on ne demande pas à
    l'utilisateur de connaître un code hexadécimal.

    Seul le gabarit des *options* est personnalisé. Le gabarit principal reste
    celui de Django, qui gère correctement les groupes (`<optgroup>`) — et les
    autres menus déroulants de l'administration ne sont pas affectés.
    """

    option_template_name = 'admin/widgets/couleur_option.html'

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        """Ajoute la valeur CSS et la teinte à chaque option du menu."""
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        option['fond'] = fond_css(value)
        option['teinte'] = teinte_debut(value)
        return option


class CategorieBudgetForm(forms.ModelForm):
    """Formulaire d'administration d'une catégorie de budget."""

    class Meta:
        model = CategorieBudget
        fields = ['nom', 'icone', 'couleur', 'ordre', 'active']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'vTextField',
                'placeholder': 'Ex : Courses',
            }),
            'icone': forms.TextInput(attrs={
                'class': 'vTextField',
                'placeholder': 'Ex : bi-basket2',
            }),
            'ordre': forms.NumberInput(attrs={
                'class': 'vSmallPositiveIntegerField',
            }),
            # Choix regroupés : couleurs simples d'abord, dégradés ensuite.
            'couleur': CouleurSelect(
                choices=(
                    ('Couleurs', [
                        (nom, COULEURS[nom][0]) for nom in ORDRE_COULEURS
                    ]),
                    ('Dégradés', [
                        (nom, DEGRADES[nom][0]) for nom in ORDRE_DEGRADES
                    ]),
                ),
                attrs={'class': 'vSelect'},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['couleur'].help_text = (
            "La couleur choisie colore la barre de progression et la pastille "
            "de la catégorie dans toute l'application."
        )


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
        fields = ['date', 'designation', 'prix_unitaire', 'quantite', 'categorie']
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
            'categorie': forms.Select(attrs={
                'class': 'form-select',
            }),
        }
        labels = {
            'date': 'Date',
            'designation': 'Désignation',
            'prix_unitaire': 'Prix unitaire (Ar)',
            'quantite': 'Quantité',
            'categorie': 'Catégorie',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Définir la date du jour par défaut
        from django.utils import timezone
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now().date()
        # Seules les catégories actives sont proposées, dans l'ordre choisi
        # par l'administrateur.
        self.fields['categorie'].queryset = CategorieBudget.objects.filter(
            active=True
        ).order_by('ordre', 'nom')
        self.fields['categorie'].required = False
        self.fields['categorie'].empty_label = '— Non catégorisée —'

        # Catégorie actuellement choisie, que la saisie vienne d'un POST
        # (formulaire renvoyé avec une erreur) ou de la base.
        if self.is_bound:
            actuel = self.data.get(self.add_prefix('categorie')) or ''
        elif self.instance.pk:
            actuel = self.instance.categorie_id or ''
        else:
            actuel = ''

        # Liste des catégories présentées sous forme de boutons colorés plutôt
        # que d'un menu déroulant : il y a peu de postes, et les voir tous
        # d'un coup évite d'ouvrir une liste pour découvrir ce qui existe.
        self.choix_categories = [
            {
                'id': categorie.pk,
                'nom': categorie.nom,
                'icone': categorie.icone,
                'teinte': categorie.teinte,
                'fond': categorie.fond,
                'coche': str(categorie.pk) == str(actuel),
            }
            for categorie in self.fields['categorie'].queryset
        ]


class RepartitionForm(forms.Form):
    """
    Saisie de la répartition du budget initial par catégorie.

    Un champ par catégorie active, pré-rempli avec le montant déjà enregistré.
    La somme est vérifiée par la vue : elle doit être exactement égale au
    montant initial du budget.
    """

    def __init__(self, *args, budget=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.budget = budget
        if budget is None:
            return

        deja = {
            ligne.categorie_id: ligne
            for ligne in budget.repartitions.select_related('categorie')
        }
        self.paires = []
        for categorie in CategorieBudget.objects.filter(active=True).order_by('ordre', 'nom'):
            nom_champ = f'categorie_{categorie.pk}'
            ligne = deja.get(categorie.pk)
            self.fields[nom_champ] = forms.DecimalField(
                required=False,
                min_value=Decimal('0'),
                max_digits=12,
                decimal_places=2,
                label=categorie.nom,
                initial=ligne.montant if ligne else None,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control',
                    'step': '0.01',
                    'min': '0',
                    'placeholder': '0.00',
                }),
            )
            # Le gabarit a besoin de la catégorie (pour sa couleur et son
            # icône) autant que du champ : on les expose ensemble plutôt que
            # de faire deviner l'appariement par l'ordre des champs.
            self.paires.append({
                'categorie': categorie,
                'nom_champ': nom_champ,
                'champ': self[nom_champ],
            })

    def valeurs(self):
        """Retourne {identifiant_categorie: Decimal} pour les montants saisis."""
        resultat = {}
        for nom in self.fields:
            if not nom.startswith('categorie_'):
                continue
            identifiant = int(nom[len('categorie_'):])
            valeur = self.cleaned_data.get(nom)
            if valeur:
                resultat[identifiant] = valeur
        return resultat