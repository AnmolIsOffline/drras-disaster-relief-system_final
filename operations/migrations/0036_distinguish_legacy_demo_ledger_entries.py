from django.db import migrations

def distinguish_ledger_rows(apps, schema_editor):
    Donation = apps.get_model('operations', 'Donation')
    FundTransaction = apps.get_model('operations', 'FundTransaction')
    db = schema_editor.connection.alias
    legacy_ids = FundTransaction.objects.using(db).filter(
        donation_id__isnull=False, kind='DEMO_DONATION', demo=True,
    ).values_list('donation_id', flat=True)
    Donation.objects.using(db).filter(pk__in=legacy_ids, demo=True, status='SUBMITTED').update(
        status='DEMO_RECORDED', confirmed_at=None,
    )

class Migration(migrations.Migration):
    dependencies = [('operations', '0035_deliveryrecord_demo')]
    operations = [migrations.RunPython(distinguish_ledger_rows, migrations.RunPython.noop)]
