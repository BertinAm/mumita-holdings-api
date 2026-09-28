from django.db import migrations

GROUPS = ('admins', 'publishers')


def forwards(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in GROUPS:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    """The two realms (PLATFORM-CONTRACT "Accounts and logins")."""

    dependencies = [('accounts', '0001_initial'), ('auth', '0012_alter_user_first_name_max_length')]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
