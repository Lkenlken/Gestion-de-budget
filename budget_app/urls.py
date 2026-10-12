from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import pwa

app_name = 'budget_app'

urlpatterns = [
    # Tableau de bord principal
    path('', views.dashboard, name='dashboard'),

    # Onglets de navigation
    path('depenses/', views.depenses, name='depenses'),
    path('statistiques/', views.statistiques, name='statistiques'),
    path('utilisateurs/', views.utilisateurs, name='utilisateurs'),

    # Devis (création, historique, partage, PDF, paiement)
    path('devis/', views.devis_liste, name='devis_liste'),
    path('devis/nouveau/', views.devis_creer, name='devis_creer'),
    path('devis/<int:devis_id>/', views.devis_detail, name='devis_detail'),
    path('devis/<int:devis_id>/modifier/', views.devis_modifier, name='devis_modifier'),
    path('devis/<int:devis_id>/supprimer/', views.devis_supprimer, name='devis_supprimer'),
    path('devis/<int:devis_id>/pdf/', views.devis_pdf, name='devis_pdf'),
    path('devis/<int:devis_id>/whatsapp/', views.devis_whatsapp, name='devis_whatsapp'),
    path('devis/<int:devis_id>/paiement/', views.devis_paiement_declarer,
         name='devis_paiement_declarer'),
    path('devis/<int:devis_id>/paiement/<int:paiement_id>/valider/',
         views.devis_paiement_valider, name='devis_paiement_valider'),

    # Répartition du budget par catégorie (administrateurs seulement)
    path('budget/<int:budget_id>/repartition/', views.repartition,
         name='repartition'),

    # Suppression de dépense (admin only, POST uniquement)
    path('depense/<int:depense_id>/supprimer/', views.supprimer_depense,
         name='supprimer_depense'),

    # Authentification
    # ThrottledLoginView : limite les tentatives de connexion répétées.
    path('login/', views.ThrottledLoginView.as_view(
        redirect_authenticated_user=True
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(
        next_page='budget_app:login'
    ), name='logout'),

    # Application installable (PWA) : servis à la racine pour que la portée
    # du service worker couvre tout le site.
    path('manifest.webmanifest', pwa.manifest, name='manifest'),
    path('sw.js', pwa.service_worker, name='service_worker'),
]