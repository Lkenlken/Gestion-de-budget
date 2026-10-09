"""
Palette de couleurs des catégories de budget.

L'utilisateur choisit une couleur **par son nom** (« bleu », « cyan »,
« rouge »…), jamais en tapant un code hexadécimal : personne ne sait, en
tapant, que `#06b6d4` est le cyan.

Ce module ne dépend pas de Django : les mêmes tables servent au formulaire
d'administration, aux migrations de données et aux gabarits.
"""

# Couleurs simples : nom technique -> (libellé affiché, code hexadécimal)
COULEURS = {
    'bleu': ('Bleu', '#2563eb'),
    'bleu-clair': ('Bleu clair', '#60a5fa'),
    'bleu-nuit': ('Bleu nuit', '#1e3a8a'),
    'cyan': ('Cyan', '#06b6d4'),
    'turquoise': ('Turquoise', '#0d9488'),
    'vert': ('Vert', '#16a34a'),
    'vert-clair': ('Vert clair', '#4ade80'),
    'jaune': ('Jaune', '#eab308'),
    'ambre': ('Ambre', '#f59e0b'),
    'orange': ('Orange', '#f97316'),
    'rouge': ('Rouge', '#dc3545'),
    'rose': ('Rose', '#db2777'),
    'violet': ('Violet', '#7c3aed'),
    'ardoise': ('Gris ardoise', '#64748b'),
}

# Dégradés : nom technique -> (libellé affiché, couleur de départ, couleur d'arrivée)
DEGRADES = {
    'bleu-degrade': ('Bleu dégradé', '#3b82f6', '#1d4ed8'),
    'cyan-degrade': ('Cyan dégradé', '#22d3ee', '#0891b2'),
    'turquoise-degrade': ('Turquoise dégradé', '#2dd4bf', '#0f766e'),
    'vert-degrade': ('Vert dégradé', '#4ade80', '#15803d'),
    'ambre-degrade': ('Ambre dégradé', '#fbbf24', '#d97706'),
    'orange-degrade': ('Orange dégradé', '#fb923c', '#ea580c'),
    'rouge-degrade': ('Rouge dégradé', '#f87171', '#b91c1c'),
    'rose-degrade': ('Rose dégradé', '#f472b6', '#be185d'),
    'violet-degrade': ('Violet dégradé', '#a78bfa', '#6d28d9'),
}

# Ordre d'affichage dans le menu déroulant.
ORDRE_COULEURS = [
    'bleu', 'bleu-clair', 'bleu-nuit', 'cyan', 'turquoise',
    'vert', 'vert-clair', 'jaune', 'ambre', 'orange',
    'rouge', 'rose', 'violet', 'ardoise',
]
ORDRE_DEGRADES = [
    'bleu-degrade', 'cyan-degrade', 'turquoise-degrade', 'vert-degrade',
    'ambre-degrade', 'orange-degrade', 'rouge-degrade', 'rose-degrade',
    'violet-degrade',
]

COULEUR_PAR_DEFAUT = 'bleu'

# Correspondance entre les anciens codes hexadécimaux (saisie libre avant
# cette palette) et les noms de la palette. Sert à la migration de données.
ANCIENNES_COULEURS = {
    '#2563eb': 'bleu',          # bleu par défaut de Django
    '#1d4ed8': 'bleu-nuit',
    '#3b82f6': 'bleu-clair',
    '#60a5fa': 'bleu-clair',
    '#06b6d4': 'cyan',
    '#0d9488': 'turquoise',
    '#0ea5e9': 'cyan',          # valeur de la graine de démonstration
    '#16a34a': 'vert',
    '#4ade80': 'vert-clair',
    '#eab308': 'jaune',
    '#f59e0b': 'ambre',
    '#f97316': 'orange',
    '#dc3545': 'rouge',
    '#db2777': 'rose',
    '#7c3aed': 'violet',
    '#64748b': 'ardoise',
}


def couleur_connue(valeur):
    """
    Traduit une valeur stockée en nom de palette.

    - un nom connu est renvoyé tel quel ;
    - un ancien code hexadécimal est converti vers le nom correspondant ;
    - toute autre valeur retombe sur la couleur par défaut, plutôt que de
      laisser une catégorie invisible dans l'interface.
    """
    if not valeur:
        return COULEUR_PAR_DEFAUT
    valeur = str(valeur).strip().lower()
    if valeur in COULEURS or valeur in DEGRADES:
        return valeur
    if valeur in ANCIENNES_COULEURS:
        return ANCIENNES_COULEURS[valeur]
    # Ancien code hexadécimal inconnu : on cherche la teinte la plus proche.
    return _plus_proche(valeur)


def _plus_proche(hexa):
    """Trouve la couleur de la palette la plus proche d'un hexadécimal."""
    if not hexa.startswith('#') or len(hexa) != 7:
        return COULEUR_PAR_DEFAUT
    try:
        cible = tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return COULEUR_PAR_DEFAUT

    meilleur, distance_min = COULEUR_PAR_DEFAUT, None
    for nom, (_, hexa_connue) in COULEURS.items():
        autre = tuple(int(hexa_connue[i:i + 2], 16) for i in (1, 3, 5))
        distance = sum((a - b) ** 2 for a, b in zip(cible, autre))
        if distance_min is None or distance < distance_min:
            meilleur, distance_min = nom, distance
    return meilleur


def libelle(valeur):
    """« bleu » -> « Bleu », « rouge-degrade » -> « Rouge dégradé »."""
    nom = couleur_connue(valeur)
    if nom in COULEURS:
        return COULEURS[nom][0]
    if nom in DEGRADES:
        return DEGRADES[nom][0]
    return COULEURS[COULEUR_PAR_DEFAUT][0]


def teinte_debut(valeur):
    """Code hexadécimal de la première teinte."""
    nom = couleur_connue(valeur)
    if nom in DEGRADES:
        return DEGRADES[nom][1]
    return COULEURS.get(nom, COULEURS[COULEUR_PAR_DEFAUT])[1]


def teinte_fin(valeur):
    """Code hexadécimal de la seconde teinte, ou None pour une couleur simple."""
    nom = couleur_connue(valeur)
    if nom in DEGRADES:
        return DEGRADES[nom][2]
    return None


def fond(valeur):
    """
    Valeur CSS à utiliser en `background`.

    Un dégradé devient `linear-gradient(...)` ; une couleur simple reste un
    hexadécimal, utilisable partout (y compris dans un `border-color`).
    """
    nom = couleur_connue(valeur)
    if nom in DEGRADES:
        return f'linear-gradient(90deg, {DEGRADES[nom][1]}, {DEGRADES[nom][2]})'
    return teinte_debut(nom)


def rgba(valeur, alpha=0.14):
    """
    Version translucide d'une couleur, pour les pastilles et les badges.

    Un dégradé n'a pas de couleur plate : c'est la teinte de départ qui est
    utilisée, avec une opacité réduite.
    """
    hexa = teinte_debut(valeur)
    r = int(hexa[1:3], 16)
    g = int(hexa[3:5], 16)
    b = int(hexa[5:7], 16)
    return f'rgba({r}, {g}, {b}, {alpha})'


def texte_lisible(valeur):
    """
    Couleur de texte lisible sur un aplat de la couleur choisie.

    Les teintes claires (jaune, ambre, vert clair…) exigent un texte foncé ;
    les autres tolèrent le blanc.
    """
    hexa = teinte_debut(valeur)
    r = int(hexa[1:3], 16)
    g = int(hexa[3:5], 16)
    b = int(hexa[5:7], 16)
    # Luminance relative (formule ITU-R BT.601).
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return '#111827' if luminance > 0.6 else '#ffffff'
