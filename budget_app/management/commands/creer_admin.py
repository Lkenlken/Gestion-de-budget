"""
Création d'un compte administrateur depuis la ligne de commande.

Le compte se connecte avec son **numéro de téléphone** et son mot de passe.

Usage
-----
Interactif (le mot de passe est saisi en caché, jamais en argument) :

    python manage.py creer_admin

Avec des arguments (le mot de passe reste demandé de façon interactive) :

    python manage.py creer_admin --nom Andonilanitra --telephone 0384160133 \
        --email contact@example.com

Options :

    --admin   crée un administrateur (défaut : superutilisateur Django)
    --lecture seule : administrateur sans droits d'écriture sur les dépenses

La commande est idempotente : relancer avec les mêmes valeurs met à jour le
compte existant au lieu d'en créer un second.
"""
import getpass
import re

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from budget_app.models import creer_profil, permission_de
from budget_app.telephone import normaliser_telephone


class Command(BaseCommand):
    help = "Crée ou met à jour un compte administrateur (connexion par téléphone)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--nom', default='',
            help="Nom / identifiant du compte (ex : Andonilanitra).",
        )
        parser.add_argument(
            '--telephone', default='',
            help="Numéro de téléphone utilisé pour se connecter (ex : 0384160133).",
        )
        parser.add_argument('--email', default='', help="Adresse e-mail (facultatif).")
        parser.add_argument(
            '--fonction', default='',
            help="Fonction affichée dans l'application (facultatif).",
        )
        parser.add_argument(
            '--sans-ecriture', action='store_true',
            help="Administrateur en lecture seule (ne peut pas supprimer de dépense).",
        )

    def handle(self, *args, **options):
        nom = (options['nom'] or '').strip()
        while not nom:
            nom = input('Nom du compte (ex : Andonilanitra) : ').strip()
            if not nom:
                self.stdout.write(self.style.ERROR('Le nom est obligatoire.'))

        numero = normaliser_telephone(
            options['telephone'] or self._demander_telephone()
        )
        if not numero:
            raise CommandError("Numéro de téléphone invalide.")

        # Un numéro ne peut être attribué qu'à un seul compte.
        conflit = User.objects.filter(profil__telephone=numero).first()
        if conflit and conflit.username != nom:
            raise CommandError(
                f"Le numéro {numero} est déjà attribué au compte « {conflut.username} »."
            )

        email = (options['email'] or '').strip()
        mot_de_passe = self._demander_mot_de_passe(nom)

        with transaction.atomic():
            utilisateur, cree = User.objects.get_or_create(
                username=nom,
                defaults={'email': email},
            )
            utilisateur.email = email or utilisateur.email
            utilisateur.is_staff = True
            utilisateur.is_superuser = True
            utilisateur.is_active = True
            if not options['sans_ecriture']:
                # `is_staff` autorise la suppression des dépenses ;
                # `is_superuser` donne en plus l'accès complet à /admin/.
                utilisateur.is_superuser = True
            utilisateur.set_password(mot_de_passe)
            utilisateur.save()

            profil, _ = creer_profil(utilisateur, numero, options['fonction'])
            permission = permission_de(utilisateur)
            permission.peut_lire = True
            permission.peut_ecrire = True
            permission.save()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✔ Compte administrateur prêt.'))
        self.stdout.write(f"  Nom         : {utilisateur.username}")
        self.stdout.write(f"  Téléphone   : {profil.telephone_affiche}  ({profil.telephone})")
        self.stdout.write(f"  E-mail      : {utilisateur.email or '(non renseigné)'}")
        self.stdout.write(f"  Mot de passe: (celui que vous venez de saisir)")
        self.stdout.write('')
        self.stdout.write(f"  Connexion   : {profil.telephone_affiche}  +  votre mot de passe")
        if cree:
            self.stdout.write('  Compte créé.')
        else:
            self.stdout.write(self.style.WARNING(
                '  Ce compte existait déjà : ses informations ont été mises à jour.'
            ))

    def _demander_telephone(self):
        while True:
            valeur = input('Téléphone (ex : 0384160133) : ').strip()
            if normaliser_telephone(valeur):
                return valeur
            self.stdout.write(self.style.ERROR('Numéro invalide, réessayez.'))

    def _demander_mot_de_passe(self, nom):
        while True:
            mot_de_passe = getpass.getpass(
                f"Mot de passe de « {nom} » : "
            )
            confirmation = getpass.getpass('Confirmation            : ')
            if not mot_de_passe:
                self.stdout.write(self.style.ERROR('Le mot de passe est obligatoire.'))
                continue
            if mot_de_passe != confirmation:
                self.stdout.write(self.style.ERROR('Les deux saisies diffèrent.'))
                continue
            self._avertir_si_faible(mot_de_passe, nom)
            return mot_de_passe

    def _avertir_si_faible(self, mot_de_passe, nom):
        """
        Signale les faiblesses sans bloquer : c'est l'administrateur qui
        décide, et Django n'impose ses règles qu'à la création interactive.
        """
        try:
            validate_password(mot_de_passe, User(username=nom))
        except ValidationError as erreurs:
            self.stdout.write(self.style.WARNING(
                '  Mot de passe faible : ' + ' '.join(erreurs.messages)
            ))
        if re.search(r'^\d+$', mot_de_passe) or len(mot_de_passe) < 10:
            self.stdout.write(self.style.WARNING(
                '  Conseil : évitez un mot de passe purement numérique ou trop court.'
            ))