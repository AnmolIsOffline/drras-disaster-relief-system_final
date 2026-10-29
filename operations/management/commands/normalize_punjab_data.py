from collections import defaultdict
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from operations.geography import is_punjab_coordinate
from operations.models import (
    Advisory, AdvisoryEvent, AllocationAuthorization, AllocationAuthorizationEvent,
    Assignment, AssignmentEvent, Dispatch, DispatchEvent, DonationCampaign,
    Emergency, EmergencyEvent, EventLog, FundTransaction, Inventory,
    InventoryMovement, Notification, Organization, Profile, SafetyTraining,
    Shelter, ShelterEvent, SupportReply, SupportTicket, SystemPreference,
    Vehicle, ZoneApplication, ZoneApplicationEvent,
)

User = get_user_model()
TEST_PASSWORD = 'PunjabRelief2026!'

ROLE_NAMES = {
    'ADMIN': ['Harpreet Singh'],
    'CITIZEN': [
        'Amritpal Singh', 'Jasleen Kaur', 'Gurkirat Singh', 'Simranjit Kaur',
        'Dilpreet Singh', 'Navjot Kaur', 'Arshdeep Singh', 'Kiranpreet Kaur',
        'Harman Singh', 'Manpreet Kaur', 'Prabhjot Singh', 'Sandeep Kaur',
        'Rupinder Singh', 'Amanpreet Kaur', 'Lakhwinder Singh', 'Ravneet Kaur',
        'Jatinder Singh', 'Taranjit Kaur', 'Kuldeep Singh', 'Rajwinder Kaur',
        'Eknoor Singh', 'Balpreet Kaur', 'Gagandeep Singh', 'Sukhdeep Kaur',
        'Inderjit Singh', 'Pavneet Kaur', 'Balwinder Kaur', 'Harleen Kaur',
        'Satnam Singh', 'Jasbir Kaur', 'Gurleen Kaur', 'Tejinder Singh',
        'Parminder Kaur', 'Kirandeep Singh', 'Jagdeep Kaur', 'Amandeep Singh',
        'Ranjit Kaur', 'Gurpreet Kaur', 'Harjot Singh', 'Nimrat Kaur',
        'Birinder Singh',
    ],
    'GOV': ['Gurpreet Singh', 'Navdeep Singh', 'Jaskaran Singh'],
    'NGO': ['Simran Kaur', 'Amandeep Brar', 'Manpreet Gill', 'Kirandeep Gill', 'Jaspreet Kaur'],
    'GOV_VOL': ['Amritpal Kaur', 'Sukhdeep Singh', 'Dilpreet Kaur', 'Mandeep Singh', 'Raghav Singh', 'Charanjit Kaur'],
    'GOV_DRIVER': ['Sukhwinder Singh', 'Maninder Singh', 'Jasleen Singh'],
    'NGO_VOL': ['Harsimran Kaur', 'Gurleen Singh', 'Prabhjot Kaur', 'Baljinder Singh', 'Simranjit Singh', 'Rupinder Kaur', 'Lovepreet Singh', 'Gagandeep Kaur', 'Jasdeep Singh', 'Kirat Kaur'],
    'NGO_DRIVER': ['Ravinder Singh', 'Navjot Gill', 'Balpreet Singh', 'Tavleen Kaur'],
}
ROLE_EMAIL = {
    'ADMIN': 'admin', 'CITIZEN': 'citizen', 'GOV': 'gov.official',
    'NGO': 'ngo.coordinator', 'GOV_VOL': 'gov.volunteer',
    'GOV_DRIVER': 'gov.driver', 'NGO_VOL': 'ngo.volunteer',
    'NGO_DRIVER': 'ngo.driver',
}

PLACES = [
    ('Ludhiana', 'Civil Lines', 30.901, 75.857),
    ('Amritsar', 'Lawrence Road', 31.634, 74.873),
    ('Jalandhar', 'Model Town', 31.326, 75.576),
    ('Patiala', 'Baradari Gardens', 30.340, 76.386),
    ('Bathinda', 'Ajit Road', 30.211, 74.945),
    ('Moga', 'Ghal Kalan Road', 30.816, 75.172),
    ('Sangrur', 'Nabha Gate', 30.245, 75.842),
    ('Kapurthala', 'Sultanpur Lodhi Road', 31.380, 75.384),
    ('Hoshiarpur', 'Model Town', 31.532, 75.912),
    ('Ferozepur', 'Mall Road', 30.933, 74.622),
]
ORGANIZATIONS = {
    1: ('Punjab State Relief Directorate', 'GOV', 'Ludhiana District'),
    2: ('Majha Community Support Network', 'NGO', 'Amritsar and Tarn Taran'),
    3: ('Malwa Emergency Response Society', 'NGO', 'Bathinda and Moga'),
    4: ('Punjab State Response Cell', 'GOV', 'Punjab'),
    5: ('Punjab Community Relief Network', 'NGO', 'Central Punjab'),
    6: ('North Punjab Relief Initiative', 'NGO', 'Pathankot and Gurdaspur'),
}
SHELTERS = [
    ('Civil Lines Family Shelter', 'Ludhiana'),
    ('Lawrence Road Relief Centre', 'Amritsar'),
    ('Model Town Community Shelter', 'Jalandhar'),
    ('Baradari Relief Hub', 'Patiala'),
    ('Ajit Road Family Centre', 'Bathinda'),
    ('Ghal Kalan Community Shelter', 'Moga'),
    ('Nabha Gate Relief Centre', 'Sangrur'),
    ('Sultanpur Lodhi Family Hub', 'Kapurthala'),
]
ADVISORY_TEXT = [
    ('Monsoon readiness guidance', 'Ludhiana', 'Keep essential medicines, drinking water, and documents in a ready-to-carry bag. Follow verified district instructions if conditions change.'),
    ('River safety and preparedness', 'Amritsar', 'Avoid crossing fast-moving water and keep children away from canal banks. Contact local responders if you need assistance.'),
    ('Relief desk information', 'Jalandhar', 'Residents can contact their district relief desk for shelter, water, and referral information. Carry essential medicines when possible.'),
    ('Road access coordination note', 'Sangrur', 'Response teams should confirm road access with local authorities before moving supplies. This item is an unpublished working note.'),
]


def rewrite_text(value):
    if not isinstance(value, str):
        return value
    replacements = {
        'Maharashtra': 'Punjab', 'Konkan Division': 'Majha region', 'Konkan': 'Majha region',
        'Pune Division': 'Ludhiana district', 'Pune': 'Ludhiana', 'Satara': 'Patiala',
        'Ratnagiri': 'Amritsar', 'Chiplun': 'Moga', 'Raigad': 'Sangrur',
        'Khed': 'Jalandhar', 'Mahad': 'Ferozepur', 'Rajapur': 'Hoshiarpur',
        'Pimpri': 'Ludhiana', 'Ajra': 'Pathankot', 'Kolhapur': 'Mansa',
        'DEMO SAMPLE': '', 'DEMO-SEED: ': '', 'DEMO: ': '', 'DEMO:': '',
        'Fictional demonstration records are shown for training and evaluation.': '',
        'Fictional sample record.': '', 'Fictional demonstration incident; seeded status snapshot.': 'Operational status recorded.',
        'Fictional training task.': 'Response coordination task.',
        'Fictional sample dispatch.': 'Relief dispatch.',
        'Fictional training dispatch.': 'Relief dispatch.',
        'Demonstration records are labeled in the database': '',
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r'\bDemo\b|\bDEMO\b|\bsample\b|\bSample\b|\bfictional\b|\bFictional\b', '', value)
    value = re.sub(r'\s{2,}', ' ', value)
    value = re.sub(r'\s+,', ',', value)
    return value.strip(' -:')


def rewrite_json(value):
    if isinstance(value, str):
        return rewrite_text(value)
    if isinstance(value, list):
        return [rewrite_json(item) for item in value]
    if isinstance(value, dict):
        return {key: rewrite_json(item) for key, item in value.items()}
    return value


class Command(BaseCommand):
    help = 'Normalize existing seeded DRRAS records to Punjab identities and locations without replacing rows.'

    @transaction.atomic
    def handle(self, *args, **options):
        changed = 0
        profile_rows = list(Profile.objects.select_related('user').filter(
            Q(user__email__iendswith='@drras.demo') | Q(details__seed_key__isnull=False)
        ).order_by('user_id'))
        by_role = defaultdict(int)
        for profile in profile_rows:
            names = ROLE_NAMES.get(profile.role, [])
            by_role[profile.role] += 1
            index = by_role[profile.role] - 1
            if index >= len(names):
                continue
            old_login = (profile.details or {}).get('seed_key') or profile.user.username
            first, *last = names[index].split()
            seq = index + 1
            local_part = f"{first}.{'.'.join(last)}.{ROLE_EMAIL[profile.role]}"
            if profile.role in ('CITIZEN', 'GOV_VOL', 'GOV_DRIVER', 'NGO_VOL', 'NGO_DRIVER'):
                local_part += f'{seq:02d}'
            email = f'{local_part.lower()}@drras.local'
            user = profile.user
            if user.username != email or user.email != email or user.first_name != first or user.last_name != ' '.join(last):
                user.username = email
                user.email = email
                user.first_name = first
                user.last_name = ' '.join(last)
                if not user.check_password(TEST_PASSWORD):
                    user.set_password(TEST_PASSWORD)
                user.save(update_fields=['username', 'email', 'first_name', 'last_name', 'password'])
                changed += 1
            details = dict(profile.details or {})
            if details.get('seed_key') != old_login:
                details['seed_key'] = old_login
                profile.details = details
                profile.save(update_fields=['details'])
                changed += 1

        for index, org in enumerate(Organization.objects.filter(demo=True).order_by('pk')):
            if index >= len(ORGANIZATIONS):
                continue
            name, kind, zone = list(ORGANIZATIONS.values())[index]
            if (org.name, org.kind, org.zone) != (name, kind, zone):
                org.name, org.kind, org.zone = name, kind, zone
                org.save(update_fields=['name', 'kind', 'zone'])
                changed += 1

        demo_emergencies = list(Emergency.objects.filter(demo=True).order_by('pk'))
        for index, row in enumerate(demo_emergencies):
            district, locality, latitude, longitude = PLACES[index % len(PLACES)]
            location = f'{locality}, {district}, Punjab'
            description = row.description
            if 'Demonstration incident' in description or 'Fictional' in description or 'sample' in description.lower():
                description = f'Response coordination entry: households in {district} may need {row.category.lower()} relief support. Verify current needs before dispatch.'
            reference = row.reference
            if reference.startswith('DR-DEMO-'):
                reference = reference.replace('DR-DEMO-', 'PB-REL-')
            elif reference.startswith('PB-DEMO-'):
                reference = reference.replace('PB-DEMO-', 'PB-OPS-')
            values = (reference, location, latitude, longitude, description)
            if (row.reference, row.location, row.latitude, row.longitude, row.description) != values:
                row.reference, row.location, row.latitude, row.longitude, row.description = values
                row.save(update_fields=['reference', 'location', 'latitude', 'longitude', 'description'])
                changed += 1

        for index, row in enumerate(Shelter.objects.filter(demo=True).order_by('pk')):
            name, district = SHELTERS[index % len(SHELTERS)]
            place = next(place for place in PLACES if place[0] == district)
            location = f'{place[1]}, {district}, Punjab'
            if (row.name, row.location, row.latitude, row.longitude) != (name, location, place[2], place[3]):
                row.name, row.location, row.latitude, row.longitude = name, location, place[2], place[3]
                row.save(update_fields=['name', 'location', 'latitude', 'longitude', 'updated_at'])
                changed += 1

        for index, row in enumerate(Advisory.objects.filter(demo=True).order_by('pk')):
            title, district, body = ADVISORY_TEXT[index % len(ADVISORY_TEXT)]
            location = f'{district}, Punjab'
            if (row.title, row.location, row.body) != (title, location, body):
                row.title, row.location, row.body = title, location, body
                row.save(update_fields=['title', 'location', 'body', 'updated_at'])
                changed += 1

        for index, vehicle in enumerate(Vehicle.objects.filter(organization__demo=True).order_by('pk'), 1):
            plate = f'PB-DR-{index:04d}'
            if vehicle.registration != plate:
                vehicle.registration = plate
                vehicle.save(update_fields=['registration'])
                changed += 1

        for index, item in enumerate(Inventory.objects.filter(organization__demo=True).order_by('pk')):
            district, locality, *_ = PLACES[index % len(PLACES)]
            warehouse = f'{district} Relief Warehouse'
            address = f'{locality}, {district}, Punjab'
            if item.warehouse != warehouse or item.warehouse_location != address:
                item.warehouse, item.warehouse_location = warehouse, address
                item.save(update_fields=['warehouse', 'warehouse_location', 'updated_at'])
                changed += 1

        for index, dispatch in enumerate(Dispatch.objects.filter(emergency__demo=True).select_related('emergency').order_by('pk')):
            district = dispatch.emergency.location.split(',')[-2].strip()
            pickup = f'{district} Relief Hub, {district}, Punjab'
            destination = dispatch.emergency.location
            if dispatch.pickup_location != pickup or dispatch.destination != destination:
                dispatch.pickup_location, dispatch.destination = pickup, destination
                dispatch.save(update_fields=['pickup_location', 'destination', 'updated_at'])
                changed += 1

        # Keep seeded campaign ownership and donor ledger relationships unchanged.
        for index, campaign in enumerate(DonationCampaign.objects.filter(demo=True).order_by('pk'), 1):
            name = rewrite_text(campaign.name)
            recipient = rewrite_text(campaign.recipient)
            description = rewrite_text(campaign.description)
            if not name or name == campaign.name:
                name = f'{campaign.organization.name if campaign.organization else "Punjab Relief"} Supply Campaign {index}'
            if (campaign.name, campaign.recipient, campaign.description) != (name, recipient, description):
                campaign.name, campaign.recipient, campaign.description = name, recipient, description
                campaign.save(update_fields=['name', 'recipient', 'description'])
                changed += 1

        text_models = [
            (EmergencyEvent.objects.filter(emergency__demo=True), ('note',)),
            (Assignment.objects.filter(emergency__demo=True), ('task_instructions', 'completion_report', 'blocked_note')),
            (AssignmentEvent.objects.filter(assignment__emergency__demo=True), ('note',)),
            (Dispatch.objects.filter(emergency__demo=True), ('cargo_details', 'trip_instructions', 'delivery_proof')),
            (DispatchEvent.objects.filter(dispatch__emergency__demo=True), ('note',)),
            (ShelterEvent.objects.filter(shelter__demo=True), ()),
            (ZoneApplication.objects.filter(organization__demo=True), ('zone', 'proposed_support', 'review_note')),
            (ZoneApplicationEvent.objects.filter(application__organization__demo=True), ()),
            (AllocationAuthorization.objects.filter(organization__demo=True), ('task_instructions', 'pickup_location', 'cargo_details', 'decision_note')),
            (AllocationAuthorizationEvent.objects.filter(authorization__organization__demo=True), ()),
            (InventoryMovement.objects.filter(inventory__organization__demo=True), ('note',)),
            (Notification.objects.filter(user__profile__details__demo=True), ('title', 'body')),
            (SupportTicket.objects.filter(user__profile__details__demo=True), ('subject', 'description')),
            (SupportReply.objects.filter(ticket__user__profile__details__demo=True), ('body',)),
            (SafetyTraining.objects.filter(demo=True), ('title', 'content')),
            (FundTransaction.objects.filter(demo=True), ('source', 'note')),
        ]
        for queryset, fields in text_models:
            for row in queryset:
                touched = []
                for field in fields:
                    old = getattr(row, field)
                    new = rewrite_text(old)
                    if new != old:
                        setattr(row, field, new)
                        touched.append(field)
                for field in ('detail', 'changes', 'value'):
                    if hasattr(row, field):
                        old = getattr(row, field)
                        new = rewrite_json(old)
                        if new != old:
                            setattr(row, field, new)
                            touched.append(field)
                if touched:
                    row.save(update_fields=touched)
                    changed += 1

        for row in EventLog.objects.filter(target__icontains='demo'):
            row.target = rewrite_text(row.target)
            row.action = rewrite_text(row.action)
            row.detail = rewrite_json(row.detail)
            row.save(update_fields=['target', 'action', 'detail'])
            changed += 1

        for preference in SystemPreference.objects.all():
            value = rewrite_json(preference.value)
            if preference.key == 'public_notice':
                value = ''
            if value != preference.value:
                preference.value = value
                preference.save(update_fields=['value', 'updated_at'])
                changed += 1

        self.stdout.write(self.style.SUCCESS(f'Punjab data normalization complete; {changed} existing records updated.'))
