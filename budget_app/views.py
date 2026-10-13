import logging
import re
from decimal import Decimal
from functools import wraps
from urllib.parse import quote

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
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from decouple import config

from .models import (
    BudgetMensuel,
    CategorieBudget,
    Depense,
    Devis,
    PaiementDevis,
    ProfilUtilisateur,
    RepartitionCategorie,
    permission_de,
    peut_creer_devis,
    libelle_operateur,
    telephone_de,
)
from .forms import (
    ConnexionForm,
    DepenseForm,
    DevisForm,
    LigneDevisFormSetFactory,
    PaiementDevisForm,
    RepartitionForm,
    formater_devis,
)
from .pdf import generer_devis
from .telephone import formater_telephone, normaliser_telephone

logger = logging.getLogger(__name__)


def _slug(texte):
    """Nom de fichier sûr, dérivé du nom d'un devis."""
    garde = []
    for caractere in str(texte).lower():
        if caractere.isalnum():
            garde.append(caractere)
        elif garde and garde[-1] != '-':
            garde.append('-')
    return ''.join(garde).strip('-') or 'devis'

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


def _contexte_commun(request, **extra):
    """
    Contexte de base commun aux pages.

    `peut_devis` pilote l'affichage de l'onglet Devis dans la barre de
    navigation : il est évalué une seule fois par requête.
    """
    commun = {'peut_devis': peut_creer_devis(request.user)}
    commun.update(extra)
    return commun


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
      ?c=<id>      dépenses d'une catégorie donnée
      ?vue=groupe  un tableau par catégorie, avec un sous-total chacune

    La vue « groupe » sépare complètement les postes : des courses et des
    provisions sont deux budgeting différents, les mélanger dans une seule
    liste masque le poids de chacun.
    """
    budget = _budget_selectionne(request)
    budgets = BudgetMensuel.objects.all()

    depenses_requises = Depense.objects.select_related('budget', 'utilisateur', 'categorie')
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

    categorie_filtree = None
    if request.GET.get('c', '').isdigit():
        categorie_filtree = CategorieBudget.objects.filter(
            pk=int(request.GET['c'])
        ).first()
        if categorie_filtree is not None:
            depenses_requises = depenses_requises.filter(categorie=categorie_filtree)

    depenses_requises = depenses_requises.order_by('-date', '-created_at')

    total = depenses_requises.aggregate(
        somme=Coalesce(montant_total(), ZERO),
    )['somme'] or 0

    # --- Vue par catégorie : un bloc par poste, avec son sous-total ------
    groupes = []
    if request.GET.get('vue') == 'groupe':
        par_categorie = {}
        for depense in depenses_requises:
            cle = depense.categorie_id
            par_categorie.setdefault(cle, []).append(depense)
        for categorie in CategorieBudget.objects.filter(active=True).order_by('ordre', 'nom'):
            lignes = par_categorie.get(categorie.pk, [])
            if not lignes:
                continue
            groupes.append({
                'categorie': categorie,
                'depenses': lignes,
                'total': sum((d.montant_total for d in lignes), ZERO),
                'nombre': len(lignes),
            })
        # Les dépenses sans catégorie ne doivent pas disparaître : sinon la
        # vue « groupe » afficherait un total inférieur à celui annoncé.
        orphelines = par_categorie.get(None, [])
        if orphelines:
            groupes.append({
                'categorie': None,
                'depenses': orphelines,
                'total': sum((d.montant_total for d in orphelines), ZERO),
                'nombre': len(orphelines),
            })

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
        'vue_groupee': request.GET.get('vue') == 'groupe',
        'groupes': groupes,
        'categorie_filtree': categorie_filtree,
        'profils_categories': CategorieBudget.objects.filter(active=True).order_by('ordre', 'nom'),
        'is_staff': request.user.is_staff,
        'onglet': 'depenses',
        'peut_devis': peut_creer_devis(request.user),
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
        'peut_devis': peut_creer_devis(request.user),
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


def devis_requis():
    """
    Autorise l'accès à l'interface des devis.

    Le droit `peut_creer_devis` est une compétence distincte du droit
    d'écriture sur les dépenses : quelqu'un qui prépare un prévision ne doit
    pas pouvoir saisir de dépenses réelles par la même occasion.

    En cas de refus, la redirection vise le tableau de bord et non la liste
    des devis : celle-ci est protégée par le même contrôle, et y renvoyer
    créerait une boucle de redirection infinie.
    """
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('budget_app:login')
            if peut_creer_devis(request.user):
                return vue(request, *args, **kwargs)
            messages.error(
                request,
                "Votre compte ne dispose pas du droit de création de devis. "
                "Contactez l'administrateur.",
            )
            return redirect('budget_app:dashboard')
        return enveloppe
    return decorateur


def _devis_autorise(devis, utilisateur, *, modification=False):
    """Renvoie le devis si l'utilisateur y a droit, sinon None."""
    if modification:
        return devis if devis.est_modifiable_par(utilisateur) else None
    return devis if devis.est_visible_par(utilisateur) else None


def _paiement_money():
    """
    Coordonnées de paiement mobile money de l'administrateur (facultatif).

    Le numéro est renvoyé deux fois : brut, pour un lien `tel:` ou WhatsApp,
    et formaté (`038 41 601 33`) pour être affiché et recopié.
    """
    numero = config('MOBILE_MONEY_NUMERO', default='').strip()
    return {
        'numero': numero,
        'numero_affiche': formater_telephone(numero) or numero,
        'nom': config('MOBILE_MONEY_NOM', default='').strip(),
        # « mvola », « M'Vola », « TELMA » et « Yas » donnent tous le même
        # libellé affiché.
        'operateur': libelle_operateur(
            config('MOBILE_MONEY_OPERATEUR', default='').strip()
        ),
    }


@login_required
@devis_requis()
def devis_liste(request):
    """
    Historique des devis : ceux de l'utilisateur, plus ceux qu'on lui a
    partagés. La liste est ordonnée du plus récent au plus ancien.
    """
    mes_devis = (
        Devis.objects
        .filter(auteur=request.user)
        .prefetch_related('lignes', 'visible_par')
    )
    partages = (
        Devis.objects
        .filter(visible_par=request.user)
        .exclude(auteur=request.user)
        .select_related('auteur')
        .prefetch_related('lignes')
    )
    # Un administrateur voit en plus tout ce qui existe.
    if request.user.is_staff:
        partages = (
            Devis.objects
            .exclude(auteur=request.user)
            .select_related('auteur')
            .prefetch_related('lignes')
        )

    contexte = {
        'mes_devis': mes_devis,
        'partages': partages,
        'onglet': 'devis',
        'peut_devis': True,
        'total_mes_devis': sum((d.total for d in mes_devis), Decimal('0.00')),
    }
    return render(request, 'budget_app/devis_liste.html', contexte)


@login_required
@devis_requis()
def devis_creer(request):
    """Nouveau devis : le nom, puis les lignes saisies à la demande."""
    if request.method == 'POST':
        form = DevisForm(request.POST)
        formset = LigneDevisFormSetFactory(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                devis = form.save(commit=False)
                devis.auteur = request.user
                devis.save()
                formset.instance = devis
                lignes = formset.save(commit=False)
                for numero, ligne in enumerate(lignes):
                    ligne.ordre = numero
                    ligne.save()
                formset.save_m2m()  # visible_par
            messages.success(
                request,
                f"Devis « {devis.nom} » enregistré "
                f"({devis.total:,.2f} Ar).".replace(',', ' '),
            )
            return redirect('budget_app:devis_detail', devis_id=devis.pk)
    else:
        form = DevisForm()
        formset = LigneDevisFormSetFactory()

    return render(request, 'budget_app/devis_form.html', {
        'form': form,
        'formset': formset,
        'nouveau': True,
        'onglet': 'devis',
        'peut_devis': True,
    })


@login_required
@devis_requis()
def devis_modifier(request, devis_id):
    """Modification d'un devis : l'auteur et les administrateurs seulement."""
    devis = get_object_or_404(Devis, pk=devis_id)
    if devis.est_modifiable_par(request.user):
        messages.error(
            request,
            "Seul l'auteur de ce devis (ou un administrateur) peut le modifier.",
        )
        return redirect('budget_app:devis_detail', devis_id=devis.pk)

    if request.method == 'POST':
        form = DevisForm(request.POST, instance=devis)
        formset = LigneDevisFormSetFactory(request.POST, instance=devis)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                devis = form.save()
                formset.instance = devis
                lignes = formset.save(commit=False)
                for numero, ligne in enumerate(lignes):
                    ligne.save()
                formset.save_m2m()
            messages.success(
                request,
                f"Devis « {devis.nom} » mis à jour.".format(
                    nom=devis.nom,
                ),
            )
            return redirect('budget_app:devis_detail', devis_id=devis.pk)
    else:
        form = DevisForm(instance=devis)
        formset = LigneDevisFormSetFactory(instance=devis)

    return render(request, 'budget_app/devis_form.html', {
        'form': form,
        'formset': formset,
        'devis': devis,
        'nouveau': False,
        'onglet': 'devis',
        'peut_devis': True,
    })


@login_required
@devis_requis()
@require_POST
def devis_supprimer(request, devis_id):
    devis = get_object_or_404(Devis, pk=devis_id)
    if not devis.est_modifiable_par(request.user):
        return HttpResponseForbidden(
            "Action interdite : seul l'auteur de ce devis peut le supprimer."
        )
    nom = devis.nom
    devis.delete()
    messages.success(request, f"Le devis « {nom} » a été supprimé.")
    return redirect('budget_app:devis_liste')


@login_required
@permission_requise('peut_lire')
def devis_detail(request, devis_id):
    """Consultation d'un devis partagé, et actions sur ses lignes."""
    devis = get_object_or_404(
        Devis.objects.select_related('auteur').prefetch_related('lignes', 'visible_par'),
        pk=devis_id,
    )
    if not devis.est_visible_par(request.user):
        # 404 plutôt que 403 : ne pas révéler l'existence d'un devis
        # simplement non partagé.
        raise Http404("Ce devis n'existe pas ou n'est pas partagé avec vous.")

    modifiable = devis.est_modifiable_par(request.user)
    partageable = (
        ProfilUtilisateur.objects
        .select_related('utilisateur')
        .order_by('utilisateur__username')
    )

    if request.method == 'POST' and modifiable:
        return devis_action(request, devis)

    return render(request, 'budget_app/devis_detail.html', {
        'devis': devis,
        'modifiable': modifiable,
        'partageable': partageable,
        # Identifiants des comptes déjà cochés : le gabarit ne peut pas
        # tester l'appartenance à une relation, la vue prépare la liste.
        'partages_ids': list(devis.visible_par.values_list('id', flat=True)),
        'paiements': devis.paiements.select_related('declare_par', 'confirme_par'),
        'paiement_form': PaiementDevisForm(devis=devis),
        'mobile_money': _paiement_money(),
        'onglet': 'devis',
        'peut_devis': peut_creer_devis(request.user),
    })


def devis_action(request, devis):
    """Actions ponctuelles depuis la fiche : partage ou suppression."""
    action = request.POST.get('action')

    if action == 'partager':
        identifiants = request.POST.getlist('visible_par')
        devis.visible_par.set(
            User.objects.filter(pk__in=[i for i in identifiants if str(i).isdigit()])
        )
        partages = devis.visible_par.count()
        messages.success(
            request,
            f"Partage mis à jour ({partages} personne"
            f"{'s' if partages > 1 else ''}).".format(partages=partages),
        )

    elif action == 'supprimer':
        nom = devis.nom
        devis.delete()
        messages.success(request, f"Le devis « {nom} » a été supprimé.")
        return redirect('budget_app:devis_liste')

    return redirect('budget_app:devis_detail', devis_id=devis.pk)


@login_required
@permission_requise('peut_lire')
def devis_pdf(request, devis_id):
    """Téléchargement du devis au format PDF."""
    devis = get_object_or_404(Devis.objects.prefetch_related('lignes'), pk=devis_id)
    if not devis.est_visible_par(request.user):
        raise Http404("Ce devis n'existe pas ou n'est pas partagé avec vous.")

    contenu = generer_devis(
        devis,
        contact={
            'nom': f"{request.user.get_full_name() or request.user.username}",
            'telephone': telephone_de(request.user),
            'email': request.user.email,
        },
        mobile_money=_paiement_money(),
    )
    if contenu is None:
        messages.error(
            request,
            "La génération de PDF n'est pas disponible sur ce serveur. "
            "Utilisez l'export ou l'impression de la page.",
        )
        return redirect('budget_app:devis_detail', devis_id=devis.pk)

    nom_fichier = f"devis-{_slug(devis.nom)}.pdf"
    reponse = HttpResponse(contenu, content_type='application/pdf')
    reponse['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    reponse['Content-Length'] = len(contenu)
    return reponse


@login_required
@permission_requise('peut_lire')
def devis_whatsapp(request, devis_id):
    """
    Ouvre WhatsApp avec le récapitulatif du devis.

    WhatsApp n'accepte pas d'envoyer un fichier depuis un simple lien web :
    cela demanderait un compte WhatsApp Business et un jeton d'API. On
    transmet donc le texte, et le PDF reste à télécharger puis à joindre
    manuellement — c'est la limite du canal, pas un oubli.
    """
    devis = get_object_or_404(Devis.objects.prefetch_related('lignes'), pk=devis_id)
    if not devis.est_visible_par(request.user):
        raise Http404("Ce devis n'existe pas ou n'est pas partagé avec vous.")

    destinataire = (config('WHATSAPP_ADMIN', default='261384160133')
                    .strip().replace(' ', ''))
    lignes = '\n'.join(
        f"- {ligne.objet} : {ligne.quantite} x "
        f"{formater_devis(ligne.prix_unitaire)} Ar = {formater_devis(ligne.total)} Ar"
        for ligne in devis.lignes.all()
    )
    reste = devis.reste_a_payer()
    texte = (
        f"DEVIS — {devis.nom}\n"
        f"Date : {devis.date.strftime('%d/%m/%Y')}\n"
        f"Établi par : {devis.auteur.username}\n"
        f"--------------------------------\n"
        f"{lignes}\n"
        f"--------------------------------\n"
        f"TOTAL : {formater_devis(devis.total)} Ar\n"
        + (f"Déjà réglé : {formater_devis(devis.total - reste)} Ar\n"
           if devis.total != reste else '')
        + f"Reste à régler : {formater_devis(reste)} Ar\n"
        + (f"\nMerci de joindre le PDF du devis.\n"
           f"Consultation en ligne : {request.build_absolute_uri(reverse('budget_app:devis_detail', args=[devis.pk]))}"
           if reste else "")
    )

    return redirect(f"https://wa.me/{destinataire}?text={quote(texte)}")


@login_required
@permission_requise('peut_lire')
@require_POST
def devis_paiement_declarer(request, devis_id):
    """Un utilisateur déclare avoir envoyé un montant par mobile money."""
    devis = get_object_or_404(Devis, pk=devis_id)
    if not devis.est_visible_par(request.user):
        raise Http404("Ce devis n'existe pas ou n'est pas partagé avec vous.")

    form = PaiementDevisForm(request.POST, devis=devis)
    if form.is_valid():
        paiement = form.save(commit=False)
        paiement.devis = devis
        paiement.declare_par = request.user
        paiement.save()
        messages.success(
            request,
            "Paiement déclaré. L'administrateur doit le vérifier avant qu'il "
            "ne soit pris en compte.",
        )
    else:
        messages.error(request, "Déclaration incomplète : vérifiez les montants.")
    return redirect('budget_app:devis_detail', devis_id=devis.pk)


@login_required
@require_POST
def devis_paiement_valider(request, devis_id, paiement_id):
    """L'administrateur valide (ou annule) une déclaration de paiement."""
    if not request.user.is_staff:
        return HttpResponseForbidden(
            "Action réservée aux administrateurs."
        )
    devis = get_object_or_404(Devis, pk=devis_id)
    paiement = get_object_or_404(PaiementDevis, pk=paiement_id, devis=devis)

    paiement.confirme = not paiement.confirme
    paiement.confirme_par = request.user if paiement.confirme else None
    paiement.save(update_fields=['confirme', 'confirme_par'])

    messages.success(
        request,
        "Paiement validé." if paiement.confirme else "Validation annulée.",
    )
    return redirect('budget_app:devis_detail', devis_id=devis.pk)


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
        'peut_devis': peut_creer_devis(request.user),
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
