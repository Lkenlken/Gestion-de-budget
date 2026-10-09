"""
Rattachement des dépenses existantes à une catégorie.

Utile quand un budget a été saisi avant la mise en place des catégories :
les dépenses existent, mais leur poste n'est pas renseigné.

    python manage.py categoriser_depenses --statistiques
    python manage.py categoriser_depenses --categorie "Courses"
    python manage.py categoriser_depenses --categorie "Courses" --mois "Octobre 2026"
    python manage.py categoriser_depenses --categorie "Courses" --remplacer
    python manage.py categoriser_depenses --categorie "Courses" --oui

Par défaut la commande montre ce qu'elle va modifier et demande confirmation.
`--oui` court-circuite la question (utile pour une série de commandes).
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from budget_app.models import BudgetMensuel, CategorieBudget, Depense


class Command(BaseCommand):
    help = "Rattache les dépenses existantes à une catégorie de budget."

    def add_arguments(self, parser):
        parser.add_argument(
            '--categorie', default='',
            help="Nom de la catégorie cible (ex : Courses).",
        )
        parser.add_argument(
            '--mois', default='',
            help="Limite aux dépenses d'un mois (ex : Octobre 2026).",
        )
        parser.add_argument(
            '--toutes', action='store_true',
            help="Prend toutes les dépenses sans catégorie, tous mois confondus.",
        )
        parser.add_argument(
            '--remplacer', action='store_true',
            help="Déplace aussi les dépenses déjà rattachées à une autre catégorie.",
        )
        parser.add_argument(
            '--retirer', action='store_true',
            help="Au contraire : retire la catégorie des dépenses sélectionnées.",
        )
        parser.add_argument(
            '--creer', action='store_true',
            help="Crée la catégorie si elle n'existe pas encore.",
        )
        parser.add_argument(
            '--statistiques', action='store_true',
            help="Affiche l'état des catégories sans rien modifier.",
        )
        parser.add_argument(
            '--oui', action='store_true',
            help="Ne pose pas de question de confirmation.",
        )

    def handle(self, *args, **options):
        if options['statistiques']:
            self.afficher_etat()
            return

        nom = (options['categorie'] or '').strip()
        if not nom:
            raise CommandError(
                "Indiquez la catégorie cible : --categorie \"Courses\""
            )

        categorie = CategorieBudget.objects.filter(nom__iexact=nom).first()
        if categorie is None:
            if not options['creer']:
                raise CommandError(
                    f"La catégorie « {nom} » n'existe pas.\n"
                    f"  Créez-la depuis l'administration, ou ajoutez --creer."
                )
            categorie = CategorieBudget.objects.create(nom=nom)
            self.stdout.write(self.style.SUCCESS(f"Catégorie créée : {nom}"))

        if not categorie.active:
            categorie.active = True
            categorie.save(update_fields=['active'])
            self.stdout.write(f"  (catégorie réactivée)")

        if options['remplacer'] and options['retirer']:
            raise CommandError(
                "--remplacer et --retirer sont incompatibles."
            )

        # --- Sélection des dépenses -----------------------------------
        selection = Depense.objects.select_related('budget', 'utilisateur')

        if options['mois']:
            budget = BudgetMensuel.objects.filter(mois__iexact=options['mois']).first()
            if budget is None:
                raise CommandError(f"Aucun budget nommé « {options['mois']} ».")
            selection = selection.filter(budget=budget)

        if options['retirer']:
            # On ne retire que les dépenses effectivement dans la catégorie
            # visée : sans ce filtre, `--retirer` viderait toutes les
            # catégories du budget.
            selection = selection.filter(categorie=categorie)
        elif not options['remplacer']:
            # Sans --remplacer, seules les dépenses non encore catégorisées
            # sont prises : c'est le cas visé par la commande, et cela évite
            # de déplacer par surprise des dépenses déjà classées.
            selection = selection.filter(categorie__isnull=True)

        depenses = list(selection.order_by('-date', '-created_at'))

        if not depenses:
            self.stdout.write(
                self.style.WARNING(
                    "Aucune dépense à modifier avec ces critères."
                )
            )
            return

        # --- Aperçu ----------------------------------------------------
        total = sum((d.montant_total for d in depenses), Decimal('0.00'))
        self.stdout.write('')
        self.stdout.write(
            f"Catégorie cible : {self.style.SUCCESS(categorie.nom)}"
        )
        self.stdout.write(
            f"Dépenses       : {len(depenses)}"
            + (f"  ({options['mois']})" if options['mois'] else "  (tous mois)")
        )
        self.stdout.write(f"Montant total  : {total:,.2f} Ar".replace(',', ' '))
        self.stdout.write('')

        par_budget = {}
        for depense in depenses:
            par_budget.setdefault(depense.budget.mois, []).append(depense)
        for mois, lignes in par_budget.items():
            somme = sum((d.montant_total for d in lignes), Decimal('0.00'))
            self.stdout.write(f"  {mois:20} {len(lignes):>4} ligne(s)  {somme:>15,.2f} Ar".replace(',', ' '))

        self.stdout.write('')
        fleche = '→ (sans catégorie)' if options['retirer'] else f'→ {categorie.nom}'
        for depense in depenses[:12]:
            actuelle = depense.categorie.nom if depense.categorie else '—'
            self.stdout.write(
                f"  {depense.date:%d/%m/%Y}  {depense.designation[:38]:38} "
                f"{depense.montant_total:>13,.2f}  {actuelle} {fleche}".replace(',', ' ')
            )
        if len(depenses) > 12:
            self.stdout.write(f"  … et {len(depenses) - 12} autre(s)")

        # --- Confirmation ----------------------------------------------
        if not options['oui']:
            question = (
                'Confirmer le retrait de la catégorie ? (oui/non) : '
                if options['retirer']
                else 'Confirmer le rattachement ? (oui/non) : '
            )
            self.stdout.write('')
            if input(question).strip().lower() not in (
                'o', 'oui', 'y', 'yes'
            ):
                self.stdout.write('Annulé, aucune modification.')
                return

        modifiees = 0
        for depense in depenses:
            depense.categorie = None if options['retirer'] else categorie
            depense.save(update_fields=['categorie'])
            modifiees += 1

        self.stdout.write('')
        if options['retirer']:
            self.stdout.write(self.style.SUCCESS(
                f"{modifiees} dépense(s) sont à nouveau sans catégorie."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"{modifiees} dépense(s) rattachée(s) à « {categorie.nom} »."
            ))
        self.stdout.write(
            f"Totaux par catégorie pour {options['mois'] or 'tous les mois'} :"
        )
        self.afficher_etat()

    def afficher_etat(self):
        """Récapitulatif : par catégorie, puis la liste des non catégorisées."""
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Catégories'))
        if not CategorieBudget.objects.exists():
            self.stdout.write('  Aucune catégorie définie.')
        for categorie in CategorieBudget.objects.prefetch_related('repartitions'):
            self.stdout.write(
                f"  {categorie.nom:20} "
                f"{'active' if categorie.active else 'inactive':9} "
                f"{categorie.repartitions.count():>3} répartition(s)  "
                f"{categorie.depenses.count():>4} dépense(s)"
            )

        par_budget = {}
        for budget in BudgetMensuel.objects.order_by('-created_at'):
            par_budget[budget] = budget

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Par budget mensuel'))
        for budget in par_budget.values():
            total = budget.depenses.count()
            if not total:
                continue
            restants = budget.depenses.filter(categorie__isnull=True).count()
            self.stdout.write(f"  {budget.mois}  —  {total} dépense(s)")
            for categorie in CategorieBudget.objects.all():
                somme = budget.categorie_depense(categorie)
                if somme:
                    self.stdout.write(
                        f"      {categorie.nom:22} {somme:>15,.2f} Ar".replace(',', ' ')
                    )
            if restants:
                self.stdout.write(
                    self.style.WARNING(
                        f"      {'Non catégorisées':22} {restants:>15} dépense(s)"
                    )
                )
            reparti = budget.total_repartition()
            if reparti != budget.montant_initial:
                self.stdout.write(
                    f"      répartition {reparti:,.2f} / budget {budget.montant_initial:,.2f}"
                    .replace(',', ' ')
                )