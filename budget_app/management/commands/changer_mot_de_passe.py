"""
Changement du mot de passe d'un compte existant.

Le mot de passe est saisie en caché : il n'apparaît ni dans l'historique du
shell, ni dans la liste des processus.

Usage
-----
        python manage.py changer_mot_de_passe

puis, pour un compte précis :

        python manage.py changer_mot_de_passe --nom Andonilanitra

ou, pour un changement non interactif (scripts, interventions) :

        python manage.py changer_mot_de_passe --nom Andonilanitra --stdin

`--stdin` lit le mot de passe sur l'entrée standard, ce qui permet de le
fournir sans le passer en argument de ligne de commande.
"""
import getpass
import re
import sys

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from budget_app.telephone import normaliser_telephone


class Command(BaseCommand):
    help = "Change le mot de passe d'un compte (identifiant : nom ou téléphone)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--nom', default='',
            help="Nom du compte, ou numéro de téléphone.",
        )
        parser.add_argument(
            '--stdin', action='store_true',
            help="Lit le nouveau mot de passe sur l'entrée standard.",
        )

    def handle(self, *args, **options):
        identifiant = (options['nom'] or '').strip()
        if not identifiant:
            identifiant = input("Compte (nom ou téléphone) : ").strip()
        if not identifiant:
            raise CommandError("Aucun compte indiqué.")

        utilisateur = self._trouver(identifiant)
        numero = getattr(getattr(utilisateur, 'profil', None), 'telephone', '')

        self.stdout.write(f"Compte trouvé : {utilisateur.username}")
        if numero:
            self.stdout.write(f"Téléphone      : {utilisateur.profil.telephone_affiche}")

        if options['stdin']:
            nouveau = sys.stdin.readline().rstrip('\n')
            if not nouveau:
                raise CommandError("Aucun mot de passe reçu sur l'entrée standard.")
            confirmation = nouveau
        else:
            nouveau, confirmation = self._demander()

        if nouveau != confirmation:
            raise CommandError("Les deux saisies diffèrent.")
        if len(nouveau) < 8:
            raise CommandError(
                "Mot de passe trop court : 8 caractères minimum."
            )

        # Avertissements (comme pour `creer_admin`) : on ne bloque pas, mais
        # on signale les faiblesses habituelles de Django.
        try:
            validate_password(nouveau, utilisateur)
        except ValidationError as erreurs:
            for message in erreurs.messages:
                self.stdout.write(self.style.WARNING(f'  Attention : {message}'))
        if re.search(r'^\d+$', nouveau):
            self.stdout.write(self.style.WARNING(
                '  Conseil : évitez un mot de passe purement numérique.'
            ))

        utilisateur.set_password(nouveau)
        utilisateur.save(update_fields=['password'])

        # Toutes les sessions ouvertes avec l'ancien mot de passe sont
        # invalidées : c'est le comportement attendu d'un changement de
        # mot de passe.
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'✔ Mot de passe modifié pour « {utilisateur.username} ».'
        ))
        self.stdout.write('  Les sessions ouvertes avec l\'ancien mot de passe '
                          'ont été déconnectées.')

    def _trouver(self, identifiant):
        numero = normaliser_telephone(identifiant)
        queryset = User.objects.all()
        if numero:
            queryset = queryset.filter(profil__telephone=numero)
        utilisateur = queryset.order_by('id').first()
        if utilisateur is None and not numero:
            utilisateur = User.objects.filter(
                username__iexact=identifiant
            ).order_by('id').first()
        if utilisateur is None:
            raise CommandError(f"Aucun compte ne correspond à « {identifiant} ».")
        return utilisateur

    def _demander(self):
        while True:
            nouveau = getpass.getpass('Nouveau mot de passe  : ')
            if not nouveau:
                self.stdout.write(self.style.ERROR(
                    'Le mot de passe est obligatoire.'
                ))
                continue
            confirmation = getpass.getpass('Confirmation           : ')
            return nouveau, confirmation