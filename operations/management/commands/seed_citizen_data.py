from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from operations.models import Organization, Profile, Shelter, DonationCampaign, Advisory, SupportTicket, SupportReply, SupportTicketEvent, Dispatch, DeliveryRecord, DispatchEvent, Assignment, AssignmentEvent

class Command(BaseCommand):
    help = 'Idempotently ensure shared Punjab demo data without rewriting citizen accounts or activity.'

    @transaction.atomic
    def handle(self, *args, **options):
        shelter_rows = [
            ('Civil Lines Family Shelter','Majha Community Support Network','Civil Lines','Amritsar',31.634,74.872,140,'+91 90000 00001'),
            ('Lawrence Road Relief Centre','Punjab State Relief Directorate','Lawrence Road','Amritsar',31.642,74.875,110,'+91 90000 00002'),
            ('Model Town Community Shelter','Majha Community Support Network','Model Town','Jalandhar',31.326,75.576,95,'+91 90000 00003'),
            ('Baradari Relief Hub','Punjab State Relief Directorate','Baradari','Patiala',30.339,76.386,85,'+91 90000 00004'),
            ('Ajit Road Family Centre','Punjab State Response Cell','Ajit Road','Bathinda',30.211,74.945,100,'+91 90000 00005'),
            ('Ghal Kalan Community Shelter','Punjab Community Relief Network','Ghal Kalan','Moga',30.823,75.171,75,'+91 90000 00006'),
            ('Nabha Gate Relief Centre','Punjab State Response Cell','Nabha Gate','Patiala',30.374,76.149,90,'+91 90000 00007'),
            ('Sultanpur Lodhi Family Hub','North Punjab Relief Initiative','Sultanpur Lodhi','Kapurthala',31.213,75.197,80,'+91 90000 00008'),
        ]
        organizations = {org.name: org for org in Organization.objects.filter(name__in={row[1] for row in shelter_rows})}
        for org_name, kind, zone in [
            ('Punjab State Relief Directorate','GOV','Punjab'),
            ('Majha Community Support Network','NGO','Majha, Punjab'),
            ('Punjab State Response Cell','GOV','Punjab'),
            ('Punjab Community Relief Network','NGO','Malwa, Punjab'),
            ('North Punjab Relief Initiative','NGO','North Punjab'),
        ]:
            org, _ = Organization.objects.get_or_create(name=org_name, defaults={'kind':kind,'zone':zone,'demo':True})
            organizations[org_name] = org
        contacts={}
        for name,org_name,locality,district,lat,lon,capacity,phone in shelter_rows:
            shelter,_=Shelter.objects.get_or_create(name=name,defaults={
                'organization':organizations[org_name],'location':f'{locality}, {district}, Punjab',
                'address':locality,'district':district,'contact_phone':phone,'shelter_type':'Family shelter',
                'description':'Fictional public shelter details for the DRRAS demonstration.','latitude':lat,
                'longitude':lon,'capacity':capacity,'occupancy':0,'status':'Open','demo':True,
            })
            contacts[name]=phone
            if shelter.demo and not shelter.contact_phone:
                shelter.contact_phone=phone; shelter.save(update_fields=['contact_phone','updated_at'])

        campaign_rows=[
            ('Punjab State Relief Directorate','State relief essentials drive','Government relief coordination','Water and essential family supplies for Punjab emergency response.','600000.00'),
            ('Majha Community Support Network','Majha family support campaign','Majha households','Community supplies and temporary shelter support in Majha.','250000.00'),
            ('Punjab State Response Cell','Punjab emergency supplies campaign','Punjab response teams','Emergency supply readiness and district relief distribution.','500000.00'),
            ('Punjab Community Relief Network','Malwa community relief campaign','Malwa households','Food, water, and basic family relief supplies in Malwa.','275000.00'),
            ('North Punjab Relief Initiative','North Punjab family relief campaign','North Punjab households','Community relief supplies for families in North Punjab.','225000.00'),
        ]
        for org_name,name,recipient,description,goal in campaign_rows:
            DonationCampaign.objects.get_or_create(name=name,organization=organizations[org_name],defaults={
                'recipient':recipient,'description':description,'goal_amount':goal,'currency':'INR','published':True,'demo':True,
            })

        publisher=Profile.objects.filter(role='GOV',approval='APPROVED',organization__isnull=False).select_related('user').first()
        if publisher:
            for title,category,severity,location,body in [
                ('Punjab flood readiness information','Weather preparedness','HIGH','Punjab','Follow official district instructions, avoid flood water, and contact emergency services if your household is at immediate risk.'),
                ('Punjab relief centre access guidance','Public safety','MEDIUM','Punjab','Check the current shelter directory for recorded capacity and contact details before travelling.'),
            ]:
                Advisory.objects.get_or_create(title=title,defaults={
                    'category':category,'severity':severity,'location':location,'body':body,
                    'published':True,'published_by':publisher.user,'demo':True,
                })

        showcase=get_user_model().objects.filter(email='amritpal.singh.citizen01@drras.local').first()
        if showcase:
            ticket,created=SupportTicket.objects.get_or_create(user=showcase,subject='Shelter access information (showcase)',defaults={
                'category':'Shelters','priority':'NORMAL','description':'Please confirm the recorded access and contact details for the nearest listed relief shelter.',
                'demo':True,
            })
            if created:
                SupportTicketEvent.objects.create(ticket=ticket,event_type='CREATED',detail={'demo':True})
                SupportReply.objects.create(ticket=ticket,author=publisher.user if publisher else None,body='Showcase reply: check the current shelter directory for the published location, capacity, and contact number.')
        # A seeded showcase record has no uploaded proof. Never manufacture a photo.
        if not DeliveryRecord.objects.filter(demo=True).exists():
            dispatch = Dispatch.objects.select_related('emergency', 'driver', 'vehicle', 'organization').filter(
                emergency__reporter__email='amritpal.singh.citizen01@drras.local',
                status='IN_TRANSIT', emergency__demo=True,
            ).order_by('pk').first()
            if dispatch:
                now = timezone.now()
                row = DeliveryRecord.objects.create(
                    dispatch=dispatch, emergency=dispatch.emergency, driver=dispatch.driver,
                    vehicle=dispatch.vehicle, organization=dispatch.organization,
                    recipient_name='Amritpal Singh (showcase)', address=dispatch.emergency.location,
                    items=[{'name': 'Drinking water (showcase)', 'quantity': 2}], delivered_at=now,
                    remarks='SHOWCASE DATA ONLY. No real delivery or photo proof is represented.',
                    demo=True, status='WAITING_CONFIRMATION',
                )
                old = dispatch.status
                dispatch.status = 'DELIVERED'; dispatch.delivered_at = now
                dispatch.delivery_proof = f'Showcase delivery record {row.pk}; no proof photo attached.'
                dispatch.save(update_fields=['status', 'delivered_at', 'delivery_proof', 'updated_at'])
                DispatchEvent.objects.create(dispatch=dispatch, actor=dispatch.driver, status='DELIVERED', note='Showcase delivery submitted; Citizen confirmation remains pending.')
                assignment = Assignment.objects.filter(emergency=dispatch.emergency, user=dispatch.driver, kind='DRIVER', status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).first()
                if assignment:
                    assignment.status='COMPLETED'; assignment.completion_report='Showcase record; awaiting Citizen response.'
                    assignment.save(update_fields=['status','completion_report','updated_at'])
                    AssignmentEvent.objects.create(assignment=assignment,actor=dispatch.driver,status='COMPLETED',note=assignment.completion_report)
                self.stdout.write(f'Created showcase delivery {row.pk} (photo intentionally absent).')
        self.stdout.write(self.style.SUCCESS('Shared Citizen demo data is ready; existing records were preserved.'))
