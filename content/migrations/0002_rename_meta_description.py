from django.db import migrations

LANGS = ('', '_en', '_fr', '_sw', '_es', '_zh', '_pt')


class Migration(migrations.Migration):
    """meta_description becomes seo_description (PLATFORM-CONTRACT API
    naming), for the base column and every locale column."""

    dependencies = [('content', '0001_initial')]

    operations = [
        migrations.RenameField('post', f'meta_description{suffix}', f'seo_description{suffix}') for suffix in LANGS
    ]
