import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import BudgetMensuel, Depense
from .forms import ConnexionForm, DepenseForm
from .telephone import normaliser_telephone

logger = logging.getLogger(__name__)

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
