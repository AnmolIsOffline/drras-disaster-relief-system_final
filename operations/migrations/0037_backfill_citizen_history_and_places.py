from django.db import migrations

DISTRICTS = {
    'Amritsar','Barnala','Bathinda','Faridkot','Fatehgarh Sahib','Fazilka','Ferozepur',
    'Gurdaspur','Hoshiarpur','Jalandhar','Kapurthala','Ludhiana','Malerkotla','Mansa',
    'Moga','Sri Muktsar Sahib','Pathankot','Patiala','Rupnagar',
    'Sahibzada Ajit Singh Nagar','Sangrur','Shaheed Bhagat Singh Nagar','Tarn Taran',
}

def backfill_history_and_places(apps, schema_editor):
    Emergency = apps.get_model('operations', 'Emergency')
    Shelter = apps.get_model('operations', 'Shelter')
    Donation = apps.get_model('operations', 'Donation')
    DonationEvent = apps.get_model('operations', 'DonationEvent')
    SupportTicket = apps.get_model('operations', 'SupportTicket')
    SupportTicketEvent = apps.get_model('operations', 'SupportTicketEvent')
    db = schema_editor.connection.alias

    for model in (Emergency, Shelter):
        for row in model.objects.using(db).all().iterator():
            if row.district and row.address:
                continue
            parts=[part.strip() for part in row.location.split(',') if part.strip()]
            if parts and parts[-1].casefold()=='punjab':
                parts.pop()
            district=parts[-1] if parts and parts[-1] in DISTRICTS else ''
            address=', '.join(parts[:-1] if district else parts)
            changed=[]
            if not row.district and district: row.district=district; changed.append('district')
            if not row.address and address: row.address=address[:180]; changed.append('address')
            if changed: row.save(using=db, update_fields=changed)

    for donation in Donation.objects.using(db).all().iterator():
        # The project has no payment gateway. A legacy CONFIRMED label alone is
        # not evidence of payment, so retain it as a contribution submission.
        if donation.status=='CONFIRMED':
            donation.status='DEMO_RECORDED' if donation.demo else 'SUBMITTED'
            donation.confirmed_at=None
            donation.save(using=db, update_fields=['status','confirmed_at'])
        DonationEvent.objects.using(db).get_or_create(
            donation_id=donation.pk, event_type='IMPORTED', to_status=donation.status,
            defaults={'from_status':'CONFIRMED' if donation.status in ('DEMO_RECORDED','SUBMITTED') else '',
                      'note':'Existing contribution preserved. No payment proof was recorded during migration.'},
        )
    for ticket in SupportTicket.objects.using(db).all().iterator():
        SupportTicketEvent.objects.using(db).get_or_create(
            ticket_id=ticket.pk, event_type='IMPORTED',
            defaults={'detail':{'status':ticket.status,'priority':ticket.priority}},
        )

class Migration(migrations.Migration):
    dependencies=[('operations','0036_distinguish_legacy_demo_ledger_entries')]
    operations=[migrations.RunPython(backfill_history_and_places,migrations.RunPython.noop)]
