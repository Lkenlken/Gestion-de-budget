"""
Génération du PDF d'un devis.

Le PDF est produit par ReportLab, sans dépendance système : il fonctionne
aussi bien sur l'hébergement gratuit que sur un poste Windows.

Si la bibliothèque est absente, `generer_devis` renvoie None et la vue
affiche un message clair plutôt qu'une page d'erreur.
"""
import io
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BLEU = colors.HexColor('#1d4ed8')
GRIS_CLAIR = colors.HexColor('#f1f5f9')
GRIS_BORD = colors.HexColor('#cbd5e1')
GRIS_TEXTE = colors.HexColor('#475569')


def formater_montant(valeur):
    """`1234.5` -> `1 234,50 Ar` (espace insécable fine comme séparateur)."""
    quantite = Decimal(valeur or 0).quantize(Decimal('0.01'))
    entier, _, decimales = f"{quantite:f}".partition('.')
    groupees = []
    while len(entier) > 3:
        groupees.insert(0, entier[-3:])
        entier = entier[:-3]
    groupees.insert(0, entier)
    return f"{' '.join(groupees)},{decimales}"


def generer_devis(devis, *, contact=None, mobile_money=None):
    """
    Retourne les octets du PDF, ou None si ReportLab n'est pas installé.

    contact : dict {nom, telephone, email} de l'administrateur
    mobile_money : dict {numero, nom, operateur} pour le bloc de paiement
    """
    try:
        tampon = io.BytesIO()
        document = SimpleDocTemplate(
            tampon,
            pagesize=A4,
            leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=16 * mm, bottomMargin=16 * mm,
            title=f"Devis {devis.nom}",
            author=(contact or {}).get('nom', 'Kendevis'),
        )
        _ecrire(document, devis, contact or {}, mobile_money or {})
        return tampon.getvalue()
    except ImportError:
        return None


def _ecrire(document, devis, contact, mobile_money):
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=20,
                        textColor=BLEU, spaceAfter=2)
    sous_titre = ParagraphStyle('sous', parent=styles['Normal'], fontSize=10,
                               textColor=GRIS_TEXTE, spaceAfter=10)
    cellule = ParagraphStyle('cell', parent=styles['Normal'], fontSize=9)
    cellule_droite = ParagraphStyle('cellD', parent=cellule, alignment=TA_RIGHT)
    total_style = ParagraphStyle('total', parent=styles['Normal'], fontSize=11,
                                textColor=BLEU, alignment=TA_RIGHT)
    pied = ParagraphStyle('pied', parent=styles['Normal'], fontSize=8,
                         textColor=GRIS_TEXTE)

    histoire = []

    # --- En-tête ------------------------------------------------------
    entete = Table(
        [
            [
                Paragraph("<b>KENDEVIS</b><br/>Gestion de budget", cellule),
                Paragraph(f"<b>DEVIS</b><br/>{_echapper(devis.nom)}", cellule_droite),
            ]
        ],
        colWidths=[85 * mm, 85 * mm],
    )
    entete.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (1, 0), (1, 0), 12),
        ('TEXTCOLOR', (1, 0), (1, 0), BLEU),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -1), 1.2, BLEU),
    ]))
    histoire.append(entete)
    histoire.append(Spacer(1, 10))

    # --- Coordonnées --------------------------------------------------
    infos_devis = Paragraph(
        f"<b>Date :</b> {devis.date.strftime('%d/%m/%Y')}<br/>"
        f"<b>Établi par :</b> {_echapper(devis.auteur.username)}",
        cellule,
    )
    infos_contact = Paragraph(
        f"<b>Contact</b><br/>"
        f"{_echapper(contact.get('nom', 'Administrateur'))}<br/>"
        + (f"Tél. {_echapper(contact.get('telephone', ''))}<br/>"
           if contact.get('telephone') else '')
        + (_echapper(contact.get('email', '')) if contact.get('email') else ''),
        cellule,
    )
    coordonnees = Table([[infos_devis, infos_contact]], colWidths=[85 * mm, 85 * mm])
    coordonnees.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, 0), GRIS_CLAIR),
        ('BOX', (0, 0), (-1, -1), 0.5, GRIS_BORD),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, GRIS_BORD),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    histoire.append(coordonnees)
    histoire.append(Spacer(1, 14))

    # --- Lignes -------------------------------------------------------
    donnees = [[
        Paragraph("#", cellule),
        Paragraph("<b>Objet</b>", cellule),
        Paragraph("<b>Quantité</b>", cellule_droite),
        Paragraph("<b>Prix unitaire</b>", cellule_droite),
        Paragraph("<b>Montant</b>", cellule_droite),
    ]]
    lignes = list(devis.lignes.all())
    for index, ligne in enumerate(lignes, start=1):
        donnees.append([
            Paragraph(str(index), cellule),
            Paragraph(f"<b>{_echapper(ligne.objet)}</b>", cellule),
            Paragraph(_quantite(ligne.quantite), cellule_droite),
            Paragraph(formater_montant(ligne.prix_unitaire), cellule_droite),
            Paragraph(formater_montant(ligne.total), cellule_droite),
        ])

    donnees.append([
        Paragraph('', cellule), Paragraph('', cellule),
        Paragraph('<b>TOTAL</b>', cellule_droite),
        Paragraph('', cellule_droite),
        Paragraph(f"<b>{formater_montant(devis.total)} Ar</b>", total_style),
    ])

    tableau = Table(
        donnees,
        colWidths=[10 * mm, 76 * mm, 22 * mm, 33 * mm, 29 * mm],
        repeatRows=1,
    )
    tableau.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), GRIS_CLAIR),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, GRIS_BORD),
        ('LINEABOVE', (0, -1), (-1, -1), 0.8, GRIS_BORD),
        ('LINEBELOW', (0, -1), (-1, -1), 0.8, GRIS_BORD),
        ('GRID', (0, 1), (-1, -2), 0.4, GRIS_BORD),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        # Une ligne sur deux légèrement grisée : le repérage visuel d'un
        # tableau de dizaines de lignes est le problème classique.
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    histoire.append(tableau)

    if not lignes:
        histoire.append(Spacer(1, 6))
        histoire.append(Paragraph(
            "Ce devis ne contient aucune ligne.", pied))

    # --- Observations -------------------------------------------------
    if devis.notes:
        histoire.append(Spacer(1, 14))
        histoire.append(Paragraph("<b>Observations</b>", cellule))
        histoire.append(Spacer(1, 3))
        histoire.append(Paragraph(_echapper(devis.notes).replace('\n', '<br/>'), cellule))

    # --- Partage et paiement ------------------------------------------
    partages = devis.visible_par.all()
    if partages:
        histoire.append(Spacer(1, 10))
        histoire.append(Paragraph(
            "<b>Visible par :</b> "
            + _echapper(', '.join(u.username for u in partages)), pied))

    reste = devis.reste_a_payer()
    if reste:
        histoire.append(Spacer(1, 14))
        tableau_paiement = Table(
            [[
                Paragraph(
                    "<b>Reste à régler</b><br/>"
                    f"{formater_montant(reste)} Ar"
                    + (f"<br/>déjà réglé : {formater_montant(devis.total - reste)} Ar"
                       if devis.total != reste else ""),
                    cellule,
                ),
                Paragraph(
                    "<b>Paiement par mobile money</b><br/>"
                    + (f"{_echapper(mobile_money.get('nom', ''))}<br/>"
                       if mobile_money.get('nom') else "")
                    + (f"N° {_echapper(mobile_money.get('numero_affiche') or mobile_money.get('numero', ''))}<br/>"
                       if (mobile_money.get('numero_affiche') or mobile_money.get('numero')) else "")
                    + (_echapper(mobile_money.get('operateur', ''))
                       if mobile_money.get('operateur') else ""),
                    cellule,
                ),
            ]],
            colWidths=[85 * mm, 85 * mm],
        )
        tableau_paiement.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), GRIS_CLAIR),
            ('BOX', (0, 0), (-1, -1), 0.5, GRIS_BORD),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, GRIS_BORD),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        histoire.append(tableau_paiement)

    # --- Pied de page -------------------------------------------------
    histoire.append(Spacer(1, 18))
    histoire.append(Paragraph(
        f"Document généré le {date.today().strftime('%d/%m/%Y')} "
        f"par l'application Kendevis.",
        pied,
    ))

    document.build(histoire)


def _echapper(texte):
    """Échappe le texte pour ReportLab, qui interprète le HTML."""
    if not texte:
        return ''
    return (str(texte)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def _quantite(valeur):
    """Affiche 2 sans décimales, 2.50 avec."""
    nombre = Decimal(valeur or 0)
    return str(nombre.quantize(Decimal('0.01')).normalize()
               if nombre % 1 else nombre.quantize(Decimal('1')))
