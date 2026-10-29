from django.db import migrations


def normalize_unverified_failures(apps, schema_editor):
    Donation = apps.get_model('operations', 'Donation')
    DonationEvent = apps.get_model('operations', 'DonationEvent')
    db = schema_editor.connection.alias
    rows = Donation.objects.using(db).filter(status='FAILED', provider_reference='')
    for donation in rows.iterator():
        donation.status = 'REJECTED'
        donation.save(using=db, update_fields=['status'])
        DonationEvent.objects.using(db).get_or_create(
            donation_id=donation.pk,
            event_type='IMPORTED',
            to_status='REJECTED',
            defaults={
                'from_status': 'FAILED',
                'note': 'Legacy unverified record normalized to recipient rejection; no payment provider reference existed.',
            },
        )


class Migration(migrations.Migration):
    dependencies = [('operations', '0037_backfill_citizen_history_and_places')]
    operations = [migrations.RunPython(normalize_unverified_failures, migrations.RunPython.noop)]
