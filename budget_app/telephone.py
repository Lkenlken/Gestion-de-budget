"""
Normalisation des numéros de téléphone.

L'utilisateur tape son numéro comme il le veut :
    0384160133 / 038 41 601 33 / +261384160133 / 00261384160133
...et l'application le range toujours dans un format unique (E.164) :
    +261384160133

Ce module ne dépend pas de Django : il est utilisable partout (modèles,
formulaires, backends d'authentification, commandes de gestion).
"""
import re

# Indicatif du pays par défaut (Madagascar).
INDICATIF_PAYS = '261'

# Longueur d'un numéro national malgache : 10 chiffres commençant par 0
# (03 = mobile, 0321xxxx = fixe...).
LONGUEUR_NATIONAL = 10


def normaliser_telephone(valeur):
    """
    Retourne le numéro au format E.164 (`+261...`), ou une chaîne vide.

    Exemples :
        >>> normaliser_telephone('0384160133')
        '+261384160133'
        >>> normaliser_telephone('038 41 601 33')
        '+261384160133'
        >>> normaliser_telephone('+261384160133')
        '+261384160133'
        >>> normaliser_telephone('00261384160133')
        '+261384160133'
        >>> normaliser_telephone('')
        ''
    """
    if not valeur:
        return ''

    brut = str(valeur).strip()

    # Un éventuel "+" de tête est conservé comme signe international,
    # tous les autres caractères non numériques sont supprimés.
    chiffres = re.sub(r'\D', '', brut)
    if not chiffres:
        return ''

    # Préfixe international dialable : 00 261 ... -> 261 ...
    if chiffres.startswith('00'):
        chiffres = chiffres[2:]

    # Déjà au format international : 261 + 9 chiffres
    if chiffres.startswith(INDICATIF_PAYS) and len(chiffres) == 12:
        return '+' + chiffres

    # Format national : 0 + 9 chiffres -> on retire le 0 d'accès national
    if len(chiffres) == LONGUEUR_NATIONAL and chiffres.startswith('0'):
        return '+' + INDICATIF_PAYS + chiffres[1:]

    # Numéro inconnu : on renvoie tel quel, en préfixant l'indicatif si
    # l'utilisateur a lui-même saisi un format international.
    if brut.startswith('+'):
        return '+' + chiffres
    return chiffres


def formater_telephone(valeur):
    """
    Retourne une version lisible du numéro : `038 41 601 33`.

    Si le numéro est stocké en E.164 mais que le préfixe national n'est pas
    connu, le numéro est renvoyé tel quel.
    """
    numero = normaliser_telephone(valeur)
    if not numero:
        return ''

    if numero.startswith('+' + INDICATIF_PAYS):
        national = '0' + numero[len(INDICATIF_PAYS) + 1:]
    else:
        return numero

    if len(national) == LONGUEUR_NATIONAL:
        return ' '.join(national[i:i + 2] for i in range(0, LONGUEUR_NATIONAL, 2))
    return national