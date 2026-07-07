from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0013_popupoffer_image'),
    ]

    operations = [
        migrations.AlterField(
            model_name='popupoffer',
            name='title',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='popupoffer',
            name='subtitle',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AlterField(
            model_name='popupoffer',
            name='badge_text',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AlterField(
            model_name='popupoffer',
            name='discount_text',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
