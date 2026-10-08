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