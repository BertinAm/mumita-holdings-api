from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'
    verbose_name = 'Dashboard accounts'

    def ready(self):
        from common import checks  # noqa: F401  (registers the deploy checks)
