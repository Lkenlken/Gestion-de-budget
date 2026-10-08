"""
Génération des icônes de l'application (PNG), sans dépendance externe.

Les icônes sont produites avec un encodeur PNG minimal (zlib + struct) et un
rendu par distance signée, suréchantillonné 2×2 pour lisser les bords.

    python tools/generer_icones.py

Produit :
    budget_app/static/budget_app/icons/icon-192.png
    budget_app/static/budget_app/icons/icon-512.png
    budget_app/static/budget_app/icons/icon-maskable-512.png
    budget_app/static/budget_app/icons/apple-touch-icon.png
    budget_app/static/budget_app/icons/favicon.png
"""
import math
import os
import struct
import zlib

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINATION = os.path.join(RACINE, 'budget_app', 'static', 'budget_app', 'icons')

# Couleurs de la marque (mêmes valeurs que --primary-strong / --primary).
HAUT = (0x3B, 0x82, 0xF6)   # blue-500
BAS = (0x1D, 0x4E, 0xD8)    # blue-700
BLANC = (255, 255, 255)

ECHELLE = 2  # suréchantillonnage pour l'anticrénelage


def ecrire_png(chemin, largeur, hauteur, pixels):
    """pixels : octets RGBC (4 octets par pixel), ligne par ligne."""
    lignes = bytearray()
    stride = largeur * 4
    for y in range(hauteur):
        lignes.append(0)  # filtre « None »
        lignes += pixels[y * stride:(y + 1) * stride]

    def morceau(type_png, donnees):
        return (
            struct.pack('>I', len(donnees))
            + type_png
            + donnees
            + struct.pack('>I', zlib.crc32(type_png + donnees) & 0xFFFFFFFF)
        )

    contenu = b'\x89PNG\r\n\x1a\n'
    contenu += morceau(b'IHDR', struct.pack('>IIBBBBB', largeur, hauteur, 8, 6, 0, 0, 0))
    contenu += morceau(b'IDAT', zlib.compress(bytes(lignes), 9))
    contenu += morceau(b'IEND', b'')

    with open(chemin, 'wb') as fichier:
        fichier.write(contenu)


def distance_rect_arrondi(x, y, cx, cy, demi_l, demi_h, rayon):
    """Signe négatif à l'intérieur du rectangle arrondi."""
    dx = abs(x - cx) - (demi_l - rayon)
    dy = abs(y - cy) - (demi_h - rayon)
    dx = max(dx, 0.0)
    dy = max(dy, 0.0)
    return math.hypot(dx, dy) - rayon


def melanger(fond, dessus, alpha):
    return tuple(
        int(round(fond[i] * (1 - alpha) + dessus[i] * alpha))
        for i in range(3)
    )


def dessiner(taille, arrondi=True, zone_securise=1.0):
    """
    Rend l'icône.

    arrondi        : fond en carré à coins arrondis (icône classique)
    zone_securise  : 1.0 = glyphe plein cadre ; 0.62 = glyphe réduit au centre,
                     taille requise par Android pour une icône « maskable »
                     (le système peut la rogner jusqu'à 40 %).
    """
    n = taille * ECHELLE
    pixels = bytearray(taille * taille * 4)

    # Géométrie exprimée en fraction de la taille, puis mise à l'échelle.
    # Portefeuille : corps blanc + poche bleue + rivet blanc.
    glyphe = [
        # (type, x0, y0, x1, y1, rayon, couleur)
        ('rect', 0.215, 0.295, 0.785, 0.705, 0.075, BLANC),
        ('rect', 0.545, 0.435, 0.775, 0.565, 0.030, None),  # None = couleur du fond
        ('rond', 0.625, 0.500, 0.0, 0.0, 0.032, BLANC),
    ]

    for y in range(taille):
        for x in range(taille):
            # Échantillonnage 2×2 pour lisser les bords.
            r = v = b = 0.0
            for sous_y in range(ECHELLE):
                for sous_x in range(ECHELLE):
                    px = (x * ECHELLE + sous_x + 0.5) / n
                    py = (y * ECHELLE + sous_y + 0.5) / n

                    # Fond : dégradé vertical bleu.
                    couleur_fond = melanger(HAUT, BAS, min(max(py, 0.0), 1.0))

                    # Masque du fond (carré plein ou coins arrondis).
                    if arrondi:
                        masque = distance_rect_arrondi(px, py, 0.5, 0.5, 0.5, 0.5, 0.22)
                    else:
                        masque = -1.0
                    if masque > 0:
                        r = v = b = 0.0
                        continue

                    couleur = couleur_fond
                    for forme in glyphe:
                        genre, x0, y0, x1, y1, rayon, teinte = forme
                        # Centrage et reduction du glyphe pour les icônes
                        # maskable.
                        if genre == 'rect':
                            centre = 0.5
                            demi = (x1 - x0) / 2 * zone_securise
                            cx = centre + ((x0 + x1) / 2 - centre) * zone_securise
                            cy = centre + ((y0 + y1) / 2 - centre) * zone_securise
                            d = distance_rect_arrondi(
                                px, py, cx, cy, demi, demi, rayon * zone_securise
                            )
                        else:
                            cx = 0.5 + (x0 - 0.5) * zone_securise
                            cy = 0.5 + (y0 - 0.5) * zone_securise
                            d = math.hypot(px - cx, py - cy) - rayon * zone_securise

                        if d <= 0:
                            couleur = couleur_fond if teinte is None else teinte

                    r += couleur[0]
                    v += couleur[1]
                    b += couleur[2]

            total = ECHELLE * ECHELLE
            decalage = (y * taille + x) * 4
            pixels[decalage + 0] = min(255, int(r / total + 0.5))
            pixels[decalage + 1] = min(255, int(v / total + 0.5))
            pixels[decalage + 2] = min(255, int(b / total + 0.5))
            pixels[decalage + 3] = 255  # opaque : pas de transparence parasite

    return pixels


def main():
    os.makedirs(DESTINATION, exist_ok=True)

    cibles = [
        ('icon-192.png', 192, True, 1.0),
        ('icon-512.png', 512, True, 1.0),
        ('icon-maskable-512.png', 512, False, 0.62),
        ('apple-touch-icon.png', 180, False, 0.82),
        ('favicon.png', 64, True, 1.0),
    ]

    for nom, taille, arrondi, zone in cibles:
        pixels = dessiner(taille, arrondi=arrondi, zone_securise=zone)
        chemin = os.path.join(DESTINATION, nom)
        ecrire_png(chemin, taille, taille, pixels)
        poids = os.path.getsize(chemin)
        print(f"  {nom:28} {taille}x{taille}  {poids / 1024:6.1f} Ko")

    print(f"\nIcônes écrites dans {DESTINATION}")


if __name__ == '__main__':
    main()