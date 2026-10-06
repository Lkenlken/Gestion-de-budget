"""
Signaux de l'application.

À la création d'un utilisateur, on crée automatiquement sa ligne
d'autorisation (lecture par défaut, écriture pour un administrateur).
Cela évite de devoir ajouter la ligne à la main dans l'administration.
"""
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PermissionUtilisateur


@receiver(post_save, sender=User)
def creer_permission_utilisateur(sender, instance, created, **kwargs):
    """Crée l'autorisation d'accès dès qu'un compte est créé."""
    if created:
        PermissionUtilisateur.objects.get_or_create(
            utilisateur=instance,
            defaults={
                'peut_lire': True,
                'peut_ecrire': instance.is_staff,
            },
        )
