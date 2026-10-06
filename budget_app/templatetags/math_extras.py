"""
Filtres mathématiques personnalisés pour les templates.

Django ne fournit pas de filtres `div`, `mul` ni `abs` (ils ont été retirés
il y a longtemps). Le dashboard utilise pourtant ces filtres pour calculer
les pourcentages et les barres de progression : ils sont donc réimplémentés
ici.

Usage dans un template :
    {% load math_extras %}
    {{ total|div:budget.montant_initial|mul:100|floatformat:1 }}
"""
from decimal import Decimal, InvalidOperation

from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


def _to_number(value):
    """Convertit une valeur template (str, int, Decimal, float) en nombre."""
    if isinstance(value, (int, float, Decimal)):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@register.filter
def div(value, arg):
    """
    Divise `value` par `arg`. Retourne 0 si le diviseur est nul ou invalide.
    Le résultat est un Decimal pour conserver la précision monétaire.
    """
    numerator = _to_number(value)
    denominator = _to_number(arg)
    if numerator is None or denominator in (None, 0):
        return 0
    return Decimal(numerator) / Decimal(denominator)


@register.filter
def mul(value, arg):
    """Multiplie `value` par `arg`."""
    left = _to_number(value)
    right = _to_number(arg)
    if left is None or right is None:
        return 0
    return Decimal(left) * Decimal(right)


@register.filter
def absv(value):
    """Valeur absolue (le nom `abs` est réservé en Python)."""
    number = _to_number(value)
    if number is None:
        return 0
    import builtins
    return builtins.abs(number)


# Alias utilisable directement dans les templates : {{ valeur|abs }}
register.filter('abs', absv)


@register.filter
def ar(value):
    """
    Formate un montant en Ariary : 1234567.8 -> "1 234 567.80 Ar".
    """
    number = _to_number(value)
    if number is None:
        return value
    formatted = floatformat(number, 2)
    # Espace fine insécable entre les milliers, comme dans le reste de l'app
    integer, _, decimals = str(formatted).partition('.')
    sign = ''
    if integer.startswith('-'):
        sign, integer = '-', integer[1:]
    grouped = ''
    for index, char in enumerate(reversed(integer)):
        grouped = char + grouped
        if (index + 1) % 3 == 0 and index + 1 < len(integer):
            grouped = ' ' + grouped
    return f"{sign}{grouped}.{decimals} Ar" if decimals else f"{sign}{grouped} Ar"
