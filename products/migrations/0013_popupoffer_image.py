from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0012_order_payment_screenshot_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='popupoffer',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='popup_offers/'),
        ),
    ]
