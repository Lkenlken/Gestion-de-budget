"""
Backends d'authentification.

`TelephoneBackend` permet de se connecter avec un **numéro de téléphone**
et un mot de passe, en plus du classique couple identifiant / mot de passe
assuré par le `ModelBackend` de Django (ce dernier reste nécessaire à
l'administration Django et à `django.contrib.auth.login`).

Le backend est declared dans `settings.AUTHENTICATION_BACKENDS`.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q

from .telephone import normaliser_telephone


class TelephoneBackend(ModelBackend):
    """
    Authentifie un utilisateur à partir de son numéro de téléphone.

    Le numéro saisi est d'abord normalisé, puis comparé au numéro stocké
    dans `ProfilUtilisateur`. En secours, la valeur saisie est comparée au
    nom d'utilisateur Django : un administrateur peut donc toujours se
    connecter avec son identifiant historique.

    Le contrôle du mot de passe passe par `check_password()` (PBKDF2, sel
    aléatoire, comparaison à temps constant) et le contrôle de l'état du
    compte par `user_can_authenticate()` : le comportement de sécurité est
    donc exactement celui du backend standard de Django.
    """

    def authenticate(self, request, username=None, password=None, telephone=None, **kwargs):
        # `username` est accepté pour rester compatible avec le
        # ModelBackend : c'est lui qui fournit cette clé au formulaire Django
        # standard, et certaines intégrations l'utilisent encore.
        identifiant = telephone or username
        if not identifiant or not password:
            return None

        identifiant = str(identifiant).strip()
        numero = normaliser_telephone(identifiant)

        queryset = User.objects.filter(Q(is_active=True))
        if numero:
            queryset = queryset.filter(
                Q(profil__telephone=numero) | Q(username__iexact=identifiant)
            )
        else:
            queryset = queryset.filter(username__iexact=identifiant)

        utilisateur = queryset.order_by('id').first()
        if utilisateur is None:
            # On ne renvoie jamais `None` explicitement avant d'avoir
            # exécuté une vérification de mot de passe : cela évite de
            # révéler par le temps de réponse quels numéros existent.
            User().set_password(password)  # coût constant volontaire
            return None

        if utilisateur.check_password(password) and self.user_can_authenticate(utilisateur):
            return utilisateur
        return None