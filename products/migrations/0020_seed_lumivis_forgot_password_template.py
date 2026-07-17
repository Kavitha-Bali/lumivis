from django.db import migrations


def seed_lumivis_forgot_password(apps, schema_editor):
    MailTemplates = apps.get_model('messaging', 'MailTemplates')
    MailTemplates.objects.get_or_create(
        template_name='lumivis_forgot_password',
        defaults={
            'template_path': 'mail/lumivis_forgot_password.html',
            'description': 'Lumivis-branded forgot-password email (dark theme, matches site UI).',
            'input_variable_values': {
                'reset_link': 'http://localhost:8000/reset-password/<uidb64>/<token>/',
                'logo_url': 'http://localhost:8000/static/logoo.png',
            },
            'is_active': True,
        },
    )


def unseed_lumivis_forgot_password(apps, schema_editor):
    MailTemplates = apps.get_model('messaging', 'MailTemplates')
    MailTemplates.objects.filter(template_name='lumivis_forgot_password').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0019_productimage'),
        ('messaging', '0002_alter_outbounds_to_mail'),
    ]

    operations = [
        migrations.RunPython(seed_lumivis_forgot_password, unseed_lumivis_forgot_password),
    ]
