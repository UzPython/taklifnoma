import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lamp", "0003_callsignal_guestmessage_guestpresence"),
    ]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="venue_map_url",
            field=models.URLField(
                blank=True,
                max_length=500,
                validators=[
                    django.core.validators.URLValidator(schemes=["http", "https"])
                ],
                verbose_name="Xarita havolasi",
            ),
        ),
    ]
