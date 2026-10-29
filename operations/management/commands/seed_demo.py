from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.db import transaction
from operations.models import Organization, Profile, Emergency, EmergencyEvent, Shelter, Inventory, Donation, DonationCampaign, Advisory, SupportTicket, SupportReply, SupportTicketEvent, DonationEvent, Assignment, ZoneApplication, Vehicle, Dispatch, DispatchEvent, FundTransaction, SafetyTraining, TrainingCompletion, AssignmentEvent, AdvisoryEvent, AllocationAuthorization, AllocationAuthorizationEvent, EventLog, InventoryMovement, Notification, ShelterEvent, SystemPreference, ZoneApplicationEvent
from django.utils import timezone
User=get_user_model()
LOCAL_TEST_PASSWORD='PunjabRelief2026!'

def ensure_local_test_password(user):
    if not user.check_password(LOCAL_TEST_PASSWORD):
        user.set_password(LOCAL_TEST_PASSWORD)

VOLUNTEER_SERVICES=['Emergency Medical Response','Community First Aid','Relief Logistics','Search and Rescue']
VOLUNTEER_SKILLS=['First aid, CPR','First aid, Basic life support','Relief logistics, Warehouse handling','Search and rescue, Radio communications']
DRIVER_CLASSES=['LMV-TR','HMV-TR','LMV-TR','HMV-TR']

def demo_responder_details(role,index=0,region='MH'):
    details={'demo':True,'availability':'AVAILABLE'}
    if role in ('GOV_VOL','NGO_VOL'):
        details.update({'department':'Emergency Response','service':VOLUNTEER_SERVICES[index%len(VOLUNTEER_SERVICES)],'skills':VOLUNTEER_SKILLS[index%len(VOLUNTEER_SKILLS)],'experience':f'{2+index%8} years'})
    elif role in ('GOV_DRIVER','NGO_DRIVER'):
        state='PB' if region=='PB' else 'MH'
        details.update({'license_number':f'{state}-12-2018-{index+1:07d}','license_class':DRIVER_CLASSES[index%len(DRIVER_CLASSES)],'experience':f'{3+index%10} years'})
    return details

class Command(BaseCommand):
    help='Create or update repeatable DRRAS demonstration records.'
    @transaction.atomic
    def handle(self,*args,**opts):
        if Profile.objects.filter(details__seed_key__isnull=False).exists():
            call_command('normalize_punjab_data')
            call_command('seed_citizen_data')
            self.stdout.write(self.style.SUCCESS('Existing seeded records are already normalized; no accounts or operational records were recreated.'))
            return
        gov,_=Organization.objects.get_or_create(name='Maharashtra State Response Cell',defaults={'kind':'GOV','zone':'Maharashtra','demo':True})
        ngo1,_=Organization.objects.get_or_create(name='Sahyog Relief Network',defaults={'kind':'NGO','zone':'Konkan','demo':True})
        ngo2,_=Organization.objects.get_or_create(name='Seva Aid Collective',defaults={'kind':'NGO','zone':'Pune Division','demo':True})
        accounts=[('admin@drras.demo','Aarav Kulkarni','ADMIN',None,'APPROVED'),('official@drras.demo','Meera Deshmukh','GOV',gov,'APPROVED'),('sahyog@drras.demo','Kabir Shah','NGO',ngo1,'APPROVED'),('seva@drras.demo','Ananya Rao','NGO',ngo2,'APPROVED'),('volunteer@drras.demo','Ishita Patil','GOV_VOL',gov,'APPROVED'),('volunteer2@drras.demo','Manav Pawar','GOV_VOL',gov,'APPROVED'),('volunteer3@drras.demo','Aditi Shinde','GOV_VOL',gov,'APPROVED'),('ngo.volunteer@drras.demo','Rohan More','NGO_VOL',ngo1,'APPROVED'),('ngo.volunteer2@drras.demo','Farah Shaikh','NGO_VOL',ngo1,'APPROVED'),('ngo.volunteer3@drras.demo','Neelam Sawant','NGO_VOL',ngo1,'APPROVED'),('driver@drras.demo','Vikram Jadhav','GOV_DRIVER',gov,'APPROVED'),('driver2@drras.demo','Sonal Kapse','GOV_DRIVER',gov,'APPROVED'),('ngo.driver@drras.demo','Nisha Pawar','NGO_DRIVER',ngo1,'APPROVED'),('ngo.driver2@drras.demo','Arjun Desai','NGO_DRIVER',ngo1,'APPROVED'),('citizen@drras.demo','Priya Joshi','CITIZEN',None,'APPROVED')]
        users={}; volunteer_index=0; driver_index=0
        for email,name,role,org,status in accounts:
            u,_=User.objects.get_or_create(username=email,defaults={'email':email,'first_name':name}); u.email=email; u.first_name=name; ensure_local_test_password(u); u.save()
            details=demo_responder_details(role,volunteer_index if role in ('GOV_VOL','NGO_VOL') else driver_index) if role in ('GOV_VOL','NGO_VOL','GOV_DRIVER','NGO_DRIVER') else {'demo':True}
            if role in ('GOV_VOL','NGO_VOL'): volunteer_index+=1
            if role in ('GOV_DRIVER','NGO_DRIVER'): driver_index+=1
            Profile.objects.update_or_create(user=u,defaults={'role':role,'organization':org,'approval':status,'details':details}); users[email]=u
        for email,name,role,org in [('gov.applicant@drras.demo','Sana Khan','GOV',gov),('ngo.applicant@drras.demo','Devendra Nair','NGO',ngo2)]:
            u,_=User.objects.get_or_create(username=email,defaults={'email':email,'first_name':name}); u.email=email; u.first_name=name; ensure_local_test_password(u); u.save(); Profile.objects.update_or_create(user=u,defaults={'role':role,'organization':org,'approval':'PENDING','details':{'demo':True}})
        # A larger, clearly fictional Punjab dataset gives the dashboards enough
        # interconnected records to demonstrate queue, assignment, and map flows.
        punjab_gov,_=Organization.objects.get_or_create(name='Punjab State Response Cell',defaults={'kind':'GOV','zone':'Punjab','demo':True})
        punjab_ngo1,_=Organization.objects.get_or_create(name='Punjab Community Relief Network',defaults={'kind':'NGO','zone':'Central Punjab','demo':True})
        punjab_ngo2,_=Organization.objects.get_or_create(name='North Punjab Relief Initiative',defaults={'kind':'NGO','zone':'North Punjab','demo':True})
        punjab_accounts={}
        responders=[
            ('punjab.official@drras.demo','Harpreet Singh','GOV',punjab_gov),
            ('punjab.ngo1@drras.demo','Simran Kaur','NGO',punjab_ngo1),
            ('punjab.ngo2@drras.demo','Gurpreet Singh','NGO',punjab_ngo2),
            ('punjab.govvol1@drras.demo','Jaspreet Gill','GOV_VOL',punjab_gov),
            ('punjab.govvol2@drras.demo','Navdeep Kaur','GOV_VOL',punjab_gov),
            ('punjab.govvol3@drras.demo','Amrit Kaur','GOV_VOL',punjab_gov),
            ('punjab.ngovol1@drras.demo','Amandeep Brar','NGO_VOL',punjab_ngo1),
            ('punjab.ngo1vol2@drras.demo','Gurleen Kaur','NGO_VOL',punjab_ngo1),
            ('punjab.ngo1vol3@drras.demo','Sukhman Singh','NGO_VOL',punjab_ngo1),
            ('punjab.ngovol2@drras.demo','Manpreet Kaur','NGO_VOL',punjab_ngo2),
            ('punjab.ngo2vol2@drras.demo','Jasdeep Kaur','NGO_VOL',punjab_ngo2),
            ('punjab.ngo2vol3@drras.demo','Rupinder Singh','NGO_VOL',punjab_ngo2),
            ('punjab.ngo2vol4@drras.demo','Gursharan Singh','NGO_VOL',punjab_ngo2),
            ('punjab.govdriver@drras.demo','Sukhwinder Singh','GOV_DRIVER',punjab_gov),
            ('punjab.ngodriver1@drras.demo','Ravinder Kaur','NGO_DRIVER',punjab_ngo1),
            ('punjab.ngodriver2@drras.demo','Baljinder Singh','NGO_DRIVER',punjab_ngo2),
        ]
        punjab_volunteer_index=0; punjab_driver_index=0
        for email,name,role,org in responders:
            u,_=User.objects.get_or_create(username=email,defaults={'email':email,'first_name':name}); u.email=email; u.first_name=name; ensure_local_test_password(u); u.save()
            details=demo_responder_details(role,punjab_volunteer_index,'PB') if role in ('GOV_VOL','NGO_VOL') else demo_responder_details(role,punjab_driver_index,'PB') if role in ('GOV_DRIVER','NGO_DRIVER') else {'demo':True}
            if role in ('GOV_VOL','NGO_VOL'): punjab_volunteer_index+=1
            if role in ('GOV_DRIVER','NGO_DRIVER'): punjab_driver_index+=1
            Profile.objects.update_or_create(user=u,defaults={'role':role,'organization':org,'approval':'APPROVED','details':details}); punjab_accounts[email]=u
        citizen_names=['Amritpal Singh','Jasleen Kaur','Gurkirat Singh','Simranjit Kaur','Dilpreet Singh','Navjot Kaur','Arshdeep Singh','Kiranpreet Kaur','Harman Singh','Manpreet Kaur','Prabhjot Singh','Sandeep Kaur','Rupinder Singh','Amanpreet Kaur','Lakhwinder Singh','Ravneet Kaur','Jatinder Singh','Taranjit Kaur','Kuldeep Singh','Rajwinder Kaur','Eknoor Singh','Balpreet Kaur','Gagandeep Singh','Sukhdeep Kaur','Inderjit Singh','Pavneet Kaur','Mandeep Singh','Harleen Kaur','Satnam Singh','Jasbir Kaur','Gurleen Kaur','Tejinder Singh','Parminder Kaur','Kirandeep Kaur','Jagdeep Singh','Amandeep Kaur','Ranjit Singh','Gurpreet Kaur','Harjot Singh','Nimrat Kaur']
        punjab_citizens=[]
        for i,name in enumerate(citizen_names,1):
            email=f'punjab.citizen{i:02d}@drras.demo'; first,*last=name.split()
            u,_=User.objects.get_or_create(username=email,defaults={'email':email,'first_name':first,'last_name':' '.join(last)})
            u.email=email; u.first_name=first; u.last_name=' '.join(last); ensure_local_test_password(u); u.save()
            Profile.objects.update_or_create(user=u,defaults={'role':'CITIZEN','organization':None,'approval':'APPROVED','details':{'demo':True}}); punjab_citizens.append(u)
        punjab_places=[('Ludhiana',30.901,75.857),('Jagraon',30.787,75.473),('Khanna',30.705,76.221),('Samrala',30.836,76.193),('Moga',30.816,75.172),('Patiala',30.340,76.386),('Ferozepur',30.933,74.622),('Jalandhar',31.326,75.576),('Amritsar',31.634,74.873),('Sangrur',30.245,75.842)]
        cats=['Flood','Medical','Fire','Other','Flood']; priorities=['HIGH','MEDIUM','CRITICAL','LOW','HIGH']; punjab_emergencies=[]
        for i in range(25):
            place,lat,lon=punjab_places[i%len(punjab_places)]; status=['OPEN','OPEN','ACCEPTED','IN_PROGRESS','RESOLVED'][i%5]
            org=None if status=='OPEN' else [punjab_gov,punjab_ngo1,punjab_ngo2][i%3]
            ref=f'PB-DEMO-{i+1:03d}'
            needs_transport=i in (2,12)
            emergency,_=Emergency.objects.update_or_create(reference=ref,defaults={'reporter':punjab_citizens[i%len(punjab_citizens)],'category':cats[i%len(cats)],'priority':priorities[i%len(priorities)],'description':f'Demonstration incident {i+1}: residents near {place} need coordinated relief support. Fictional sample record.','location':f'{place}, Punjab','latitude':lat+(i%4)*0.002,'longitude':lon+(i%3)*0.002,'affected':12+(i*7)%95,'required_skills':'First aid' if needs_transport else '','needs_transport':needs_transport,'required_vehicle_capacity':8 if needs_transport else 0,'status':status,'verification':'Verified' if status!='OPEN' else 'Pending','accepted_by':org,'demo':True})
            if not emergency.history.filter(event_type='DEMO_SEEDED').exists(): EmergencyEvent.objects.create(emergency=emergency,actor=emergency.reporter,event_type='DEMO_SEEDED',to_status=status,note='Fictional demonstration incident; seeded status snapshot.')
            punjab_emergencies.append(emergency)
        volunteer_users_by_org={punjab_gov:[punjab_accounts[key] for key in ('punjab.govvol1@drras.demo','punjab.govvol2@drras.demo','punjab.govvol3@drras.demo')],punjab_ngo1:[punjab_accounts[key] for key in ('punjab.ngovol1@drras.demo','punjab.ngo1vol2@drras.demo','punjab.ngo1vol3@drras.demo')],punjab_ngo2:[punjab_accounts[key] for key in ('punjab.ngovol2@drras.demo','punjab.ngo2vol2@drras.demo','punjab.ngo2vol3@drras.demo','punjab.ngo2vol4@drras.demo')]}
        desired_assignments={}; active_roster_index={org.pk:0 for org in volunteer_users_by_org}; completed_roster_index={org.pk:0 for org in volunteer_users_by_org}
        for e in punjab_emergencies:
            if e.status not in ('ACCEPTED','IN_PROGRESS','RESOLVED'): continue
            eligible=volunteer_users_by_org[e.accepted_by]
            if e.status=='RESOLVED':
                responder=eligible[completed_roster_index[e.accepted_by_id]%len(eligible)]; completed_roster_index[e.accepted_by_id]+=1
                assignment_status='COMPLETED'
            else:
                responder=eligible[active_roster_index[e.accepted_by_id]%len(eligible)]; active_roster_index[e.accepted_by_id]+=1
                assignment_status='IN_PROGRESS' if e.status=='IN_PROGRESS' else 'ASSIGNED'
            desired_assignments[(e.pk,responder.pk)] = (e,responder,assignment_status)
        for stale in Assignment.objects.filter(emergency__reference__startswith='PB-DEMO-',kind='VOL',status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).select_related('emergency'):
            if (stale.emergency_id,stale.user_id) not in desired_assignments:
                stale.status='CANCELLED'; stale.save(update_fields=['status','updated_at'])
                AssignmentEvent.objects.create(assignment=stale,actor=None,status='CANCELLED',note='Demo seed reconciliation: closed stale sample assignment while preserving its record and timeline.')
        for e,responder,assignment_status in desired_assignments.values():
            assignment,created=Assignment.objects.get_or_create(emergency=e,user=responder,kind='VOL',defaults={'organization':e.accepted_by,'assigned_by':None,'status':assignment_status,'task_instructions':'Fictional training task. Check in with the assigned response lead.','completion_report':'Demonstration task completed.' if assignment_status=='COMPLETED' else ''})
            changed=not created and (assignment.status!=assignment_status or assignment.organization_id!=e.accepted_by_id)
            if changed:
                old_status=assignment.status; assignment.status=assignment_status; assignment.organization=e.accepted_by; assignment.save(update_fields=['status','organization','updated_at'])
                AssignmentEvent.objects.create(assignment=assignment,actor=None,status=assignment_status,note=f'Demo seed reconciliation: {old_status} → {assignment_status}.')
            elif created or not assignment.history.exists():
                AssignmentEvent.objects.create(assignment=assignment,actor=None,status=assignment_status,note='Fictional training task seeded for repeatable demo data.')
        requests=[('DR-DEMO-101','Flood','CRITICAL','River water entered ground-floor homes; urgent evacuation support needed.','Chiplun, Ratnagiri',19.517,73.517,86,'OPEN',None),('DR-DEMO-102','Medical','HIGH','Community clinic needs medicine and transport for residents.','Khed, Pune',18.858,73.887,34,'OPEN',None),('DR-DEMO-103','Landslide','HIGH','Road access blocked after slope failure; families require food kits.','Mahad, Raigad',18.083,73.417,52,'ACCEPTED',ngo1),('DR-DEMO-104','Fire','MEDIUM','Small market fire contained; household relief requested.','Satara, Satara',17.680,73.990,18,'IN_PROGRESS',gov),('DR-DEMO-105','Cyclone','MEDIUM','Roof damage and water supply disruption reported.','Dapoli, Ratnagiri',17.758,73.185,29,'RESOLVED',ngo2),('DR-DEMO-106','Flood','HIGH','Several lanes are waterlogged and families need drinking water.','Rajapur, Ratnagiri',16.657,73.518,41,'OPEN',None),('DR-DEMO-107','Fire','MEDIUM','Electrical fire damaged a row of small shops; no injuries reported.','Pimpri, Pune',18.629,73.799,16,'OPEN',None),('DR-DEMO-108','Medical','CRITICAL','Urgent medicine and ambulance support requested for an isolated hamlet.','Ajra, Kolhapur',16.116,74.211,27,'OPEN',None)]
        for ref,cat,prio,desc,loc,lat,lon,affected,status,org in requests:
            emergency,_=Emergency.objects.update_or_create(reference=ref,defaults={'reporter':users['citizen@drras.demo'],'category':cat,'priority':prio,'description':desc,'location':loc,'latitude':lat,'longitude':lon,'affected':affected,'status':status,'verification':'Verified' if status!='OPEN' else 'Pending','accepted_by':org,'demo':True})
            if not emergency.history.filter(event_type='DEMO_SEEDED').exists(): EmergencyEvent.objects.create(emergency=emergency,actor=emergency.reporter,event_type='DEMO_SEEDED',to_status=status,note='Fictional demonstration incident; seeded status snapshot.')
        for ref,email,kind in [('DR-DEMO-103','ngo.volunteer@drras.demo','VOL'),('DR-DEMO-103','ngo.volunteer2@drras.demo','VOL'),('DR-DEMO-103','ngo.driver@drras.demo','DRIVER'),('DR-DEMO-103','ngo.driver2@drras.demo','DRIVER'),('DR-DEMO-104','volunteer@drras.demo','VOL'),('DR-DEMO-104','volunteer2@drras.demo','VOL'),('DR-DEMO-104','driver@drras.demo','DRIVER'),('DR-DEMO-104','driver2@drras.demo','DRIVER')]:
            assignment_status='IN_PROGRESS' if (ref,email) in [('DR-DEMO-103','ngo.driver@drras.demo'),('DR-DEMO-104','driver2@drras.demo')] else 'ASSIGNED'
            assignment,_=Assignment.objects.update_or_create(emergency=Emergency.objects.get(reference=ref),user=users[email],kind=kind,defaults={'status':assignment_status,'task_instructions':'Fictional training task. Confirm details with the response lead before deployment.'})
            if not assignment.history.exists(): AssignmentEvent.objects.create(assignment=assignment,status=assignment.status,note='Demo assignment initialized')
        vehicles={}
        for org,plate,vtype,capacity in [(gov,'MH14-GV-2401','Medical van',6),(gov,'MH14-GV-2402','Relief truck',24),(gov,'MH14-GV-2403','Field transport van',8),(ngo1,'MH12-SR-1107','Supply van',8),(ngo1,'MH12-SR-1108','Rescue SUV',5),(ngo1,'MH12-SR-1109','Relief minibus',12),(ngo2,'MH12-SA-2804','Relief van',10)]:
            vehicle,_=Vehicle.objects.update_or_create(registration=plate,defaults={'organization':org,'kind':vtype,'capacity':capacity,'demo':True}); vehicles[plate]=vehicle
        punjab_transport=[(2,punjab_ngo2,'punjab.ngodriver2@drras.demo','PB-NPR-TR-01','PB-NPR-TR-VEH',12),(12,punjab_gov,'punjab.govdriver@drras.demo','PB-GOV-TR-01','PB-GOV-TR-VEH',16)]
        for index,org,email,driver_name,plate,capacity in punjab_transport:
            vehicle,_=Vehicle.objects.update_or_create(registration=plate,defaults={'organization':org,'kind':'Medical relief van','capacity':capacity,'demo':True})
            emergency=punjab_emergencies[index]; driver=punjab_accounts[email]
            Assignment.objects.update_or_create(emergency=emergency,user=driver,kind='DRIVER',defaults={'status':'ASSIGNED','task_instructions':'Fictional sample dispatch. Coordinate with the volunteer lead before moving supplies.'})
            dispatch,_=Dispatch.objects.update_or_create(emergency=emergency,driver=driver,defaults={'organization':org,'vehicle':vehicle,'pickup_location':f'{emergency.location} demo depot','destination':emergency.location,'cargo_details':'First-aid kits and family relief packs','trip_instructions':'Fictional sample transport assignment.','status':'ASSIGNED'})
            if not dispatch.history.filter(status='ASSIGNED').exists(): DispatchEvent.objects.create(dispatch=dispatch,actor=driver,status='ASSIGNED',note='Demonstration transport dispatch created')
        for ref,email,plate,status in [('DR-DEMO-103','ngo.driver@drras.demo','MH12-SR-1107','IN_TRANSIT'),('DR-DEMO-103','ngo.driver2@drras.demo','MH12-SR-1108','ASSIGNED'),('DR-DEMO-104','driver@drras.demo','MH14-GV-2401','ASSIGNED'),('DR-DEMO-104','driver2@drras.demo','MH14-GV-2402','IN_TRANSIT')]:
            dispatch,_=Dispatch.objects.update_or_create(emergency=Emergency.objects.get(reference=ref),driver=users[email],defaults={'organization':Emergency.objects.get(reference=ref).accepted_by,'vehicle':vehicles[plate],'pickup_location':'Demo response warehouse','destination':Emergency.objects.get(reference=ref).location,'cargo_details':'Water, first-aid packs and family supply kits','trip_instructions':'Fictional training dispatch. Coordinate with the response lead before unloading.','status':status})
            if not dispatch.history.filter(status='ASSIGNED').exists(): DispatchEvent.objects.create(dispatch=dispatch,actor=users[email],status='ASSIGNED',note='Demonstration dispatch created')
            if status!='ASSIGNED' and not dispatch.history.filter(status=status).exists(): DispatchEvent.objects.create(dispatch=dispatch,actor=users[email],status=status,note='Demonstration trip progress')
        shelters=[('Ratnagiri Community Hall','Chiplun, Ratnagiri',17.533,73.517,240,176,'Shelter','Family rest area with drinking water and accessible washrooms.',ngo1),('Pune District Relief Centre','Pune, Pune',18.520,73.856,320,221,'Supply center','Coordinates food kits, blankets, and district-level stock distribution.',gov),('Mahad Municipal School','Mahad, Raigad',18.083,73.417,150,143,'Shelter','Temporary family accommodation with a staffed information desk.',ngo1),('Satara Sports Complex','Satara, Satara',17.680,74.018,180,62,'Relief hub','Community registration, charging, and referral point.',gov)]
        for name,loc,lat,lon,cap,occ,stype,description,org in shelters: Shelter.objects.update_or_create(name=name,defaults={'organization':org,'location':loc,'shelter_type':stype,'description':description,'latitude':lat,'longitude':lon,'capacity':cap,'occupancy':occ,'demo':True})
        for name,loc,lat,lon,cap,occ,stype,description,org in [('Ludhiana Demo Relief Hub','Ludhiana, Punjab',30.901,75.857,260,148,'Relief hub','Sample coordination point for water, food, and referrals.',punjab_gov),('Moga Community Shelter','Moga, Punjab',30.816,75.172,180,91,'Shelter','Fictional temporary shelter with family sleeping space.',punjab_ngo1),('Patiala Sample Relief Centre','Patiala, Punjab',30.340,76.386,220,177,'Medical post','Sample first-aid and basic triage location.',punjab_gov),('Jalandhar Demo Family Hub','Jalandhar, Punjab',31.326,75.576,150,64,'Relief hub','Sample family support desk and supply pickup point.',punjab_ngo2)]: Shelter.objects.update_or_create(name=name,defaults={'organization':org,'location':loc,'shelter_type':stype,'description':description,'latitude':lat,'longitude':lon,'capacity':cap,'occupancy':occ,'demo':True})
        for org,wh,address,item,category,qty,unit in [(gov,'Pune Central Warehouse','18 Market Yard Road, Pune','Water kits','Water & sanitation',480,'kits'),(gov,'Ratnagiri Depot','NH66 Service Road, Ratnagiri','First-aid packs','Medical',96,'packs'),(ngo1,'Chiplun Relief Store','Khed-Chiplun Road, Chiplun','Food parcels','Food',210,'parcels'),(ngo2,'Pune Community Hub','Sinhagad Road, Pune','Blankets','Shelter & bedding',175,'blankets')]: Inventory.objects.update_or_create(organization=org,warehouse=wh,item=item,defaults={'category':category,'warehouse_location':address,'quantity':qty,'unit':unit})
        for org,kind,amount,source,ref,note in [(gov,'ALLOCATION','5000000.00','State disaster response grant','FND-DEMO-GOV-001','Approved seasonal response budget'),(gov,'EXPENDITURE','1245000.00','Emergency logistics','FND-DEMO-GOV-002','Monsoon response supplies'),(ngo1,'ALLOCATION','800000.00','Sahyog preparedness grant','FND-DEMO-NGO-001','Demo grant record'),(ngo1,'EXPENDITURE','236000.00','Konkan food and transport','FND-DEMO-NGO-002','Monsoon response'),(ngo2,'ALLOCATION','450000.00','Seva community fund','FND-DEMO-NGO2-001','Demo grant record'),(ngo2,'EXPENDITURE','128000.00','Pune family kits','FND-DEMO-NGO2-002','Response stock')]:
            FundTransaction.objects.get_or_create(reference=ref,defaults={'organization':org,'kind':kind,'amount':amount,'source':source,'note':note,'demo':True})
        advisory_rows=[
            ('Monsoon preparedness: Konkan belt','Keep essential medication and drinking water ready. Follow local authority evacuation instructions and use listed relief shelters.','Konkan Division','HIGH',True),
            ('River level watch: Satara','Monitor official river-level updates, avoid low crossings, and move to a listed shelter if local officials advise evacuation.','Satara District','MEDIUM',True),
            ('Relief centre hours: Pune Division','District relief desks are open for family registration, water, and referral support. Bring essential medication where possible.','Pune Division','LOW',True),
            ('Draft: coastal road access update','Confirm road access with local officials before transporting relief supplies. This sample advisory remains an unpublished draft.','Raigad District','HIGH',False),
        ]
        for title,body,location,severity,published in advisory_rows:
            advisory,_=Advisory.objects.update_or_create(title=title,defaults={'body':body,'location':location,'severity':severity,'published':published,'demo':True})
            if not advisory.history.exists(): AdvisoryEvent.objects.create(advisory=advisory,event_type='PUBLISHED' if published else 'DRAFTED',detail={'seeded':True,'severity':advisory.severity})
        ZoneApplication.objects.get_or_create(organization=ngo2,zone='Pune East',defaults={'proposed_support':'Two rotating volunteer teams, family supply kits and a shared mobile medical desk.','volunteer_availability':18,'vehicle_availability':3})
        campaign_rows=[(punjab_gov,'Punjab Shelter Essentials Drive','District relief shelters','Fund clean water and family kits for temporary shelters across the response area.','750000.00'),(punjab_ngo1,'Sutlej First Aid & Medical Stock','Punjab Community Relief Network','Restock first-aid kits and mobile medical supplies for flood-affected villages.','350000.00'),(punjab_ngo2,'Community Food Parcels','North Punjab Relief Initiative','Prepare shelf-stable meals and delivery routes for families needing short-term support.','225000.00')]
        campaigns={}
        for org,name,recipient,description,goal in campaign_rows:
            campaign,_=DonationCampaign.objects.get_or_create(name=name,organization=org,defaults={'recipient':recipient,'description':description,'goal_amount':goal,'published':True,'demo':True}); campaigns[name]=campaign
        donation_rows=[('DON-DEMO-001','2500.00','SUBMITTED','Punjab Shelter Essentials Drive'),('DON-DEMO-002','750.00','SUBMITTED','Sutlej First Aid & Medical Stock'),('DON-DEMO-003','300.00','REJECTED','Community Food Parcels')]
        for ref,amount,status,campaign_name in donation_rows:
            donation,created=Donation.objects.get_or_create(reference=ref,defaults={'donor':users['citizen@drras.demo'],'campaign':campaigns[campaign_name],'amount':amount,'currency':'INR','status':status,'demo':True})
            if created:
                DonationEvent.objects.get_or_create(donation=donation,event_type=status,to_status=status,defaults={'actor':donation.donor,'note':'Fictional sample record. No payment was processed.'})
                if status=='REJECTED':
                    donation.failure_reason='Demonstration sample rejected state'; donation.save(update_fields=['failure_reason'])
        ticket_rows=[
            (users['citizen@drras.demo'],'Shelter accessibility information','Shelters','Please confirm wheelchair access at the nearest relief centre.','In Progress','HIGH'),
            (users['volunteer@drras.demo'],'Field kit collection point','Volunteer support','Please confirm the collection window for first-aid kits before my assigned shift.','Open','NORMAL'),
            (users['ngo.volunteer@drras.demo'],'Vehicle roster correction','Team records','My availability is current, but I am missing from the next volunteer roster review.','Resolved','LOW'),
            (users['citizen@drras.demo'],'Water distribution schedule','Emergency response','Please share the next water distribution time for the Chiplun relief area.','Open','URGENT'),
        ]
        tickets={}
        for owner,subject,category,description,status,priority in ticket_rows:
            ticket,_=SupportTicket.objects.get_or_create(user=owner,subject=subject,defaults={'category':category,'description':description,'status':status,'priority':priority})
            tickets[subject]=ticket
        reply_rows=[
            (tickets['Shelter accessibility information'],users['admin@drras.demo'],'The shelter profile lists accessible washrooms. The site coordinator can confirm the current entrance route.'),
            (tickets['Shelter accessibility information'],users['citizen@drras.demo'],'Thank you. Please add the entrance route details when they are confirmed.'),
            (tickets['Water distribution schedule'],users['admin@drras.demo'],'The distribution schedule will be posted by the district response desk after the next supply check.'),
        ]
        for ticket,author,body in reply_rows: SupportReply.objects.get_or_create(ticket=ticket,author=author,body=body)
        all_responders=['GOV_VOL','NGO_VOL','GOV_DRIVER','NGO_DRIVER']
        training_rows=[
            ('FIELD-CHECKIN','Field check-in and buddy system','Field safety','Confirm your incident lead, assigned zone, communications method and buddy before deployment. Check in on arrival and before leaving the site.',all_responders),
            ('FLOOD-SAFETY','Flood and unstable-ground awareness','Hazard awareness','Do not enter moving or unknown-depth water, damaged buildings or restricted areas. Stop work and alert your lead when the route or structure appears unsafe.',['GOV_VOL','NGO_VOL']),
            ('PPE-HYGIENE','Protective equipment and hygiene','Personal safety','Use task-appropriate protective equipment, keep cuts covered, wash or sanitize hands, and follow the organization’s infection-control instructions.',['GOV_VOL','NGO_VOL']),
            ('PRIVACY-SAFEGUARDING','Resident privacy and safeguarding','Safeguarding','Ask before collecting personal details or taking photographs. Share only information needed for the response, protect children and vulnerable adults, and report safeguarding concerns to your lead.',all_responders),
            ('FIRST-AID-BOUNDARIES','First-aid role boundaries','Medical safety','Provide care only within your current training and authorization. Request qualified medical personnel for urgent care; do not give medication or perform unfamiliar procedures.',['GOV_VOL','NGO_VOL']),
            ('DRIVER-VEHICLE-CHECK','Vehicle and route safety check','Transport safety','Before travel, check vehicle condition, assigned cargo, destination and communications plan. Follow road closures and speed limits; stop and contact dispatch if the route becomes unsafe.',['GOV_DRIVER','NGO_DRIVER']),
        ]
        for code,title,category,content,roles in training_rows:
            SafetyTraining.objects.get_or_create(code=code,defaults={'title':title,'category':category,'content':content,'required_roles':roles,'active':True,'demo':True})
        field_safety=SafetyTraining.objects.get(code='FIELD-CHECKIN')
        TrainingCompletion.objects.get_or_create(training=field_safety,user=users['volunteer@drras.demo'],defaults={'acknowledged_at':timezone.now(),'completed_at':timezone.now(),'note':'Demonstration acknowledgement only.'})
        # Seed enough workflow history for the first run to demonstrate audit,
        # inventory, shelter, authorization, and notification modules. Stable
        # natural keys keep these snapshots idempotent without resetting user data.
        zone_application=ZoneApplication.objects.get(organization=ngo2,zone='Pune East')
        ZoneApplicationEvent.objects.get_or_create(application=zone_application,event_type='SUBMITTED',defaults={'actor':users['seva@drras.demo'],'detail':{'demo':True,'note':'Fictional seeded application submission.'}})

        demo_emergency=Emergency.objects.get(reference='DR-DEMO-103')
        stock=Inventory.objects.get(organization=ngo1,warehouse='Chiplun Relief Store',item='Food parcels')
        authorization_note='DEMO-SEED: Konkan food parcels allocation proposal'
        authorization=AllocationAuthorization.objects.filter(task_instructions=authorization_note).first()
        if not authorization:
            authorization=AllocationAuthorization.objects.create(emergency=demo_emergency,organization=ngo1,requested_by=users['sahyog@drras.demo'],kind='STOCK',inventory=stock,requested_quantity=25,task_instructions=authorization_note,pickup_location=stock.warehouse,cargo_details='Food parcels for households affected by the landslide; fictional sample proposal.',status='PENDING')
        AllocationAuthorizationEvent.objects.get_or_create(authorization=authorization,event_type='SUBMITTED',defaults={'actor':users['sahyog@drras.demo'],'detail':{'demo':True,'quantity':25}})

        # Explicit opening receipts and subsequent sample movements reconcile
        # each seeded stock position to its ledger without rewriting quantities.
        water_stock=Inventory.objects.get(organization=gov,warehouse='Pune Central Warehouse',item='Water kits')
        first_aid_stock=Inventory.objects.get(organization=gov,warehouse='Ratnagiri Depot',item='First-aid packs')
        blankets_stock=Inventory.objects.get(organization=ngo2,warehouse='Pune Community Hub',item='Blankets')
        movement_rows=[(stock,'RECEIPT',180,None,'DEMO-SEED: Food parcels opening balance'),(stock,'RECEIPT',50,None,'DEMO-SEED: Food parcels opening receipt'),(stock,'ISSUE',20,demo_emergency,'DEMO-SEED: Food parcels sample issue'),(water_stock,'RECEIPT',400,None,'DEMO-SEED: Water kits opening balance'),(water_stock,'RECEIPT',120,None,'DEMO-SEED: Water kits opening receipt'),(water_stock,'ISSUE',40,Emergency.objects.get(reference='DR-DEMO-104'),'DEMO-SEED: Water kits sample issue'),(first_aid_stock,'RECEIPT',96,None,'DEMO-SEED: First-aid packs opening balance'),(blankets_stock,'RECEIPT',175,None,'DEMO-SEED: Blankets opening balance')]
        actors={'RECEIPT':users['official@drras.demo'],'ISSUE':users['official@drras.demo']}
        for inventory,kind,quantity,emergency,note in movement_rows:
            InventoryMovement.objects.get_or_create(inventory=inventory,kind=kind,note=note,defaults={'quantity':quantity,'emergency':emergency,'actor':actors[kind]})

        shelter=Shelter.objects.get(name='Ratnagiri Community Hall')
        ShelterEvent.objects.get_or_create(shelter=shelter,event_type='DEMO_SNAPSHOT',defaults={'actor':users['official@drras.demo'],'changes':{'demo':True,'capacity':shelter.capacity,'occupancy':shelter.occupancy,'note':'Fictional seeded shelter status snapshot.'}})

        preference_defaults={'platform_name':'DRRAS','support_email':'support@drras.demo','default_emergency_priority':'MEDIUM','public_notice':'Fictional demonstration records are shown for training and evaluation.','shelter_capacity_thresholds':{'high_occupancy_pct':50,'nearly_full_pct':85}}
        for key,value in preference_defaults.items(): SystemPreference.objects.get_or_create(key=key,defaults={'value':value,'updated_by':users['admin@drras.demo']})

        notification_rows=[(users['official@drras.demo'],'DEMO: Allocation review queue','A fictional NGO stock proposal is waiting in Allocation Authorizations.','/gov.html'),(users['sahyog@drras.demo'],'DEMO: Proposal submitted','A fictional food parcel proposal is awaiting Government review.','/ngo.html'),(users['volunteer@drras.demo'],'DEMO: Field check-in','Review the sample field safety guidance before taking an assignment.','/gov_volunteer.html'),(users['driver@drras.demo'],'DEMO: Dispatch checklist','Review the sample vehicle and route safety guidance before dispatch.','/govt_driver.html'),(users['citizen@drras.demo'],'DEMO: Public relief information','Sample shelter and advisory information is available on the public dashboard.','/citizen.html')]
        for user,title,body,link in notification_rows: Notification.objects.get_or_create(user=user,title=title,body=body,defaults={'link':link})

        for action,target,actor,detail in [('Demo request accepted','DR-DEMO-103',users['sahyog@drras.demo'],{'organization':'Sahyog Relief Network'}),('Demo response underway','DR-DEMO-104',users['official@drras.demo'],{'organization':'Maharashtra State Response Cell'}),('Demo relief request resolved','DR-DEMO-105',users['seva@drras.demo'],{'organization':'Seva Aid Collective'}),('Demo stock ledger initialized','Pune Central Warehouse/Water kits',users['official@drras.demo'],{'opening_balance':400,'receipt':120,'issue':40}),('Demo shelter snapshot recorded','Ratnagiri Community Hall',users['official@drras.demo'],{'occupancy':shelter.occupancy,'capacity':shelter.capacity})]:
            EventLog.objects.get_or_create(action=action,target=target,defaults={'actor':actor,'detail':{'demo':True,**detail}})
        call_command('normalize_punjab_data')
        call_command('seed_citizen_data')
        self.stdout.write(self.style.SUCCESS('Punjab relief records are ready. Local account password: PunjabRelief2026!'))
