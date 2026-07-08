from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0017_add_promo_fields_to_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='cancelrequest',
            name='admin_response',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.CreateModel(
            name='ContactMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('email', models.EmailField(max_length=254)),
                ('subject', models.CharField(blank=True, default='', max_length=200)),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
