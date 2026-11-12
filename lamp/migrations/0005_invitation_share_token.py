import uuid

from django.db import migrations, models


def populate_share_tokens(apps, schema_editor):
    Invitation = apps.get_model('lamp', 'Invitation')
    for invitation in Invitation.objects.all():
        invitation.share_token = uuid.uuid4()
        invitation.save(update_fields=['share_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('lamp', '0004_invitation_venue_map_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitation',
            name='share_token',
            field=models.UUIDField(
                db_index=True,
                default=None,
                editable=False,
                null=True,
                verbose_name='Umumiy havola tokeni',
            ),
        ),
        migrations.RunPython(populate_share_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='invitation',
            name='share_token',
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='Umumiy havola tokeni',
            ),
        ),
    ]
