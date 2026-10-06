from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'budget_app'

urlpatterns = [
    # Tableau de bord principal
    path('', views.dashboard, name='dashboard'),

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
]