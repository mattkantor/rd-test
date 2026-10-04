import uuid

from django.db import migrations, models


def backfill(apps, schema_editor):
    for site in apps.get_model("web", "Site").objects.all():
        site.public_id = uuid.uuid4()
        site.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0007_snapshot_metrics'),
    ]

    # Added nullable, filled row by row, then made unique: a default on the AddField would give every row the same UUID.
    operations = [
        migrations.AddField(model_name='site', name='public_id', field=models.UUIDField(null=True, editable=False)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(model_name='site', name='public_id',
                              field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
    ]
