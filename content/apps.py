from django.apps import AppConfig


class ContentConfig(AppConfig):
    name = 'content'

    def ready(self):
        from . import images  # noqa: F401  (registers the media clean-up signal)
