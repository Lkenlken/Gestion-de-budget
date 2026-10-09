import logging
from decimal import Decimal
from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout as django_logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, DecimalField, F, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponse, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import (
    BudgetMensuel,
    CategorieBudget,
    Depense,
    ProfilUtilisateur,
    RepartitionCategorie,
    permission_de,
    telephone_de,
)
from .forms import ConnexionForm, DepenseForm, RepartitionForm
from .telephone import formater_telephone, normaliser_telephone

logger = logging.getLogger(__name__)

# Type utilisé pour sommer prix_unitaire × quantite : la multiplication de
# deux champs produit un Decimal dont Django ne devine pas la précision.
MONTANT = DecimalField(max_digits=14, decimal_places=2)
ZERO = Decimal('0.00')


def montant_total():
    """
    Somme des montants d'un queryset de dépenses (prix_unitaire × quantite).

    Deux précautions :
      * `Sum(a) * Sum(b)` est refusé par l'ORM : il faut multiplier les
        champs de chaque ligne puis sommer ;
      * `Coalesce(..., 0)` est refusé également — un Decimal et un entier
        ne peuvent pas être mélangés. La valeur de repli est donc `Decimal`.
    """
    return Sum(F('prix_unitaire') * F('quantite'), output_field=MONTANT)

# --- Paramètres de limitation des tentatives de connexion -----------------
# Au bout de `LOGIN_ATTEMPT_LIMIT` échecs consécutifs, la connexion est
# bloquée pendant `LOGIN_ATTEMPT_WINDOW` secondes (clé mise en cache).
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW = 5 * 60  # 5 minutes


def _client_ip(request):
    """Retourne l'adresse IP du client (tient compte d'un proxy si présent)."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or 'inconnu'


def _cache_key(request, identifiant=''):
    """
    Clé de cache unique pour un couple (IP, identifiant).

    L'identifiant est le numéro de téléphone normalisé : `0384160133`,
    `038 41 601 33` et `+261384160133` partagent donc le même compteur
    d'échecs, ce qui empêche de contourner la limite en changeant
    la façon dont le numéro est écrit.
    """
    return f"login-attempt:{_client_ip(request)}:{normaliser_telephone(identifiant)}"


@method_decorator(never_cache, name='dispatch')
class ThrottledLoginView(auth_views.LoginView):
    """
    Page de connexion protégée contre le force brute.

    L'identifiant est le **numéro de téléphone** (voir `ConnexionForm`).

    - 5 tentatives ratées dans la même adresse IP / numéro => blocage
      de 5 minutes (réponse HTTP 429).
    - Une connexion réussie remet le compteur à zéro.
    - `never_cache` évite que la page de connexion soit mise en cache par le
      navigateur ou par un proxy.
    """
    template_name = 'budget_app/registration/login.html'
    authentication_form = ConnexionForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST' and not request.user.is_authenticated:
            telephone = (request.POST.get('telephone') or '').strip()
            key = _cache_key(request, telephone)
            if cache.get(f'{key}:blocked'):
                logger.warning(
                    "Tentative de connexion bloquée (IP=%s, telephone=%s)",
                    _client_ip(request), normaliser_telephone(telephone),
                )
                return HttpResponse(
                    "<h1>429 - Trop de tentatives</h1>"
                    "<p>Trop de tentatives de connexion échouées. "
                    "Réessayez dans quelques minutes.</p>",
                    status=429,
                    content_type='text/html; charset=utf-8',
                )
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        """Comptabilise l'échec et bloque la clé si la limite est atteinte."""
        request = self.request
        telephone = (request.POST.get('telephone') or '').strip()
        key = _cache_key(request, telephone)

        if cache.add(key, 1, LOGIN_ATTEMPT_WINDOW):
            failures = 1
        else:
            try:
                failures = cache.incr(key)
            except ValueError:
                cache.add(key, 1, LOGIN_ATTEMPT_WINDOW)
                failures = 1

        # On bloque à partir de la (LIMIT + 1)-ème tentative ratée :
        # l'utilisateur dispose donc bien de `LOGIN_ATTEMPT_LIMIT` essais.
        if failures > LOGIN_ATTEMPT_LIMIT:
            cache.set(f'{key}:blocked', True, LOGIN_ATTEMPT_WINDOW)
            logger.warning(
                "Blocage des connexions pour IP=%s telephone=%s (%s échecs)",
                _client_ip(request), normaliser_telephone(telephone), failures,
            )
            return HttpResponse(
                "<h1>429 - Trop de tentatives</h1>"
                "<p>Trop de tentatives de connexion échouées. "
                "Réessayez dans 5 minutes.</p>",
                status=429,
                content_type='text/html; charset=utf-8',
            )

        messages.error(
            request,
            "Numéro de téléphone ou mot de passe incorrect "
            f"({max(LOGIN_ATTEMPT_LIMIT - failures, 0)} tentative(s) restante(s)).",
        )
        return super().form_invalid(form)

    def form_valid(self, form):
        """Réinitialise le compteur à la connexion réussie."""
        request = self.request
        telephone = (request.POST.get('telephone') or '').strip()
        key = _cache_key(request, telephone)
        cache.delete(key)
        cache.delete(f'{key}:blocked')
        return super().form_valid(form)


def permission_requise(droit):
    """
    N'autorise l'accès que si l'utilisateur possède le droit demandé.

    `permission_de()` crée la ligne d'autorisation manquante avec des droits
    par défaut (lecture seule pour un utilisateur, lecture + écriture pour un
    administrateur), ce qui évite qu'un compte créé hors de l'administration
    se retrouve bloqué sans raison.

    Le compte désactivé est renvoyé vers la déconnexion : la session devient
    inutile et il est plus possible de rien écrire.

    En cas de refus, la session est fermée et l'utilisateur est renvoyé vers la
    page de connexion. Rediriger vers le tableau de bord serait une faute : le
    tableau de bord est lui-même protégé, cela créerait une boucle de
    redirection infinie.
    """
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('budget_app:login')

            permission = permission_de(request.user)
            if permission is not None and getattr(permission, droit, False):
                return vue(request, *args, **kwargs)

            # Aucune autorisation : on ferme la session et on explique.
            django_logout(request)
            if request.user.is_active:
                messages.error(
                    request,
                    "Votre compte ne dispose pas des autorisations nécessaires. "
                    "Contactez l'administrateur.",
                )
            else:
                messages.error(
                    request,
                    "Votre compte a été désactivé. Contactez l'administrateur.",
                )
            return redirect('budget_app:login')

        return enveloppe
    return decorateur


def _budget_selectionne(request):
    """
    Récupère le budget demandé via `?b=<id>`.

    Seuls les administrateurs peuvent naviguer dans l'historique des mois :
    un utilisateur classique voit toujours le budget le plus récent.
    """
    dernier = BudgetMensuel.objects.first()
    if not request.user.is_staff:
        return dernier

    budget_id = request.GET.get('b')
    if budget_id and budget_id.isdigit():
        return BudgetMensuel.objects.filter(pk=int(budget_id)).first() or dernier
    return dernier


@login_required
@permission_requise('peut_lire')
def dashboard(request):
    """
    Vue principale du tableau de bord.
    - Affiche le budget mensuel sélectionné (le plus récent par défaut)
    - Permet d'ajouter une dépense (utilisateur authentifié)
    - Calcule le total dépensé et le solde restant
    """
    budget = _budget_selectionne(request)

    total_depenses = 0
    reste = 0
    depenses = []
    budget_precedent = None
    budget_suivant = None
    form = DepenseForm()

    if budget:
        depenses = budget.depenses.select_related('utilisateur').all()
        total_depenses = budget.total_depenses()
        reste = budget.reste_budget()

        # Navigation dans l'historique (réservée aux administrateurs)
        if request.user.is_staff:
            budget_precedent = BudgetMensuel.objects.filter(
                created_at__lt=budget.created_at
            ).order_by('-created_at').first()
            budget_suivant = BudgetMensuel.objects.filter(
                created_at__gt=budget.created_at
            ).order_by('created_at').first()

    # Gestion du formulaire d'ajout de dépense
    if request.method == 'POST':
        if not budget:
            messages.error(
                request,
                "Aucun budget mensuel n'est défini. Contactez l'administrateur.",
            )
            return redirect('budget_app:dashboard')

        form = DepenseForm(request.POST)
        if form.is_valid():
            depense = form.save(commit=False)
            depense.budget = budget
            depense.utilisateur = request.user
            depense.save()
            messages.success(request, "Dépense ajoutée avec succès !")
            return redirect('budget_app:dashboard')

    # Évolution : dernier budget créé supérieur au budget courant ?
    budgets_total = BudgetMensuel.objects.count()

    context = {
        'budget': budget,
        'total_depenses': total_depenses,
        'reste': reste,
        'depenses': depenses,
        'form': form,
        'is_staff': request.user.is_staff,
        'budget_precedent': budget_precedent,
        'budget_suivant': budget_suivant,
        'budgets_total': budgets_total,
        'peut_naviguer': request.user.is_staff and budgets_total > 1,
        'categories': budget.resume_categories() if budget else [],
        'repartition_manquante': budget.repartition_incomplete() if budget else True,
    }
    return render(request, 'budget_app/dashboard.html', context)


@login_required
@require_POST
def supprimer_depense(request, depense_id):
    """
    Supprime une dépense.

    - La vue n'accepte que les requêtes POST (protection CSRF + pas de
      suppression par simple lien/clique droit).
    - Accessible UNIQUEMENT aux administrateurs (is_staff=True).
    """
    if not request.user.is_staff:
        return HttpResponseForbidden(
            "Action interdite : seuls les administrateurs peuvent supprimer "
            "une dépense."
        )

    depense = get_object_or_404(Depense, id=depense_id)
    designation = depense.designation
    depense.delete()
    logger.info(
        "Dépense supprimée : %s (par %s)", designation, request.user.username,
    )
    messages.success(request, f"La dépense '{designation}' a été supprimée.")
    return redirect('budget_app:dashboard')


@login_required
@permission_requise('peut_lire')
def depenses(request):
    """
    Onglet « Dépenses » : l'historique complet, tous mois confondus.

    Filtres disponibles :
      ?b=<id>      un mois précis (par défaut le plus récent)
      ?q=texte     recherche sur la désignation
      ?u=<id>      dépenses d'un utilisateur donné (réservé aux administrateurs)
    """
    budget = _budget_selectionne(request)
    budgets = BudgetMensuel.objects.all()

    depenses_requises = Depense.objects.select_related('budget', 'utilisateur')
    if budget:
        depenses_requises = depenses_requises.filter(budget=budget)

    recherche = (request.GET.get('q') or '').strip()
    if recherche:
        depenses_requises = depenses_requises.filter(designation__icontains=recherche)

    auteur = None
    if request.user.is_staff and request.GET.get('u', '').isdigit():
        auteur_id = int(request.GET['u'])
        auteur = User.objects.filter(pk=auteur_id).first()
        if auteur is not None:
            depenses_requises = depenses_requises.filter(utilisateur=auteur)

    depenses_requises = depenses_requises.order_by('-date', '-created_at')

    total = depenses_requises.aggregate(
        somme=Coalesce(montant_total(), ZERO),
    )['somme'] or 0

    context = {
        'budget': budget,
        'budgets': budgets,
        'depenses': depenses_requises,
        'total': total,
        'recherche': recherche,
        'auteur': auteur,
        'auteurs': User.objects.order_by('username') if request.user.is_staff else None,
        'profils_auteurs': (
            ProfilUtilisateur.objects.select_related('utilisateur').order_by('utilisateur__username')
            if request.user.is_staff else None
        ),
        'is_staff': request.user.is_staff,
        'onglet': 'depenses',
    }
    return render(request, 'budget_app/depenses.html', context)


@login_required
@permission_requise('peut_lire')
def statistiques(request):
    """
    Onglet « Statistiques » : où part l'argent, et qui le dépense.

    Trois lectures complémentaires :
      * répartition par poste (les désignations les plus coûteuses) ;
      * répartition par auteur ;
      * évolution mois par mois du montant dépensé.
    """
    budget = _budget_selectionne(request)

    perimetre = Depense.objects.select_related('utilisateur')
    if budget:
        perimetre = perimetre.filter(budget=budget)
    else:
        perimetre = None

    # --- Par poste ---------------------------------------------------
    par_poste = []
    if perimetre is not None:
        lignes = perimetre.values('designation').annotate(
            total=Coalesce(montant_total(), ZERO),
            nombre=Count('id'),
        ).order_by('-total')[:12]
        par_poste = list(lignes)

    # --- Par auteur --------------------------------------------------
    par_auteur = []
    if perimetre is not None:
        lignes = perimetre.values(
            'utilisateur__id',
            'utilisateur__username',
            'utilisateur__profil__telephone',
        ).annotate(
            total=Coalesce(montant_total(), ZERO),
            nombre=Count('id'),
        ).order_by('-total')
        for ligne in lignes:
            numero = ligne['utilisateur__profil__telephone']
            par_auteur.append({
                'id': ligne['utilisateur__id'],
                'username': ligne['utilisateur__username'],
                'telephone': formater_telephone(numero) if numero else '—',
                'total': ligne['total'],
                'nombre': ligne['nombre'],
            })

    # --- Évolution mensuelle ----------------------------------------
    evolution = []
    lignes = (
        Depense.objects
        .annotate(mois=TruncMonth('budget__created_at'))
        .values('mois')
        .annotate(total=Coalesce(montant_total(), ZERO))
        .order_by('mois')
    )
    for ligne in lignes:
        evolution.append({
            'mois': ligne['mois'],
            'total': ligne['total'],
            'libelle': ligne['mois'].strftime('%b %Y') if ligne['mois'] else '—',
        })

    total_general = sum(item['total'] for item in par_poste) or 1
    pic = max((item['total'] for item in par_poste), default=0) or 1
    pic_auteur = max((item['total'] for item in par_auteur), default=0) or 1
    pic_mois = max((item['total'] for item in evolution), default=0) or 1

    context = {
        'budget': budget,
        'par_poste': par_poste,
        'par_auteur': par_auteur,
        'evolution': evolution,
        'par_categorie': budget.resume_categories() if budget else [],
        'categories_actives': CategorieBudget.objects.filter(active=True),
        'repartition_manquante': budget.repartition_incomplete() if budget else True,
        'ecart_repartition': budget.ecart_repartition() if budget else Decimal('0.00'),
        'total_general': total_general,
        'pics': {'poste': pic, 'auteur': pic_auteur, 'mois': pic_mois},
        'nombre_depenses': perimetre.count() if perimetre is not None else 0,
        'onglet': 'statistiques',
    }
    return render(request, 'budget_app/statistiques.html', context)


@login_required
@permission_requise('peut_lire')
def repartition(request, budget_id):
    """
    Répartition du budget initial par catégorie — administrateurs seulement.

    GET  : affiche le formulaire, pré-rempli.
    POST : enregistre. La somme des montants doit être exactement égale au
    montant initial du budget ; sinon rien n'est enregistré et l'écart est
    indiqué, pour éviter de laisser un budget incohérent.
    """
    budget = get_object_or_404(BudgetMensuel, pk=budget_id)

    # Décision d'accès : la répartition du budget est une décision
    # d'administration. Elle est vérifiée ici, pas seulement dans le
    # gabarit, et un utilisateur non-admin reçoit une erreur 403 explicite
    # plutôt qu'une page qui laisse croire à une répartition vide.
    if not request.user.is_staff:
        return HttpResponseForbidden(
            "Action interdite : seuls les administrateurs peuvent répartir "
            "le budget par catégorie."
        )

    form = RepartitionForm(request.POST or None, budget=budget)

    if request.method == 'POST' and form.is_valid():
        valeurs = form.valeurs()
        total = sum(valeurs.values(), Decimal('0.00'))

        if total != budget.montant_initial:
            ecart = budget.montant_initial - total
            form.add_error(
                None,
                "La somme des catégories "
                f"({total:,.2f} Ar) doit être égale au budget initial "
                f"({budget.montant_initial:,.2f} Ar). ".replace(',', ' ')
                + f"Il manque {abs(ecart):,.2f} Ar. ".replace(',', ' ')
                + ("Retirez ce montant." if ecart > 0 else "Réduisez d'autant."),
            )
        else:
            with transaction.atomic():
                budget.repartitions.exclude(
                    categorie_id__in=valeurs.keys()
                ).delete()
                for categorie_id, montant in valeurs.items():
                    RepartitionCategorie.objects.update_or_create(
                        budget=budget,
                        categorie_id=categorie_id,
                        defaults={'montant': montant},
                    )
            logger.info(
                "Budget %s réparti par %s",
                budget.mois, request.user.username,
            )
            messages.success(
                request,
                f"Répartition enregistrée pour {budget.mois} "
                f"({total:,.2f} Ar sur {len(valeurs)} catégories).".replace(',', ' '),
            )
            return redirect(request.POST.get('suite') or 'budget_app:statistiques')

    return render(request, 'budget_app/repartition.html', {
        'budget': budget,
        'form': form,
        'categories': budget.resume_categories(),
        'onglet': 'statistiques',
    })


@login_required
@permission_requise('peut_lire')
def utilisateurs(request):
    """
    Onglet « Utilisateurs » : qui a accès à l'application.

    Tout le monde voit la liste (pour savoir qui enregistre les dépenses), mais
    seuls les administrateurs peuvent changer les droits : le contrôle est
    refait côté serveur au POST.
    """
    profils = ProfilUtilisateur.objects.select_related(
        'utilisateur', 'utilisateur__permission_budget'
    ).order_by('utilisateur__username')

    contexte = {
        'profils': profils,
        'onglet': 'utilisateurs',
        'is_staff': request.user.is_staff,
    }

    if request.method == 'POST' and request.user.is_staff:
        identifiant = request.POST.get('utilisateur')
        action = request.POST.get('action')
        permission = permission_de(request.user)

        if permission is not None and permission.peut_ecrire:
            if identifiant.isdigit():
                cible = User.objects.filter(pk=int(identifiant)).first()
                if cible is not None and cible != request.user:
                    if action == 'lire':
                        permission_cible = permission_de(cible)
                        permission_cible.peut_lire = not permission_cible.peut_lire
                        permission_cible.modifie_par = request.user
                        permission_cible.save()
                        messages.success(
                            request,
                            f"Autorisation de lecture de « {cible.username} » mise à jour.",
                        )
                    elif action == 'ecrire':
                        permission_cible = permission_de(cible)
                        permission_cible.peut_ecrire = not permission_cible.peut_ecrire
                        permission_cible.modifie_par = request.user
                        permission_cible.save()
                        messages.success(
                            request,
                            f"Autorisation d'écriture de « {cible.username} » mise à jour.",
                        )
                else:
                    messages.error(
                        request,
                        "Impossible de modifier ce compte.",
                    )
        else:
            messages.error(
                request,
                "Vous devez disposer du droit d'écriture pour modifier les accès.",
            )
        return redirect('budget_app:utilisateurs')

    contexte['profils'] = ProfilUtilisateur.objects.select_related(
        'utilisateur', 'utilisateur__permission_budget'
    ).order_by('utilisateur__username')
    return render(request, 'budget_app/utilisateurs.html', contexte)
