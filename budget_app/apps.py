from django.apps import AppConfig


class BudgetAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'budget_app'
    verbose_name = 'Gestion de Budget'

    def ready(self):
        from . import signals  # noqa: F401
