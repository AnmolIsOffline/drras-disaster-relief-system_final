import json
import re
from datetime import timedelta
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError, OperationalError
from django.db.models import Sum, Q
from django.utils import timezone
from django.http import JsonResponse, FileResponse
from django.utils.dateparse import parse_datetime
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from .api_common import error, profile, payload, notify, sqlite_write_conflict
from .geography import PUNJAB_DISTRICTS, format_punjab_address, is_punjab_coordinate
from .models import Profile, Organization, Emergency, EmergencyEvent, Assignment, AssignmentEvent, AllocationAuthorization, AllocationAuthorizationEvent, Shelter, ShelterEvent, Donation, Advisory, AdvisoryEvent, Inventory, InventoryMovement, EventLog, SupportTicket, SupportTicketEvent, SupportReply, Notification, ZoneApplication, ZoneApplicationEvent, Vehicle, Dispatch, DispatchEvent, DeliveryRecord, FundTransaction, SystemPreference, SafetyTraining, TrainingCompletion
User=get_user_model()
ROLE_PAGE={'ADMIN':'admin.html','GOV':'gov.html','NGO':'ngo.html','GOV_VOL':'gov_volunteer.html','NGO_VOL':'ngo_volunteer.html','GOV_DRIVER':'govt_driver.html','NGO_DRIVER':'ngo_driver.html','CITIZEN':'citizen.html'}
def record_emergency_event(emergency,actor,event_type,from_status='',to_status='',note=''):
    return EmergencyEvent.objects.create(emergency=emergency,actor=actor,event_type=event_type,from_status=from_status,to_status=to_status,note=note)
def public_profile_details(details):
    return {key:value for key,value in (details or {}).items() if key not in ('seed_key','demo')}
def calculate_emergency_priority(severity, affected, injured, vulnerable_counts):
    """Map severity to baseline priority, then escalate for counts: >=25 affected or >=3 injured is CRITICAL; any injury/vulnerability or >=10 affected is HIGH; >=3 affected is at least MEDIUM."""
    priority={'LOW':'LOW','MODERATE':'MEDIUM','SEVERE':'HIGH','CRITICAL':'CRITICAL'}[severity]
    injured=injured or 0
    affected_known=affected is not None
    vulnerable_total=sum(value for value in vulnerable_counts.values() if value is not None)
    if injured>=3 or (affected_known and affected>=25): return 'CRITICAL'
    if injured>0 or vulnerable_total>0 or (affected_known and affected>=10): return 'HIGH'
    if affected_known and affected>=3 and priority=='LOW': return 'MEDIUM'
    return priority
def page(request,page='index'):
    allowed={'index','login','register','admin','gov','ngo','gov_volunteer','ngo_volunteer','govt_driver','ngo_driver','citizen'}
    if page not in allowed: page='index'
    return render(request,f'{page}.html')
@require_http_methods(['GET','POST'])
def me(request):
    if request.method=='POST': return error('Use login or register endpoint.')
    if not request.user.is_authenticated: return JsonResponse({'authenticated':False})
    p=profile(request)
    return JsonResponse({'authenticated':True,'id':request.user.id,'name':request.user.get_full_name() or request.user.username,'email':request.user.email,'role':p.role if p else 'CITIZEN','approval':p.approval if p else 'APPROVED','organization':p.organization.name if p and p.organization else None,'dashboard':ROLE_PAGE.get(p.role,'citizen.html') if p else 'citizen.html'})
@require_http_methods(['POST'])
def login_view(request):
    d=payload(request); user=authenticate(request,username=(d.get('email') or '').lower(),password=d.get('password',''))
    if not user: return error('Email or password is incorrect.',401)
    p=getattr(user,'profile',None)
    if p and p.approval in ('REJECTED','SUSPENDED'): return error('This account is '+p.approval.lower()+'. Contact an administrator.',403)
    login(request,user); return JsonResponse({'ok':True,'dashboard':ROLE_PAGE.get(p.role,'citizen.html') if p else 'citizen.html','approval':p.approval if p else 'APPROVED'})
@require_http_methods(['POST'])
def logout_view(request): logout(request); return JsonResponse({'ok':True})
@require_http_methods(['POST'])
def register(request):
    d=payload(request); role=d.get('role','CITIZEN'); valid={x[0] for x in Profile.ROLES if x[0]!='ADMIN'}
    if role not in valid: return error('Select a valid registration role.')
    email=(d.get('email') or '').strip().lower(); password=d.get('password',''); name=(d.get('name') or '').strip()
    try: validate_email(email)
    except ValidationError: return error('Enter a valid email address.')
    if not name or len(password)<8: return error('Name and password (at least 8 characters) are required.')
    if password!=d.get('confirm'): return error('Password and confirmation do not match.')
    required={'GOV':['organization','department','designation'],'NGO':['organization','designation'],'GOV_VOL':['organization','department','skills'],'NGO_VOL':['organization','skills','availability'],'GOV_DRIVER':['organization','license_number'],'NGO_DRIVER':['organization','license_number']}.get(role,[])
    if any(not str(d.get(field,'')).strip() for field in required): return error('Complete the required details for the selected role.')
    if User.objects.filter(username=email).exists(): return error('An account with this email already exists.')
    org=None; oname=(d.get('organization') or '').strip()
    if role in ('NGO','NGO_VOL','NGO_DRIVER') and oname:
        org=Organization.objects.filter(name__iexact=oname,kind='NGO').first()
        if not org and role=='NGO': org=Organization.objects.create(name=oname,kind='NGO')
        if not org: return error('Select an existing NGO affiliation or register as an NGO Coordinator first.')
    elif role in ('GOV','GOV_VOL','GOV_DRIVER'):
        org=Organization.objects.filter(name__iexact=oname,kind='GOV').first() if oname else None
        if not org and role=='GOV' and oname: org=Organization.objects.create(name=oname,kind='GOV')
        if not org: return error('Select an existing Government organization or register as a Government Official first.')
    approval='APPROVED' if role=='CITIZEN' else 'PENDING'
    u=User.objects.create_user(username=email,email=email,password=password,first_name=name[:150]); Profile.objects.create(user=u,role=role,organization=org,approval=approval,phone=d.get('phone',''),details={k:v for k,v in d.items() if k not in ('password','confirm','email','name','phone','organization')})
    return JsonResponse({'ok':True,'approval':approval,'message':'Registration received. Please sign in after approval.'},status=201)
@login_required
def dashboard(request):
    p=profile(request); qs=Emergency.objects.all()
    if p and p.role=='CITIZEN': qs=qs.filter(reporter=request.user)
    if p and p.role=='NGO': qs=(qs.filter(status='OPEN') | qs.filter(accepted_by=p.organization)) if p.organization else qs.filter(status='OPEN')
    if p and p.role=='GOV': qs=(qs.filter(status='OPEN') | qs.filter(accepted_by=p.organization)) if p.organization else qs.filter(status='OPEN')
    if p and p.role in ('GOV_VOL','NGO_VOL','GOV_DRIVER','NGO_DRIVER'): qs=qs.filter(assignments__user=request.user).distinct()
    items=qs.order_by('-created_at')[:100]
    all_emergencies=Emergency.objects.all()
    active_emergencies=all_emergencies.filter(status__in=['ACCEPTED','IN_PROGRESS'])
    assignment_rows=Assignment.objects.filter(status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED'])
    shelter_rows=Shelter.objects.all()
    fund_rows=FundTransaction.objects.filter(kind='ALLOCATION')
    donation_rows=Donation.objects.filter(status='PAYMENT_VERIFIED',demo=False,provider_reference__gt='')
    if p and p.role in ('GOV','NGO') and p.organization_id:
        organization_emergencies=all_emergencies.filter(accepted_by_id=p.organization_id)
        active_emergencies=organization_emergencies.filter(status__in=['ACCEPTED','IN_PROGRESS'])
        assignment_rows=assignment_rows.filter(organization_id=p.organization_id)
        shelter_rows=shelter_rows.filter(organization_id=p.organization_id)
        fund_rows=fund_rows.filter(organization_id=p.organization_id)
        donation_rows=donation_rows.filter(campaign__organization_id=p.organization_id)
        metric_emergencies=organization_emergencies
    else:
        metric_emergencies=all_emergencies
        if p and p.role=='GOV' and p.organization_id:
            fund_rows=fund_rows.filter(organization_id=p.organization_id)
            donation_rows=donation_rows.filter(campaign__organization_id=p.organization_id)
        elif p and p.role=='CITIZEN':
            donation_rows=donation_rows.filter(donor=request.user)
    metric_total=metric_emergencies.count()
    metric_resolved=metric_emergencies.filter(status='RESOLVED').count()
    authorization_rows=AllocationAuthorization.objects.filter(status='PENDING')
    if p and p.role=='NGO' and p.organization_id:
        authorization_rows=authorization_rows.filter(organization_id=p.organization_id)
    allocated=fund_rows.aggregate(v=Sum('amount'))['v'] or 0
    confirmed=donation_rows.aggregate(v=Sum('amount'))['v'] or 0
    demo_rows=FundTransaction.objects.filter(kind='DEMO_DONATION',demo=True)
    if p and p.role in ('GOV','NGO'): demo_rows=demo_rows.filter(organization_id=p.organization_id)
    elif p and p.role=='CITIZEN': demo_rows=demo_rows.filter(donation__donor=request.user)
    demo_confirmed=demo_rows.aggregate(v=Sum('amount'))['v'] or 0
    high_priority=active_emergencies.filter(priority__in=['CRITICAL','HIGH']).values('location').distinct().count()
    affected=metric_emergencies.aggregate(v=Sum('affected'))['v'] or 0
    counts={'users':User.objects.count(),'gov_officials':Profile.objects.filter(role='GOV').count(),'ngos':Organization.objects.filter(kind='NGO').count(),'pending_approvals':Profile.objects.filter(approval='PENDING').count(),'open_emergencies':Emergency.objects.filter(status='OPEN').count(),'pending_verification':qs.filter(status='OPEN',verification='Pending').count(),'accepted_requests':qs.filter(status='ACCEPTED').count(),'pending_allocation_authorizations':authorization_rows.count(),'active_operations':active_emergencies.count(),'assignments':assignment_rows.count(),'shelters':shelter_rows.count(),'confirmed_donations':str(confirmed),'demo_confirmed_donations':str(demo_confirmed),'high_priority_zones':high_priority,'affected_population':affected,'relief_fulfillment':round(metric_resolved*100/metric_total) if metric_total else 0,'allocated_funds':str(allocated),'recent_activity':EventLog.objects.filter(created_at__gte=timezone.now()-timedelta(hours=24)).count(),'my_assignments':Assignment.objects.filter(user=request.user,status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).count(),'my_dispatches':Dispatch.objects.filter(driver=request.user).count(),'my_notifications':Notification.objects.filter(user=request.user,read_at__isnull=True).count(),'my_requests':Emergency.objects.filter(reporter=request.user).count() if p and p.role=='CITIZEN' else 0}
    thresholds=shelter_capacity_thresholds()
    return JsonResponse({'counts':counts,'emergencies':[emergency_json(e) for e in items],'shelters':[shelter_json(s,thresholds) for s in shelter_rows.select_related('organization').order_by('name')]})
@login_required
def users(request):
    p=profile(request)
    if not p or p.role!='ADMIN': return error('Administrator access required.',403)
    qs=Profile.objects.select_related('user','organization','approval_decided_by').all()
    if request.GET.get('role'): qs=qs.filter(role=request.GET['role'])
    if request.GET.get('approval'): qs=qs.filter(approval=request.GET['approval'])
    if request.GET.get('organization'): qs=qs.filter(organization__name__icontains=request.GET['organization'].strip())
    if request.GET.get('q'):
        q=request.GET['q'].strip(); qs=qs.filter(Q(user__first_name__icontains=q)|Q(user__last_name__icontains=q)|Q(user__email__icontains=q)|Q(organization__name__icontains=q))
    orderings={'recent':'-user__date_joined','oldest':'user__date_joined','name':'user__first_name','email':'user__email'}
    ordering=orderings.get(request.GET.get('sort','recent'))
    try: limit=min(100,max(1,int(request.GET.get('limit',25)))); offset=max(0,int(request.GET.get('offset',0)))
    except ValueError: return error('Limit and offset must be whole numbers.')
    qs=qs.order_by(ordering,'user__pk'); total=qs.count(); page=list(qs[offset:offset+limit]); emails=[x.user.email for x in page]
    history={email:[] for email in emails}
    decisions=EventLog.objects.filter(target__in=emails,action__in=['Registration approved','Registration rejected','Team registration approved','Team registration rejected','Account approved','Account rejected','Account suspended']).select_related('actor').order_by('created_at')
    for event in decisions:
        history[event.target].append({'action':event.action,'actor':(event.actor.get_full_name() or event.actor.email or event.actor.username) if event.actor else 'System','reason':event.detail.get('reason',''),'created_at':event.created_at.isoformat()})
    results=[{'id':x.user_id,'name':x.user.get_full_name(),'email':x.user.email,'role':x.get_role_display(),'role_code':x.role,'approval':x.approval,'organization':x.organization.name if x.organization else None,'organization_id':x.organization_id,'joined':x.user.date_joined.isoformat(),'approval_history':history[x.user.email]} for x in page]
    return JsonResponse({'results':results,'pagination':{'total':total,'limit':limit,'offset':offset,'next_offset':offset+limit if offset+limit<total else None,'previous_offset':max(0,offset-limit) if offset else None},'filters':{'role':request.GET.get('role',''),'approval':request.GET.get('approval',''),'organization':request.GET.get('organization',''),'sort':request.GET.get('sort','recent')}})
@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy with another account update. Refresh and try again.')
@transaction.atomic
def user_status(request,pk):
    actor=profile(request)
    if not actor or actor.role!='ADMIN': return error('Administrator access required.',403)
    target=Profile.objects.select_related('user').filter(user_id=pk).first()
    if not target: return error('User not found.',404)
    if target.user_id==request.user.id: return error('You cannot suspend your own account.',400)
    d=payload(request); status=d.get('status'); reason=str(d.get('reason','')).strip()
    if status not in ('APPROVED','SUSPENDED','REJECTED'): return error('Choose a valid account status.')
    if status=='REJECTED' and not reason: return error('A rejection reason is required.')
    target.approval=status; target.approval_decided_at=timezone.now(); target.approval_decided_by=request.user; target.rejection_reason=reason if status=='REJECTED' else ''; target.save(update_fields=['approval','approval_decided_at','approval_decided_by','rejection_reason']); EventLog.objects.create(actor=request.user,action='Account '+status.lower(),target=target.user.email,detail={'reason':reason})
    notify(target.user,'Account status changed',f'Your account status is now {status.lower()}.',ROLE_PAGE.get(target.role,'/'))
    return JsonResponse({'ok':True,'approval':status})

@login_required
@require_http_methods(['PATCH'])
@sqlite_write_conflict('SQLite is busy with another account update. Refresh and try again.')
@transaction.atomic
def update_user_role(request,pk):
    actor=profile(request)
    if not actor or actor.role!='ADMIN' or actor.approval!='APPROVED': return error('Approved Administrator access required.',403)
    target=Profile.objects.select_related('user','organization').filter(user_id=pk).first()
    if not target: return error('User not found.',404)
    if target.user_id==request.user.id: return error('You cannot change your own role or organization.',400)
    d=payload(request); role=d.get('role')
    allowed_roles={value for value,_ in Profile.ROLES}
    if role not in allowed_roles: return error('Choose a valid account role.')
    if Assignment.objects.filter(user=target.user,status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).exists(): return error('Complete or cancel this user’s active assignments before changing their role or organization.',409)
    organization_id=d.get('organization_id')
    org=None
    if role not in ('ADMIN','CITIZEN'):
        if not organization_id: return error('Select the organization required for this role.')
        org=Organization.objects.filter(pk=organization_id).first()
        if not org: return error('Organization not found.')
        expected='NGO' if role.startswith('NGO') else 'GOV'
        if org.kind!=expected: return error('The selected organization type does not match the account role.')
    elif organization_id not in (None,'',0,'0'):
        return error('Administrator and Citizen accounts cannot be affiliated with an operational organization.')
    old_role=target.role; old_org=target.organization
    approval_reset=(old_role!=role or target.organization_id!=(org.pk if org else None)) and role not in ('ADMIN','CITIZEN')
    target.role=role; target.organization=org
    update_fields=['role','organization']
    if approval_reset:
        target.approval='PENDING'; target.approval_decided_at=None; target.approval_decided_by=None; target.rejection_reason=''
        update_fields.extend(['approval','approval_decided_at','approval_decided_by','rejection_reason'])
    target.save(update_fields=update_fields)
    EventLog.objects.create(actor=request.user,action='User role or organization updated',target=target.user.email,detail={'old_role':old_role,'new_role':role,'old_organization':old_org.name if old_org else None,'new_organization':org.name if org else None,'approval_reset':approval_reset})
    notice='Your role or organization changed. An authorized reviewer must approve your new operational access.' if approval_reset else f'An Administrator updated your role to {target.get_role_display()}'+(f' in {org.name}.' if org else '.')
    notify(target.user,'Account role updated',notice,ROLE_PAGE.get(role,'/'))
    return JsonResponse({'ok':True,'role':target.get_role_display(),'role_code':target.role,'approval':target.approval,'organization':org.name if org else None,'organization_id':org.pk if org else None})
@login_required
@require_http_methods(['GET','POST'])
@sqlite_write_conflict('SQLite is busy with another settings update. Refresh and try again.')
@transaction.atomic
def settings_view(request):
    p=profile(request)
    if not p: return error('Account profile is missing.',403)
    if request.method=='GET': return JsonResponse({'name':request.user.get_full_name(),'email':request.user.email,'phone':p.phone,'role':p.get_role_display(),'approval':p.approval,'organization':p.organization.name if p.organization else None,'details':public_profile_details(p.details)})
    locked_user=User.objects.get(pk=request.user.pk)
    p=Profile.objects.filter(user=locked_user).first()
    if not p: return error('Account profile is missing.',403)
    request.user=locked_user
    d=payload(request)
    if p.role=='CITIZEN':
        unexpected=set(d)-{'name','phone'}
        if unexpected: return error('Citizens may update only their display name and contact number.',403)
        if not isinstance(d.get('name'),str) or not d['name'].strip() or len(d['name'].strip())>150:
            return error('Enter a display name between 1 and 150 characters.')
        phone=str(d.get('phone','')).strip()
        if phone and (len(phone)>30 or not re.fullmatch(r'[0-9+().\-\s]{7,30}',phone) or sum(ch.isdigit() for ch in phone)<7):
            return error('Enter a valid contact number with at least 7 digits.')
        locked_user.first_name=d['name'].strip()
        locked_user.save(update_fields=['first_name'])
        p.phone=phone
        p.save(update_fields=['phone'])
        return JsonResponse({'ok':True,'message':'Profile settings saved.'})
    name=(d.get('name') or '').strip(); new_password=d.get('new_password','')
    if new_password and not request.user.check_password(d.get('current_password','')): return error('Current password is incorrect.',403)
    if new_password and (len(new_password)<8 or new_password!=d.get('confirm_password')): return error('New password must be at least 8 characters and match confirmation.')
    if name:
        request.user.first_name=name[:150]; request.user.save(update_fields=['first_name'])
    if 'phone' in d: p.phone=str(d['phone'])[:30]
    if isinstance(d.get('details'),dict): p.details={**p.details,**d['details']}
    if 'availability' in d:
        if p.role not in ('GOV_VOL','NGO_VOL','GOV_DRIVER','NGO_DRIVER'): return error('Availability can only be updated by responders and drivers.',403)
        if d['availability'] not in ('AVAILABLE','UNAVAILABLE'): return error('Availability must be Available or Unavailable.')
        p.details={**p.details,'availability':d['availability']}
    p.save(update_fields=['phone','details'])
    if new_password:
        request.user.set_password(new_password); request.user.save(update_fields=['password']); update_session_auth_hash(request,request.user)
    return JsonResponse({'ok':True,'message':'Profile settings saved.'})

@login_required
@require_http_methods(['GET','POST'])
def system_preferences(request):
    p=profile(request)
    if not p or p.role!='ADMIN' or p.approval!='APPROVED': return error('Approved administrator access required.',403)
    default_shelter_thresholds={'high_occupancy_pct':50,'nearly_full_pct':85}
    defaults={'platform_name':'DRRAS','support_email':'','default_emergency_priority':'MEDIUM','public_notice':'','shelter_capacity_thresholds':default_shelter_thresholds}
    if request.method=='GET':
        saved={row.key:row.value for row in SystemPreference.objects.all()}
        return JsonResponse({'preferences':{**defaults,**saved}})
    d=payload(request); name=(d.get('platform_name') or '').strip(); email=(d.get('support_email') or '').strip(); priority=d.get('default_emergency_priority','MEDIUM'); notice=(d.get('public_notice') or '').strip()
    if not name or len(name)>80: return error('Platform name is required and must be at most 80 characters.')
    if email:
        try: validate_email(email)
        except ValidationError: return error('Enter a valid support email address.')
    if priority not in ('CRITICAL','HIGH','MEDIUM','LOW'): return error('Choose a valid default emergency priority.')
    try:
        high_occupancy=int(d.get('shelter_high_occupancy_pct',default_shelter_thresholds['high_occupancy_pct']))
        nearly_full=int(d.get('shelter_nearly_full_pct',default_shelter_thresholds['nearly_full_pct']))
    except (TypeError,ValueError): return error('Shelter occupancy thresholds must be whole percentages.')
    if not 1<=high_occupancy<nearly_full<100: return error('Set high occupancy from 1–98% and nearly full above it but below 100%.')
    shelter_thresholds={'high_occupancy_pct':high_occupancy,'nearly_full_pct':nearly_full}
    values={'platform_name':name,'support_email':email,'default_emergency_priority':priority,'public_notice':notice[:1000],'shelter_capacity_thresholds':shelter_thresholds}
    for key,value in values.items():
        SystemPreference.objects.update_or_create(key=key,defaults={'value':value,'updated_by':request.user})
    EventLog.objects.create(actor=request.user,action='System preferences updated',target='DRRAS',detail={'keys':list(values)})
    return JsonResponse({'ok':True,'preferences':values})

@require_http_methods(['GET'])
def public_preferences(request):
    defaults={'platform_name':'DRRAS','support_email':'','public_notice':'','shelter_capacity_thresholds':{'high_occupancy_pct':50,'nearly_full_pct':85}}
    saved={row.key:row.value for row in SystemPreference.objects.filter(key__in=defaults)}
    return JsonResponse({'preferences':{**defaults,**saved}})

@login_required
@require_http_methods(['GET','POST'])
def training(request):
    p=profile(request)
    responder_roles=('GOV_VOL','NGO_VOL','GOV_DRIVER','NGO_DRIVER')
    if not p or (p.role not in responder_roles and p.role!='ADMIN'): return error('Safety training is available to approved responders and Administrators.',403)
    if p.role!='ADMIN' and p.approval!='APPROVED': return error('Your responder account must be approved to access training.',403)
    if request.method=='POST':
        if p.role not in responder_roles: return error('Only a responder can acknowledge training modules.',403)
        d=payload(request); training_id=d.get('training_id')
        try: training_id=int(training_id)
        except (ValueError,TypeError): return error('Select a valid training module.')
        module=SafetyTraining.objects.filter(pk=training_id,active=True).first()
        if not module or p.role not in module.required_roles: return error('Training module not found for your responder role.',404)
        if d.get('acknowledged') not in (True,'true','True','on','1',1): return error('Confirm that you reviewed the training material before marking it complete.')
        completion,_=TrainingCompletion.objects.get_or_create(training=module,user=request.user)
        if not completion.completed_at:
            completion.acknowledged_at=timezone.now(); completion.completed_at=timezone.now(); completion.note=(d.get('note') or '').strip()[:500]; completion.save()
            EventLog.objects.create(actor=request.user,action='Safety training completed',target=module.code,detail={'training_id':module.pk,'title':module.title})
        return JsonResponse({'ok':True,'completed_at':completion.completed_at.isoformat()})
    modules=SafetyTraining.objects.filter(active=True).order_by('category','title')
    if p.role!='ADMIN': modules=[module for module in modules if p.role in module.required_roles]
    completions={row.training_id:row for row in TrainingCompletion.objects.filter(user=request.user,training__in=modules)}
    return JsonResponse({'results':[{'id':module.pk,'code':module.code,'title':module.title,'category':module.category,'content':module.content,'required_roles':module.required_roles,'demo':module.demo,'completed_at':completions[module.pk].completed_at.isoformat() if module.pk in completions and completions[module.pk].completed_at else None,'acknowledged_at':completions[module.pk].acknowledged_at.isoformat() if module.pk in completions and completions[module.pk].acknowledged_at else None} for module in modules]})
def emergency_json(e, include_assignment_contact=False):
    assignments=e.assignments.select_related('user','organization','assigned_by').order_by('kind','user__first_name')
    dispatches=e.dispatches.select_related('driver','vehicle').order_by('created_at')
    return {'id':e.id,'reference':e.reference,'reporter_id':e.reporter_id,'category':e.category,'severity':e.severity,'priority':e.priority,'priority_override_reason':e.priority_override_reason,'description':e.description,'location':e.location,'address':e.address,'district':e.district,'latitude':e.latitude,'longitude':e.longitude,'affected':e.affected,'injured':e.injured,'vulnerable_counts':e.vulnerable_counts or {},'required_skills':[s.strip() for s in e.required_skills.split(',') if s.strip()],'needs_transport':e.needs_transport,'required_vehicle_capacity':e.required_vehicle_capacity,'status':e.status,'verification':e.verification,'accepted_by':e.accepted_by.name if e.accepted_by else None,'demo':e.demo,'created_at':e.created_at.isoformat(),'updated_at':e.updated_at.isoformat(),'history':[{'event_type':h.event_type,'from_status':h.from_status,'to_status':h.to_status,'note':h.note,'actor':h.actor.get_full_name() if h.actor else 'System','created_at':h.created_at.isoformat()} for h in e.history.select_related('actor').order_by('created_at')],'assignments':[{'id':a.id,'user_id':a.user_id,'name':a.user.get_full_name() or a.user.username,'phone':a.user.profile.phone if include_assignment_contact and hasattr(a.user,'profile') else '', 'organization_id':a.organization_id,'organization':a.organization.name if a.organization else None,'assigned_by_id':a.assigned_by_id,'assigned_by':(a.assigned_by.get_full_name() or a.assigned_by.email) if a.assigned_by else None,'created_at':a.created_at.isoformat(),'kind':a.kind,'status':a.status,'task_instructions':a.task_instructions,'completion_report':a.completion_report,'blocked_note':a.blocked_note,'acknowledged_at':a.acknowledged_at.isoformat() if a.acknowledged_at else None,'updated_at':a.updated_at.isoformat(),'history':[{'status':h.status,'note':h.note,'actor':h.actor.get_full_name() if h.actor else 'System','created_at':h.created_at.isoformat()} for h in a.history.select_related('actor').order_by('created_at')]} for a in assignments],'dispatches':[{'id':d.id,'driver':d.driver.get_full_name() or d.driver.username,'vehicle':d.vehicle.registration if d.vehicle else None,'status':d.status,'pickup_location':d.pickup_location,'cargo_details':d.cargo_details,'delivery_proof':d.delivery_proof,'delivery':delivery_json(d.delivery_record) if hasattr(d,'delivery_record') else None,'updated_at':d.updated_at.isoformat()} for d in dispatches]}
@login_required
@require_http_methods(['GET','POST'])
def emergencies(request):
    p=profile(request)
    if request.method=='GET':
        qs=Emergency.objects.select_related('reporter','accepted_by').all()
        if p and p.role=='CITIZEN': qs=qs.filter(reporter=request.user)
        if p and p.role=='NGO': qs=(qs.filter(status='OPEN') | qs.filter(accepted_by=p.organization)) if p.organization else qs.filter(status='OPEN')
        if p and p.role=='GOV': qs=(qs.filter(status='OPEN') | qs.filter(accepted_by=p.organization)) if p.organization else qs.filter(status='OPEN')
        if p and p.role in ('GOV_VOL','NGO_VOL','GOV_DRIVER','NGO_DRIVER'): qs=qs.filter(assignments__user=request.user).distinct()
        q=request.GET.get('q'); status=request.GET.get('status'); priority=request.GET.get('priority')
        if q: qs=qs.filter(Q(location__icontains=q) | Q(reference__icontains=q) | Q(description__icontains=q))
        if status: qs=qs.filter(status=status)
        if priority: qs=qs.filter(priority=priority)
        if request.GET.get('category'): qs=qs.filter(category=request.GET['category'])
        if request.GET.get('verification'): qs=qs.filter(verification=request.GET['verification'])
        try:
            limit=min(100,max(1,int(request.GET.get('limit',50)))); offset=max(0,int(request.GET.get('offset',0)))
        except ValueError: return error('Limit and offset must be whole numbers.')
        qs=qs.distinct().order_by('-created_at'); total=qs.count()
        return JsonResponse({'results':[emergency_json(e,include_assignment_contact=bool(p and p.role=='CITIZEN' and e.reporter_id==request.user.id)) for e in qs[offset:offset+limit]],'pagination':{'total':total,'limit':limit,'offset':offset,'next_offset':offset+limit if offset+limit<total else None,'previous_offset':max(0,offset-limit) if offset else None}})
    d=payload(request)
    can_report=bool(p and (p.role=='CITIZEN' or (p.role=='GOV' and p.approval=='APPROVED')))
    if not can_report: return error('Citizen or approved Government Official access is required to submit a request.',403)
    required=['category','description','address','district']
    if any(not d.get(k) for k in required): return error('Category, description, locality and Punjab district are required.')
    try: location=format_punjab_address(d['address'],d['district'])
    except ValueError as exc: return error(str(exc))
    if d.get('latitude') not in (None,'') or d.get('longitude') not in (None,''):
        if not is_punjab_coordinate(d.get('latitude'),d.get('longitude')):
            return error('Emergency coordinates must fall within Punjab.')
    def optional_count(key, default):
        value=d.get(key, default)
        if value in (None, ''): return None
        value=int(value)
        if value < 0: raise ValueError
        return value
    try:
        affected=optional_count('affected',1); injured=optional_count('injured',0)
    except (ValueError,TypeError): return error('Affected and injured counts must be non-negative whole numbers or blank when unknown.')
    vulnerable=d.get('vulnerable_counts') or {}
    if isinstance(vulnerable,str):
        try: vulnerable=json.loads(vulnerable)
        except (ValueError,TypeError): return error('Vulnerable population counts are invalid.')
    allowed_vulnerable={'children','elderly','pregnant','people_with_disabilities','infants'}
    if not isinstance(vulnerable,dict) or set(vulnerable)-allowed_vulnerable: return error('Vulnerable population counts contain unsupported categories.')
    try:
        vulnerable={key:(None if value in (None,'') else int(value)) for key,value in vulnerable.items()}
        if any(value is not None and value < 0 for value in vulnerable.values()): raise ValueError
    except (ValueError,TypeError): return error('Vulnerable population counts must be whole numbers.')
    known_vulnerable=sum(value for value in vulnerable.values() if value is not None)
    if affected is not None and ((injured is not None and injured>affected) or known_vulnerable>affected): return error('Injured and vulnerable counts cannot exceed the affected population.')
    severity=d.get('severity','MODERATE')
    if severity not in dict(Emergency.SEVERITIES): return error('Choose a valid incident severity.')
    priority=calculate_emergency_priority(severity,affected,injured,vulnerable)
    import uuid
    # Government incident intake may still record operational transport needs;
    # Citizens do not submit resource or vehicle requests from this form.
    needs_transport=bool(p.role=='GOV' and d.get('needs_transport') in (True,'true','True','on','1',1))
    try: required_vehicle_capacity=max(0,int(d.get('required_vehicle_capacity',0))) if needs_transport else 0
    except (ValueError,TypeError): return error('Vehicle capacity must be a whole number.')
    raw_skills=d.get('required_skills','') if p.role=='GOV' else ''
    required_skills=', '.join(dict.fromkeys(s.strip() for s in raw_skills.split(',') if s.strip())) if isinstance(raw_skills,str) else ''
    e=Emergency.objects.create(reference='PB-'+uuid.uuid4().hex[:8].upper(),reporter=request.user,category=d['category'],severity=severity,priority=priority,description=d['description'],location=location,address=str(d['address']).strip(),district=str(d['district']).strip(),affected=affected,injured=injured,vulnerable_counts=vulnerable,latitude=d.get('latitude') or None,longitude=d.get('longitude') or None,needs_transport=needs_transport,required_vehicle_capacity=required_vehicle_capacity,required_skills=required_skills)
    record_emergency_event(e,request.user,'SUBMITTED','',e.status,'Emergency request submitted')
    EventLog.objects.create(actor=request.user,action='Emergency submitted',target=e.reference)
    for target in Profile.objects.filter(role__in=['GOV','NGO'],approval='APPROVED').select_related('user'):
        notify(target.user,'New emergency request',f'{e.reference}: {e.category} reported at {e.location}.','/gov.html')
    return JsonResponse({'ok':True,'emergency':emergency_json(e)},status=201)
@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy accepting this emergency. Refresh and try again.')
def accept_emergency(request,pk):
    p=profile(request); d=payload(request); e=Emergency.objects.filter(pk=pk).first()
    if not e: return error('Emergency not found.',404)
    if not p or p.role not in ('GOV','NGO') or p.approval!='APPROVED': return error('An approved official or NGO coordinator is required.',403)
    org=p.organization
    if not org: return error('Your account is not linked to an organization.',403)
    try:
        with transaction.atomic():
            # A conditional UPDATE is an atomic compare-and-set on SQLite. It
            # makes only the first OPEN->ACCEPTED transition succeed even
            # though SQLite does not implement row-level SELECT FOR UPDATE.
            changes={'status':'ACCEPTED','accepted_by_id':org.pk}
            if p.role=='GOV': changes['verification']='Verified'
            won=Emergency.objects.filter(pk=pk,status='OPEN').update(**changes)
            if not won:
                e=Emergency.objects.select_related('accepted_by').filter(pk=pk).first()
                if not e: return error('Emergency not found.',404)
                if e.accepted_by_id: return error(f'This request has already been accepted by {e.accepted_by.name}.',409)
                return error('This request has already been closed.',409)
            e=Emergency.objects.select_related('reporter','accepted_by').get(pk=pk)
            record_emergency_event(e,request.user,'ACCEPTED','OPEN',e.status,org.name)
            EventLog.objects.create(actor=request.user,action='Emergency accepted',target=e.reference,detail={'organization':org.name})
            notify(e.reporter,'Response organization assigned',f'{org.name} accepted {e.reference}.','/citizen.html')
    except OperationalError as exc:
        if 'locked' in str(exc).casefold(): return error('Another organization is updating this request. Refresh and try again.',409)
        raise
    return JsonResponse({'ok':True,'emergency':emergency_json(e)})

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy with another emergency update. Refresh and try again.')
@transaction.atomic
def cancel_emergency(request,pk):
    e=Emergency.objects.select_related('reporter','accepted_by').filter(pk=pk).first()
    if not e: return error('Emergency not found.',404)
    p=profile(request); d=payload(request); reason=(d.get('reason') or '').strip()
    if e.status in ('RESOLVED','CANCELLED'): return error('A resolved or cancelled request cannot be cancelled again.',409)
    owner_open=e.reporter_id==request.user.id and e.status=='OPEN' and bool(p and (p.role=='CITIZEN' or (p.role=='GOV' and p.approval=='APPROVED')))
    admin=bool(p and p.role=='ADMIN' and p.approval=='APPROVED')
    responsible=bool(p and p.role in ('GOV','NGO') and p.approval=='APPROVED' and p.organization_id==e.accepted_by_id and e.accepted_by_id)
    if not (owner_open or admin or responsible): return error('Only the reporting Citizen for an open request, its responsible organization, or an approved Administrator can cancel it.',403)
    if (admin or responsible or (owner_open and p.role=='GOV')) and not reason: return error('Provide a cancellation reason for the operational record.')
    previous=e.status; e.status='CANCELLED'; e.save(update_fields=['status'])
    active=e.assignments.filter(status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED'])
    responders=list(active.select_related('user'))
    for assignment in responders:
        assignment.status='CANCELLED'; assignment.save(update_fields=['status','updated_at'])
        AssignmentEvent.objects.create(assignment=assignment,actor=request.user,status='CANCELLED',note=reason or 'Emergency cancelled')
        notify(assignment.user,'Emergency request cancelled',f'{e.reference} has been cancelled. Reason: {reason or "Cancelled by reporting Citizen"}.',ROLE_PAGE.get(assignment.user.profile.role,'/'))
    for dispatch in Dispatch.objects.filter(emergency=e).exclude(status__in=['DELIVERED','CANCELLED']):
        dispatch.status='CANCELLED'; dispatch.save(update_fields=['status','updated_at'])
        DispatchEvent.objects.create(dispatch=dispatch,actor=request.user,status='CANCELLED',note=reason or 'Emergency cancelled')
        notify(dispatch.driver,'Dispatch cancelled',f'Dispatch for {e.reference} has been cancelled.','/govt_driver.html')
    record_emergency_event(e,request.user,'CANCELLED',previous,e.status,reason or 'Cancelled by reporting Citizen')
    EventLog.objects.create(actor=request.user,action='Emergency cancelled',target=e.reference,detail={'reason':reason,'previous_status':previous})
    notify(e.reporter,'Emergency request cancelled',f'{e.reference} is now cancelled. {reason}'.strip(),'/citizen.html')
    return JsonResponse({'ok':True,'emergency':emergency_json(e)})
@login_required
@require_http_methods(['POST'])
def triage_emergency(request,pk):
    p=profile(request); e=Emergency.objects.filter(pk=pk).first()
    if not e: return error('Emergency not found.',404)
    if not p or p.role!='GOV' or p.approval!='APPROVED': return error('Approved Government Official access required.',403)
    data=payload(request); verification=data.get('verification'); priority=data.get('priority'); reason=str(data.get('priority_override_reason','')).strip()
    if verification not in ('Verified','Rejected','Pending'): return error('Choose Verified, Rejected or Pending.')
    if priority is not None:
        if priority not in dict(Emergency.PRIORITIES) or not reason: return error('A valid priority and override reason are required.')
    e.verification=verification
    e.save(update_fields=['verification','updated_at'])
    EventLog.objects.create(actor=request.user,action='Emergency triage updated',target=e.reference,detail={'verification':verification})
    if priority is not None:
        old=e.priority; e.priority=priority; e.priority_override_by=request.user; e.priority_override_reason=reason[:2000]; e.priority_overridden_at=timezone.now()
        e.save(update_fields=['priority','priority_override_by','priority_override_reason','priority_overridden_at','updated_at'])
        EventLog.objects.create(actor=request.user,action='Emergency priority overridden',target=e.reference,detail={'from':old,'to':priority,'reason':reason[:2000]})
    record_emergency_event(e,request.user,'TRIAGE',e.status,e.status,verification)
    notify(e.reporter,'Emergency request reviewed',f'{e.reference} verification status: {verification}.','/citizen.html')
    return JsonResponse({'ok':True,'verification':verification,'priority':e.priority})
@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy allocating responders. Refresh availability and try again.')
@transaction.atomic
def assign(request,pk):
    p=profile(request); d=payload(request); e=Emergency.objects.filter(pk=pk).first()
    if not e: return error('Emergency not found.',404)
    if not p or p.role not in ('GOV','NGO') or p.approval!='APPROVED' or e.accepted_by!=p.organization: return error('Only the accepting organization can assign resources.',403)
    try:
        with transaction.atomic(): return perform_assignment(e,p.organization,request.user,d)
    except IntegrityError:
        return error('A responder or vehicle was assigned in a competing operation. Refresh availability and try again.',409)
    except OperationalError as exc:
        if 'locked' in str(exc).casefold(): return error('Another allocation is being saved. Refresh availability and try again.',409)
        raise

def perform_assignment(e,organization,actor,d):
    if e.status not in ('ACCEPTED','IN_PROGRESS'): return error('Resources can only be assigned to an accepted active request.',409)
    ids=d.get('user_ids',[]); kind=d.get('kind','VOL'); requested_vehicle_ids=d.get('vehicle_ids',[])
    if kind not in ('VOL','DRIVER') or not isinstance(ids,list) or not ids: return error('Select one or more eligible responders.')
    if not isinstance(requested_vehicle_ids,list): return error('Vehicle selections must be a list.')
    if kind!='DRIVER' and requested_vehicle_ids: return error('Vehicles can only be assigned alongside drivers.')
    if kind=='DRIVER' and e.needs_transport and not e.assignments.filter(kind='VOL').exclude(status='CANCELLED').exists(): return error('Assign at least one approved volunteer before assigning transport drivers.')
    expected={'VOL':['GOV_VOL','NGO_VOL'],'DRIVER':['GOV_DRIVER','NGO_DRIVER']}[kind]
    candidates=[]; team_skills=set()
    try: selected_user_ids=list(dict.fromkeys(int(uid) for uid in ids))
    except (TypeError,ValueError): return error('Responder IDs must be whole numbers.')
    locked_user_ids=list(User.objects.filter(pk__in=selected_user_ids).order_by('pk').values_list('pk',flat=True))
    if len(locked_user_ids)!=len(selected_user_ids): return error('One or more selected users do not exist.')
    list(Profile.objects.filter(user_id__in=locked_user_ids).order_by('user_id').values_list('pk',flat=True))
    candidates_by_id={candidate.pk:candidate for candidate in User.objects.filter(pk__in=locked_user_ids).select_related('profile','profile__organization')}
    for uid in selected_user_ids:
        candidate=candidates_by_id.get(uid)
        if not candidate: return error('One or more selected users do not exist.')
        cp=candidate.profile
        if cp.role not in expected or cp.approval!='APPROVED' or cp.organization_id!=organization.pk: return error('All selected responders must be approved and belong to your organization.',403)
        candidate_details=cp.details if isinstance(cp.details,dict) else {}
        if candidate_details.get('availability','AVAILABLE')!='AVAILABLE': return error(f'{candidate.get_full_name()} is not currently available.',409)
        if Assignment.objects.filter(user=candidate,status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).exists(): return error(f'{candidate.get_full_name()} already has an active assignment.',409)
        raw_skills=candidate_details.get('skills',[])
        if isinstance(raw_skills,str): skill_values=raw_skills.replace(';',',').split(',')
        elif isinstance(raw_skills,list): skill_values=raw_skills
        else: skill_values=[]
        team_skills.update(str(skill).strip().casefold() for skill in skill_values if str(skill).strip())
        candidates.append(candidate)
    required_skills={skill.strip().casefold() for skill in e.required_skills.split(',') if skill.strip()}
    if kind=='VOL' and required_skills:
        missing_skills=required_skills-team_skills
        if missing_skills: return error('The selected volunteer team is missing required skills: '+', '.join(sorted(missing_skills)),409)
    available_vehicles=[]
    if kind=='DRIVER':
        vehicle_query=Vehicle.objects.filter(organization=organization,capacity__gte=e.required_vehicle_capacity).exclude(dispatches__status__in=['ASSIGNED','ACCEPTED','IN_TRANSIT','EXCEPTION'])
        if requested_vehicle_ids:
            try: vehicle_ids=list(dict.fromkeys(int(vehicle_id) for vehicle_id in requested_vehicle_ids))
            except (TypeError,ValueError): return error('Vehicle IDs must be whole numbers.')
            if len(vehicle_ids)!=len(requested_vehicle_ids): return error('Choose each vehicle only once.')
            if len(vehicle_ids)!=len(candidates): return error('Choose exactly one vehicle for each selected driver.')
            vehicle_query=vehicle_query.filter(pk__in=vehicle_ids)
            available_vehicles=list(vehicle_query.order_by('id'))
            if len(available_vehicles)!=len(vehicle_ids): return error('One or more selected vehicles are unavailable, outside your organization, or below the required capacity.',409)
            by_id={v.pk:v for v in available_vehicles}; available_vehicles=[by_id[vid] for vid in vehicle_ids]
        else:
            available_vehicles=list(vehicle_query.order_by('id')[:len(candidates)])
        if available_vehicles:
            locked_vehicle_ids=[vehicle.pk for vehicle in available_vehicles]
            still_available=set(Vehicle.objects.filter(pk__in=locked_vehicle_ids,organization=organization,capacity__gte=e.required_vehicle_capacity).exclude(dispatches__status__in=['ASSIGNED','ACCEPTED','IN_TRANSIT','EXCEPTION']).values_list('pk',flat=True))
            if still_available!=set(locked_vehicle_ids): return error('One or more vehicles were just assigned elsewhere. Refresh availability and try again.',409)
    if kind=='DRIVER' and len(available_vehicles)<len(candidates): return error('Not enough available vehicles for the selected drivers.',409)
    created=[]
    for index,candidate in enumerate(candidates):
        a,created_now=Assignment.objects.get_or_create(emergency=e,user=candidate,kind=kind,defaults={'organization':organization,'assigned_by':actor,'task_instructions':d.get('task_instructions','')}); created.append(a.pk)
        if not created_now and d.get('task_instructions'):
            a.task_instructions=d['task_instructions']; a.save(update_fields=['task_instructions','updated_at'])
        was_closed=not created_now and a.status in ('COMPLETED','CANCELLED')
        if was_closed: a.status='ASSIGNED'; a.save(update_fields=['status'])
        if created_now or was_closed or not a.history.exists(): AssignmentEvent.objects.create(assignment=a,actor=actor,status='ASSIGNED',note=a.task_instructions or 'Responder assigned')
        if kind=='DRIVER':
            vehicle=available_vehicles[index]; previous_dispatch_status=Dispatch.objects.filter(emergency=e,driver=candidate).values_list('status',flat=True).first(); dispatch,dispatch_created=Dispatch.objects.update_or_create(emergency=e,driver=candidate,defaults={'organization':organization,'vehicle':vehicle,'pickup_location':d.get('pickup_location',''),'destination':e.location,'cargo_details':d.get('cargo_details',''),'trip_instructions':d.get('task_instructions',''),'status':'ASSIGNED'})
            if dispatch_created or previous_dispatch_status!='ASSIGNED': DispatchEvent.objects.create(dispatch=dispatch,actor=actor,status='ASSIGNED',note='Dispatch created' if dispatch_created else 'Dispatch reassigned')
        if created_now or was_closed: notify(candidate,'New response assignment',f'You have been assigned to {e.reference} at {e.location}.',ROLE_PAGE.get(candidate.profile.role,'/'))
    EventLog.objects.create(actor=actor,action='Resources assigned',target=e.reference,detail={'assignment_ids':created})
    return JsonResponse({'ok':True,'assignment_ids':created})

def allocation_authorization_json(row):
    profiles={profile.user_id:profile for profile in Profile.objects.filter(user_id__in=row.user_ids).select_related('user')}
    users=[]
    for user_id in row.user_ids:
        member=profiles.get(user_id)
        if not member:
            users.append({'id':user_id,'name':f'Unknown responder #{user_id}','role':'Unknown','approval':'UNKNOWN','availability':'UNKNOWN','active_assignment':False,'skills':''})
            continue
        details=member.details if isinstance(member.details,dict) else {}
        users.append({'id':user_id,'name':member.user.get_full_name() or member.user.email,'role':member.get_role_display(),'approval':member.approval,'availability':details.get('availability','AVAILABLE'),'active_assignment':Assignment.objects.filter(user_id=user_id,status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).exists(),'skills':details.get('skills','')})
    vehicles={vehicle.pk:vehicle for vehicle in Vehicle.objects.filter(pk__in=row.vehicle_ids)}
    vehicle_rows=[]
    for vehicle_id in row.vehicle_ids:
        vehicle=vehicles.get(vehicle_id)
        if not vehicle:
            vehicle_rows.append({'id':vehicle_id,'registration':f'Unknown vehicle #{vehicle_id}','capacity':0,'available':False})
            continue
        busy=vehicle.dispatches.filter(status__in=['ASSIGNED','ACCEPTED','IN_TRANSIT','EXCEPTION']).exists()
        vehicle_rows.append({'id':vehicle.pk,'registration':vehicle.registration,'capacity':vehicle.capacity,'available':not busy,'organization':vehicle.organization.name})
    stock={'id':row.inventory_id,'item':row.inventory.item,'category':row.inventory.category,'warehouse':row.inventory.warehouse,'warehouse_location':row.inventory.warehouse_location,'unit':row.inventory.unit,'available_quantity':row.inventory.quantity} if row.inventory_id else None
    return {'id':row.pk,'emergency_id':row.emergency_id,'emergency':row.emergency.reference,'location':row.emergency.location,'emergency_status':row.emergency.status,'required_skills':[skill.strip() for skill in row.emergency.required_skills.split(',') if skill.strip()],'required_vehicle_capacity':row.emergency.required_vehicle_capacity,'organization_id':row.organization_id,'organization':row.organization.name,'requested_by':row.requested_by.get_full_name() or row.requested_by.email,'kind':row.kind,'user_ids':row.user_ids,'users':users,'vehicle_ids':row.vehicle_ids,'vehicles':vehicle_rows,'inventory':stock,'requested_quantity':row.requested_quantity,'task_instructions':row.task_instructions,'pickup_location':row.pickup_location,'cargo_details':row.cargo_details,'status':row.status,'reviewed_by':row.reviewed_by.get_full_name() or row.reviewed_by.email if row.reviewed_by else None,'reviewed_at':row.reviewed_at.isoformat() if row.reviewed_at else None,'decision_note':row.decision_note,'executed_at':row.executed_at.isoformat() if row.executed_at else None,'created_at':row.created_at.isoformat(),'history':[{'event_type':event.event_type,'actor':event.actor.get_full_name() or event.actor.email if event.actor else 'System','detail':event.detail,'created_at':event.created_at.isoformat()} for event in row.history.select_related('actor').order_by('created_at')]}

@login_required
@require_http_methods(['GET','POST'])
@transaction.atomic
def allocation_authorizations(request):
    p=profile(request)
    if not p or p.role not in ('GOV','NGO') or p.approval!='APPROVED' or not p.organization: return error('Approved Government or NGO coordinator access required.',403)
    if request.method=='POST':
        if p.role!='NGO' or p.organization.kind!='NGO': return error('Only an NGO Coordinator can submit allocation proposals.',403)
        d=payload(request); emergency=Emergency.objects.filter(pk=d.get('emergency_id'),accepted_by=p.organization).first()
        if not emergency: return error('Choose an active emergency accepted by your NGO.',404)
        if emergency.status not in ('ACCEPTED','IN_PROGRESS'): return error('Proposals can only be made for active accepted requests.',409)
        kind=d.get('kind','VOL'); user_ids=d.get('user_ids',[]); vehicle_ids=d.get('vehicle_ids',[]); inventory=None; requested_quantity=None
        if not isinstance(user_ids,list) or not isinstance(vehicle_ids,list): return error('Resource selections must be lists.')
        if kind=='STOCK':
            if user_ids or vehicle_ids: return error('A stock proposal cannot include responders or vehicles.')
            try: inventory_id=int(d.get('inventory_id')); requested_quantity=int(d.get('quantity'))
            except (ValueError,TypeError): return error('Select an inventory item and a whole-number quantity.')
            inventory=Inventory.objects.filter(pk=inventory_id,organization=p.organization).first()
            if not inventory: return error('Inventory item not found in this NGO.',404)
            if requested_quantity<=0 or requested_quantity>inventory.quantity: return error('Requested quantity must be available in the selected warehouse.',409)
            task_instructions=str(d.get('note','')).strip()
        elif kind in ('VOL','DRIVER'):
            if not user_ids: return error('Select one or more responders for the proposal.')
            if kind=='VOL' and vehicle_ids: return error('Volunteer proposals cannot include vehicles.')
            task_instructions=str(d.get('task_instructions','')).strip()
        else: return error('Choose volunteers, drivers, or relief supplies for the proposal.')
        if kind in ('VOL','DRIVER'):
            try: user_ids=list(dict.fromkeys(int(value) for value in user_ids)); vehicle_ids=list(dict.fromkeys(int(value) for value in vehicle_ids))
            except (ValueError,TypeError): return error('Responder and vehicle IDs must be valid whole numbers.')
            if kind=='DRIVER' and len(vehicle_ids)!=len(user_ids): return error('Choose exactly one suitable vehicle per proposed driver.')
            if len(user_ids)>20 or len(vehicle_ids)>20: return error('A proposal can include at most 20 responders and 20 vehicles.')
            expected_role='NGO_VOL' if kind=='VOL' else 'NGO_DRIVER'
            candidates=list(Profile.objects.filter(user_id__in=user_ids,organization=p.organization).select_related('user'))
            if len(candidates)!=len(user_ids) or any(candidate.role!=expected_role or candidate.approval!='APPROVED' for candidate in candidates): return error('Every proposed responder must be an approved member of this NGO.',403)
            if any((candidate.details if isinstance(candidate.details,dict) else {}).get('availability','AVAILABLE')!='AVAILABLE' for candidate in candidates): return error('Proposed responders must currently be available.',409)
            if Assignment.objects.filter(user_id__in=user_ids,status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).exists(): return error('A proposed responder already has an active assignment.',409)
            if kind=='VOL' and emergency.required_skills:
                skills=set()
                for candidate in candidates:
                    value=(candidate.details if isinstance(candidate.details,dict) else {}).get('skills',[])
                    values=value.replace(';',',').split(',') if isinstance(value,str) else value if isinstance(value,list) else []
                    skills.update(str(skill).strip().casefold() for skill in values if str(skill).strip())
                missing={skill.strip().casefold() for skill in emergency.required_skills.split(',') if skill.strip()}-skills
                if missing: return error('The proposed volunteer team does not cover required skills: '+', '.join(sorted(missing)),409)
            if kind=='DRIVER':
                suitable=Vehicle.objects.filter(organization=p.organization,capacity__gte=emergency.required_vehicle_capacity).exclude(dispatches__status__in=['ASSIGNED','ACCEPTED','IN_TRANSIT','EXCEPTION']).distinct()
                if suitable.filter(pk__in=vehicle_ids).count()!=len(vehicle_ids): return error('Proposed vehicles must be available, owned by this NGO, and meet the request capacity.',409)
            if kind=='DRIVER' and emergency.needs_transport and not emergency.assignments.filter(kind='VOL').exclude(status='CANCELLED').exists(): return error('Propose at least one volunteer before proposing transport drivers.',409)
        authorization=AllocationAuthorization.objects.create(emergency=emergency,organization=p.organization,requested_by=request.user,kind=kind,user_ids=user_ids if kind!='STOCK' else [],vehicle_ids=vehicle_ids if kind!='STOCK' else [],inventory=inventory,requested_quantity=requested_quantity,task_instructions=task_instructions,pickup_location=str(d.get('pickup_location','')).strip(),cargo_details=str(d.get('cargo_details','')).strip())
        AllocationAuthorizationEvent.objects.create(authorization=authorization,actor=request.user,event_type='SUBMITTED',detail={'kind':kind,'user_ids':user_ids if kind!='STOCK' else [],'vehicle_ids':vehicle_ids if kind!='STOCK' else [],'inventory_id':inventory.pk if inventory else None,'quantity':requested_quantity})
        EventLog.objects.create(actor=request.user,action='Allocation authorization requested',target=emergency.reference,detail={'authorization_id':authorization.pk,'organization':p.organization.name,'kind':kind,'quantity':requested_quantity})
        for official in Profile.objects.filter(role='GOV',approval='APPROVED').select_related('user'):
            notify(official.user,'Allocation proposal needs review',f'{p.organization.name} proposed {kind.lower()} resources for {emergency.reference}.','/gov.html')
        return JsonResponse({'ok':True,'authorization':allocation_authorization_json(authorization)},status=201)
    qs=AllocationAuthorization.objects.select_related('emergency','organization','requested_by','reviewed_by','inventory').prefetch_related('history__actor')
    if p.role=='NGO': qs=qs.filter(organization=p.organization)
    return JsonResponse({'results':[allocation_authorization_json(row) for row in qs.order_by('-created_at')[:200]]})

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy reviewing another allocation. Refresh and try again.')
@transaction.atomic
def review_allocation_authorization(request,pk):
    p=profile(request)
    if not p or p.role!='GOV' or p.approval!='APPROVED': return error('Approved Government Official access required.',403)
    row=AllocationAuthorization.objects.select_related('emergency','organization','requested_by').filter(pk=pk).first()
    if not row: return error('Allocation proposal not found.',404)
    if row.status!='PENDING': return error('This proposal has already been reviewed.',409)
    if not Emergency.objects.filter(pk=row.emergency_id,accepted_by=row.organization,status__in=['ACCEPTED','IN_PROGRESS']).exists(): return error('The linked emergency is no longer active under this NGO.',409)
    d=payload(request); decision=d.get('decision'); note=str(d.get('note','')).strip()
    if decision not in ('APPROVED','REJECTED'): return error('Decision must be APPROVED or REJECTED.')
    if decision=='REJECTED' and not note: return error('Provide a reason when rejecting an allocation proposal.')
    row.status=decision; row.reviewed_by=request.user; row.reviewed_at=timezone.now(); row.decision_note=note; row.save(update_fields=['status','reviewed_by','reviewed_at','decision_note'])
    AllocationAuthorizationEvent.objects.create(authorization=row,actor=request.user,event_type=decision,detail={'note':note})
    EventLog.objects.create(actor=request.user,action='Allocation proposal '+decision.lower(),target=row.emergency.reference,detail={'authorization_id':row.pk,'organization':row.organization.name,'note':note})
    notify(row.requested_by,'Allocation proposal reviewed',f'{row.emergency.reference}: proposal {decision.lower()}.'+(f' {note}' if note else ''),ROLE_PAGE.get(row.requested_by.profile.role,'/'))
    return JsonResponse({'ok':True,'status':row.status})

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy executing another allocation. Refresh and try again.')
@transaction.atomic
def execute_allocation_authorization(request,pk):
    p=profile(request)
    if not p or p.role!='NGO' or p.approval!='APPROVED' or not p.organization: return error('Approved NGO Coordinator access required.',403)
    row=AllocationAuthorization.objects.select_related('emergency','organization').filter(pk=pk,organization=p.organization).first()
    if not row: return error('Allocation proposal not found.',404)
    if row.status!='APPROVED': return error('Only an approved proposal can be executed.',409)
    emergency=Emergency.objects.filter(pk=row.emergency_id,accepted_by=row.organization).first()
    if not emergency: return error('The emergency is no longer owned by this NGO.',409)
    if emergency.status not in ('ACCEPTED','IN_PROGRESS'): return error('The emergency is no longer active.',409)
    if row.kind=='STOCK':
        stock=Inventory.objects.filter(pk=row.inventory_id,organization=row.organization).first()
        if not stock: return error('The approved stock item is no longer available in this NGO.',409)
        if not row.requested_quantity or stock.quantity<row.requested_quantity: return error('Available stock is now lower than the approved quantity.',409)
        stock.quantity-=row.requested_quantity; stock.save(update_fields=['quantity','updated_at'])
        movement=InventoryMovement.objects.create(inventory=stock,emergency=emergency,actor=request.user,kind='ISSUE',quantity=row.requested_quantity,note=row.task_instructions[:240])
        EventLog.objects.create(actor=request.user,action='Approved emergency stock allocation executed',target=emergency.reference,detail={'authorization_id':row.pk,'inventory_id':stock.pk,'quantity':row.requested_quantity,'movement_id':movement.pk})
        row.status='EXECUTED'; row.executed_at=timezone.now(); row.save(update_fields=['status','executed_at'])
        AllocationAuthorizationEvent.objects.create(authorization=row,actor=request.user,event_type='EXECUTED',detail={'movement_id':movement.pk,'inventory_id':stock.pk,'quantity':row.requested_quantity})
        return JsonResponse({'ok':True,'status':row.status,'movement_id':movement.pk,'quantity_remaining':stock.quantity})
    result=perform_assignment(emergency,row.organization,request.user,{'kind':row.kind,'user_ids':row.user_ids,'vehicle_ids':row.vehicle_ids,'task_instructions':row.task_instructions,'pickup_location':row.pickup_location,'cargo_details':row.cargo_details})
    if result.status_code!=200: return result
    row.status='EXECUTED'; row.executed_at=timezone.now(); row.save(update_fields=['status','executed_at'])
    assignment_ids=json.loads(result.content).get('assignment_ids',[])
    AllocationAuthorizationEvent.objects.create(authorization=row,actor=request.user,event_type='EXECUTED',detail={'assignment_ids':assignment_ids})
    EventLog.objects.create(actor=request.user,action='Approved allocation executed',target=row.emergency.reference,detail={'authorization_id':row.pk,'assignment_ids':assignment_ids})
    return JsonResponse({'ok':True,'status':row.status,'assignment_ids':assignment_ids})

@login_required
def team(request):
    p=profile(request)
    if not p or p.role not in ('GOV','NGO') or not p.organization: return error('Organization official access required.',403)
    kind=request.GET.get('kind','VOL'); wanted=('GOV_' if p.role=='GOV' else 'NGO_')+('VOL' if kind=='VOL' else 'DRIVER')
    rows=Profile.objects.filter(organization=p.organization,role=wanted,approval='APPROVED').select_related('user')
    results=[]
    for x in rows:
        assignments=list(x.user.assignments.filter(organization=p.organization).select_related('emergency').order_by('-created_at')[:30])
        active_assignments=[a for a in assignments if a.status in ('ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED')]
        active=bool(active_assignments)
        availability='ASSIGNED' if active else x.details.get('availability','AVAILABLE')
        def assignment_json(a):
            return {'id':a.pk,'emergency':a.emergency.reference,'zone':a.emergency.location,'kind':a.kind,'status':a.status,'instructions':a.task_instructions,'completion_report':a.completion_report,'created_at':a.created_at.isoformat(),'updated_at':a.updated_at.isoformat()}
        results.append({'id':x.user_id,'name':x.user.get_full_name() or x.user.username,'role':x.get_role_display(),'role_code':x.role,'organization':x.organization.name if x.organization else None,'approval':x.approval,'availability':availability,'service':x.details.get('service',x.details.get('department','')),'skills':x.details.get('skills',''),'active':active,'assigned_zones':list(dict.fromkeys(a.emergency.location for a in active_assignments)),'current_assignments':[assignment_json(a) for a in active_assignments],'assignment_history':[assignment_json(a) for a in assignments]})
    return JsonResponse({'results':results})
@login_required
@require_http_methods(['GET'])
def team_approvals(request):
    p=profile(request)
    if not p or p.role not in ('GOV','NGO') or p.approval!='APPROVED' or not p.organization: return error('Approved organization coordinator access required.',403)
    roles=['GOV_VOL','GOV_DRIVER'] if p.role=='GOV' else ['NGO_VOL','NGO_DRIVER']
    rows=Profile.objects.filter(organization=p.organization,role__in=roles,approval='PENDING').select_related('user')
    return JsonResponse({'results':[{'id':x.id,'name':x.user.get_full_name(),'email':x.user.email,'role':x.get_role_display(),'created_at':x.user.date_joined.isoformat()} for x in rows]})
@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy updating this team approval. Refresh and try again.')
@transaction.atomic
def team_approval_decision(request,pk):
    p=profile(request); app=Profile.objects.select_related('user','organization').filter(pk=pk,approval='PENDING').first()
    if not app: return error('Pending team application not found.',404)
    if not p or p.role not in ('GOV','NGO') or p.approval!='APPROVED' or not p.organization or app.organization_id!=p.organization_id: return error('You cannot review this team member.',403)
    eligible=['GOV_VOL','GOV_DRIVER'] if p.role=='GOV' else ['NGO_VOL','NGO_DRIVER']
    if app.role not in eligible: return error('This account is not an eligible team application.',403)
    d=payload(request); decision=d.get('decision')
    if decision not in ('APPROVED','REJECTED'): return error('Decision must be APPROVED or REJECTED.')
    reason=str(d.get('reason','')).strip()
    if decision=='REJECTED' and not reason: return error('A rejection reason is required.')
    app.approval=decision; app.approval_decided_at=timezone.now(); app.approval_decided_by=request.user; app.rejection_reason=reason if decision=='REJECTED' else ''; app.save(update_fields=['approval','approval_decided_at','approval_decided_by','rejection_reason']); EventLog.objects.create(actor=request.user,action='Team registration '+decision.lower(),target=app.user.email,detail={'reason':reason}); notify(app.user,'Registration status updated',f'Your team registration was {decision.lower()}.'+(f' Reason: {reason}' if reason else ''),ROLE_PAGE.get(app.role,'/'))
    return JsonResponse({'ok':True,'approval':decision})
@login_required
@require_http_methods(['GET','POST'])
def vehicles(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Organization operations access required.',403)
    qs=Vehicle.objects.select_related('organization').all()
    if p.role in ('GOV','NGO'): qs=qs.filter(organization=p.organization)
    if request.method=='POST':
        d=payload(request)
        if p.role not in ('GOV','NGO') or p.approval!='APPROVED' or not p.organization: return error('Approved organization account required.',403)
        if not d.get('registration'): return error('Vehicle registration is required.')
        try: vehicle=Vehicle.objects.create(organization=p.organization,registration=d['registration'].strip().upper(),kind=d.get('kind','Relief van'),capacity=max(0,int(d.get('capacity',0))))
        except (ValueError,TypeError): return error('Vehicle capacity must be a whole number.')
        except IntegrityError: return error('That vehicle registration already exists.')
        return JsonResponse({'ok':True,'id':vehicle.id},status=201)
    return JsonResponse({'results':[{'id':v.id,'organization':v.organization.name,'registration':v.registration,'kind':v.kind,'capacity':v.capacity,'available':not v.dispatches.filter(status__in=['ASSIGNED','ACCEPTED','IN_TRANSIT','EXCEPTION']).exists()} for v in qs.order_by('organization__name','registration')]})
@login_required
def dispatches(request):
    p=profile(request)
    if not p: return error('Account profile missing.',403)
    qs=Dispatch.objects.select_related('emergency','driver','organization','vehicle').all()
    if p.role=='GOV': qs=qs.filter(organization=p.organization)
    elif p.role=='NGO': qs=qs.filter(organization=p.organization)
    elif p.role in ('GOV_DRIVER','NGO_DRIVER'): qs=qs.filter(driver=request.user)
    elif p.role not in ('ADMIN',): return error('Driver or organization operations access required.',403)
    return JsonResponse({'results':[{'id':d.id,'emergency':d.emergency.reference,'pickup_location':d.pickup_location,'location':d.destination,'cargo_details':d.cargo_details,'trip_instructions':d.trip_instructions,'delivery_proof':d.delivery_proof,'driver':d.driver.get_full_name(),'vehicle':d.vehicle.registration if d.vehicle else None,'vehicle_capacity':d.vehicle.capacity if d.vehicle else None,'status':d.status,'created_at':d.created_at.isoformat(),'updated_at':d.updated_at.isoformat(),'delivered_at':d.delivered_at.isoformat() if d.delivered_at else None,'delivery':delivery_json(d.delivery_record) if hasattr(d,'delivery_record') else None,'history':[{'status':h.status,'note':h.note,'actor':h.actor.get_full_name() if h.actor else 'System','created_at':h.created_at.isoformat()} for h in d.history.select_related('actor').order_by('created_at')]} for d in qs.order_by('-created_at')[:200]]})

def delivery_json(row):
    return {'id':row.pk,'dispatch_id':row.dispatch_id,'emergency_id':row.emergency_id,'emergency':row.emergency.reference,'driver':row.driver.get_full_name() or row.driver.email,'vehicle':row.vehicle.registration if row.vehicle else None,'organization':row.organization.name,'recipient_name':row.recipient_name,'address':row.address,'items':row.items,'delivered_at':row.delivered_at.isoformat(),'photo_url':f'/api/deliveries/{row.pk}/photo/' if row.photo else None,'remarks':row.remarks,'demo':row.demo,'status':row.status,'citizen_responded_at':row.citizen_responded_at.isoformat() if row.citizen_responded_at else None,'issue_details':row.issue_details,'created_at':row.created_at.isoformat(),'updated_at':row.updated_at.isoformat()}

def valid_delivery_photo(upload):
    if not upload or upload.size>8*1024*1024: return False
    extension=upload.name.rsplit('.',1)[-1].lower() if '.' in upload.name else ''
    signature=upload.read(12); upload.seek(0)
    return (extension in ('jpg','jpeg') and signature.startswith(b'\xff\xd8\xff')) or (extension=='png' and signature.startswith(b'\x89PNG\r\n\x1a\n')) or (extension=='webp' and signature[:4]==b'RIFF' and signature[8:12]==b'WEBP')

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy saving this delivery. Refresh and try again.')
@transaction.atomic
def submit_delivery(request,pk):
    p=profile(request)
    dispatch=Dispatch.objects.select_related('emergency','driver','organization','vehicle').filter(pk=pk).first()
    if not dispatch: return error('Dispatch not found.',404)
    if not p or p.role not in ('GOV_DRIVER','NGO_DRIVER') or p.approval!='APPROVED' or request.user.id!=dispatch.driver_id or p.organization_id!=dispatch.organization_id:
        return error('Only the approved assigned driver can submit this delivery.',403)
    if dispatch.status!='IN_TRANSIT': return error('Start the assigned trip before submitting delivery details.',409)
    if hasattr(dispatch,'delivery_record'): return error('Delivery details have already been submitted for this dispatch.',409)
    recipient=str(request.POST.get('recipient_name','')).strip(); address=str(request.POST.get('address','')).strip(); remarks=str(request.POST.get('remarks','')).strip()
    if not recipient or len(recipient)>160 or not address or len(address)>240: return error('Recipient name and delivery address are required.')
    try: items=json.loads(request.POST.get('items','[]'))
    except (TypeError,ValueError): return error('Delivery items must be valid JSON.')
    if not isinstance(items,list) or not items or len(items)>50: return error('Add between one and 50 delivered items.')
    normalized=[]
    for item in items:
        if not isinstance(item,dict): return error('Each delivered item must include a name and quantity.')
        name=str(item.get('name','')).strip()
        try: quantity=int(item.get('quantity'))
        except (TypeError,ValueError): return error('Item quantities must be positive whole numbers.')
        if not name or len(name)>120 or quantity<1: return error('Each item needs a name and positive whole-number quantity.')
        normalized.append({'name':name,'quantity':quantity})
    delivered_at=parse_datetime(request.POST.get('delivered_at',''))
    if not delivered_at: return error('Enter the delivery date and time.')
    if timezone.is_naive(delivered_at): delivered_at=timezone.make_aware(delivered_at,timezone.get_current_timezone())
    photo=request.FILES.get('photo')
    if not valid_delivery_photo(photo): return error('Upload a JPEG, PNG, or WebP photo up to 8 MB.')
    row=DeliveryRecord.objects.create(dispatch=dispatch,emergency=dispatch.emergency,driver=request.user,vehicle=dispatch.vehicle,organization=dispatch.organization,recipient_name=recipient,address=address,items=normalized,delivered_at=delivered_at,photo=photo,remarks=remarks,demo=dispatch.emergency.demo)
    old_status=dispatch.status; dispatch.status='DELIVERED'; dispatch.delivered_at=delivered_at; dispatch.delivery_proof=f'Delivery record {row.pk} submitted; waiting for Citizen confirmation.'; dispatch.save(update_fields=['status','delivered_at','delivery_proof','updated_at'])
    DispatchEvent.objects.create(dispatch=dispatch,actor=request.user,status='DELIVERED',note=f'Delivery details submitted; awaiting Citizen confirmation. Record {row.pk}.')
    assignment=Assignment.objects.filter(emergency=dispatch.emergency,user=request.user,kind='DRIVER').first()
    if assignment and assignment.status in ('ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED'):
        assignment.status='COMPLETED'; assignment.completion_report=f'Delivery details submitted; awaiting Citizen confirmation. Record {row.pk}.'; assignment.save(update_fields=['status','completion_report','updated_at']); AssignmentEvent.objects.create(assignment=assignment,actor=request.user,status='COMPLETED',note=assignment.completion_report)
    EventLog.objects.create(actor=request.user,action='Delivery details submitted',target=dispatch.emergency.reference,detail={'dispatch_id':dispatch.pk,'delivery_id':row.pk,'from_dispatch_status':old_status,'to_dispatch_status':'DELIVERED'})
    notify(dispatch.emergency.reporter,'Delivery ready for confirmation',f'{dispatch.emergency.reference}: delivery details were submitted. Please confirm receipt or report an issue.','/citizen.html')
    for coordinator in Profile.objects.filter(organization=dispatch.organization,role__in=['GOV','NGO'],approval='APPROVED').select_related('user'):
        notify(coordinator.user,'Delivery details submitted',f'{dispatch.emergency.reference}: the driver submitted delivery details; Citizen confirmation is pending.',ROLE_PAGE.get(coordinator.role,'/'))
    return JsonResponse({'ok':True,'delivery':delivery_json(row),'message':'Delivery details saved. Waiting for Citizen confirmation.'},status=201)

@login_required
@require_http_methods(['GET'])
def deliveries(request):
    p=profile(request)
    qs=DeliveryRecord.objects.select_related('dispatch','emergency','driver','vehicle','organization').all()
    if not p: return error('Account profile missing.',403)
    if p.role=='CITIZEN': qs=qs.filter(emergency__reporter=request.user)
    elif p.role in ('GOV','NGO'): qs=qs.filter(organization=p.organization)
    elif p.role in ('GOV_DRIVER','NGO_DRIVER'): qs=qs.filter(driver=request.user)
    elif p.role!='ADMIN': return error('Delivery record access is restricted.',403)
    return JsonResponse({'results':[delivery_json(row) for row in qs.order_by('-delivered_at')[:200]]})

@login_required
@require_http_methods(['GET'])
def delivery_photo(request,pk):
    p=profile(request); row=DeliveryRecord.objects.select_related('emergency','dispatch','organization').filter(pk=pk).first()
    if not row: return error('Delivery proof not found.',404)
    allowed=bool(p and ((p.role=='CITIZEN' and row.emergency.reporter_id==request.user.id) or (p.role in ('GOV_DRIVER','NGO_DRIVER') and row.driver_id==request.user.id) or (p.role in ('GOV','NGO') and p.organization_id==row.organization_id) or p.role=='ADMIN'))
    if not allowed: return error('You cannot view this delivery proof.',403)
    if not row.photo or not row.photo.storage.exists(row.photo.name): return error('Delivery photo is unavailable.',404)
    extension=row.photo.name.rsplit('.',1)[-1].lower(); content_type={'jpg':'image/jpeg','jpeg':'image/jpeg','png':'image/png','webp':'image/webp'}.get(extension,'application/octet-stream')
    response=FileResponse(row.photo.open('rb'),content_type=content_type); response['X-Content-Type-Options']='nosniff'; response['Cache-Control']='private, no-store'; return response

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy recording the Citizen response. Refresh and try again.')
@transaction.atomic
def delivery_response(request,pk):
    p=profile(request); row=DeliveryRecord.objects.select_related('dispatch','emergency','driver','organization').filter(pk=pk,emergency__reporter=request.user).first()
    if not p or p.role!='CITIZEN' or not row: return error('Delivery record not found for your emergency request.',404)
    if row.status!='WAITING_CONFIRMATION': return error('A response has already been recorded for this delivery.',409)
    d=payload(request); action=d.get('action'); issue=str(d.get('issue_details','')).strip()
    if action not in ('CONFIRMED','ISSUE_REPORTED'): return error('Choose Confirm Received or Report Issue.')
    if action=='ISSUE_REPORTED' and not issue: return error('Describe the delivery issue before submitting.')
    if len(issue)>2000: return error('Issue details must be 2,000 characters or fewer.')
    row.status=action; row.issue_details=issue if action=='ISSUE_REPORTED' else ''; row.citizen_responded_at=timezone.now(); row.save(update_fields=['status','issue_details','citizen_responded_at','updated_at'])
    note='Citizen confirmed receipt.' if action=='CONFIRMED' else f'Citizen reported a delivery issue: {issue}'
    DispatchEvent.objects.create(dispatch=row.dispatch,actor=request.user,status='DELIVERED',note=note)
    EventLog.objects.create(actor=request.user,action='Delivery '+action.lower(),target=row.emergency.reference,detail={'delivery_id':row.pk,'issue_details':row.issue_details})
    notify(row.driver,'Citizen delivery response',f'{row.emergency.reference}: {"receipt confirmed" if action=="CONFIRMED" else "an issue was reported"}.',ROLE_PAGE.get(row.driver.profile.role,'/'))
    for coordinator in Profile.objects.filter(organization=row.organization,role__in=['GOV','NGO'],approval='APPROVED').select_related('user'):
        notify(coordinator.user,'Citizen delivery response',f'{row.emergency.reference}: {"receipt confirmed" if action=="CONFIRMED" else "a delivery issue was reported"}.'+(f' {issue}' if issue else ''),ROLE_PAGE.get(coordinator.role,'/'))
    if action=='CONFIRMED' and not row.emergency.assignments.exclude(status__in=['COMPLETED','CANCELLED']).exists() and row.emergency.status not in ('RESOLVED','CANCELLED'):
        previous=row.emergency.status; row.emergency.status='RESOLVED'; row.emergency.save(update_fields=['status']); record_emergency_event(row.emergency,request.user,'RESOLVED',previous,'RESOLVED','Citizen confirmed delivery receipt')
    return JsonResponse({'ok':True,'delivery':delivery_json(row),'message':'Receipt confirmed.' if action=='CONFIRMED' else 'Delivery issue recorded and sent to the response organization.'})

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy updating this assignment. Refresh and try again.')
@transaction.atomic
def update_assignment(request,pk):
    p=profile(request)
    emergency_id=Assignment.objects.filter(pk=pk).values_list('emergency_id',flat=True).first()
    if emergency_id is None: return error('Assignment not found.',404)
    Emergency.objects.get(pk=emergency_id)
    a=Assignment.objects.select_related('user','emergency','emergency__accepted_by','organization').filter(pk=pk).first()
    if not a: return error('Assignment not found.',404)
    coordinator_access=bool(p and p.role in ('GOV','NGO') and p.approval=='APPROVED' and p.organization_id==a.organization_id)
    responder_roles=('GOV_VOL','NGO_VOL') if a.kind=='VOL' else ('GOV_DRIVER','NGO_DRIVER')
    assignee_access=bool(request.user.id==a.user_id and p and p.approval=='APPROVED' and p.role in responder_roles and p.organization_id==a.organization_id)
    if not (coordinator_access or assignee_access): return error('Approved organization coordinators or the approved assigned responder can update this assignment.',403)
    d=payload(request); status=d.get('status'); report=(d.get('completion_report') or '').strip(); blocked=(d.get('blocked_note') or '').strip(); cancellation=(d.get('cancellation_reason') or '').strip()
    if status=='COMPLETED' and a.kind=='DRIVER': return error('Submit the delivery details form with recipient, items, date/time, and photo proof.',409)
    if status not in ('ACKNOWLEDGED','IN_PROGRESS','BLOCKED','COMPLETED','CANCELLED'): return error('Choose a valid assignment status.')
    allowed={'ASSIGNED':{'ACKNOWLEDGED','IN_PROGRESS','BLOCKED','COMPLETED','CANCELLED'},'ACKNOWLEDGED':{'IN_PROGRESS','BLOCKED','COMPLETED','CANCELLED'},'IN_PROGRESS':{'BLOCKED','COMPLETED','CANCELLED'},'BLOCKED':{'IN_PROGRESS','COMPLETED','CANCELLED'}}
    if status not in allowed.get(a.status,set()): return error(f'Cannot change an assignment from {a.status} to {status}.',409)
    if status=='COMPLETED' and not report: return error('A completion report is required before closing this task.')
    if status=='CANCELLED' and not cancellation: return error('A reason is required before cancelling this assignment.')
    a.status=status
    if report: a.completion_report=report
    if blocked: a.blocked_note=blocked
    if status=='ACKNOWLEDGED' and not a.acknowledged_at: a.acknowledged_at=timezone.now()
    a.save(update_fields=['status','completion_report','blocked_note','acknowledged_at','updated_at'])
    event_note=report or blocked or cancellation
    AssignmentEvent.objects.create(assignment=a,actor=request.user,status=status,note=event_note)
    EventLog.objects.create(actor=request.user,action='Assignment '+status.lower(),target=a.emergency.reference,detail={'assignee':a.user.email,'completion_report':a.completion_report,'blocked_note':a.blocked_note,'cancellation_reason':cancellation})
    if status=='CANCELLED':
        current_status=a.emergency.status
        record_emergency_event(a.emergency,request.user,'ASSIGNMENT_CANCELLED',current_status,current_status,cancellation)
        notify(a.emergency.reporter,'Responder assignment cancelled',f'{a.user.get_full_name() or a.user.username} cancelled their assignment for {a.emergency.reference}: {cancellation}', '/citizen.html')
        if a.emergency.accepted_by_id:
            for coordinator in Profile.objects.filter(organization_id=a.emergency.accepted_by_id,role__in=['GOV','NGO'],approval='APPROVED').select_related('user'):
                notify(coordinator.user,'Responder assignment cancelled',f'{a.user.get_full_name() or a.user.username} cancelled their assignment for {a.emergency.reference}: {cancellation}',ROLE_PAGE.get(coordinator.role,'/'))
    if status=='BLOCKED':
        org=a.emergency.accepted_by
        if org:
            for coordinator in Profile.objects.filter(organization=org,role__in=['GOV','NGO'],approval='APPROVED').select_related('user'):
                notify(coordinator.user,'Responder needs assistance',f'{a.user.get_full_name() or a.user.username} is blocked on {a.emergency.reference}: {a.blocked_note or "assistance requested"}',ROLE_PAGE.get(coordinator.role,'/'))
    if status=='IN_PROGRESS' and a.emergency.status=='ACCEPTED':
        old_status=a.emergency.status; a.emergency.status='IN_PROGRESS'; a.emergency.save(update_fields=['status'])
        record_emergency_event(a.emergency,request.user,'IN_PROGRESS',old_status,a.emergency.status,'Response team began work')
        notify(a.emergency.reporter,'Response work started',f'Response work has started for {a.emergency.reference}.','/citizen.html')
    if a.kind=='DRIVER':
        dispatch=Dispatch.objects.filter(emergency=a.emergency,driver=a.user).first()
        if dispatch:
            old_status=dispatch.status
            if status in ('ACKNOWLEDGED','IN_PROGRESS','BLOCKED','COMPLETED','CANCELLED'):
                dispatch.status={'ACKNOWLEDGED':'ACCEPTED','IN_PROGRESS':'IN_TRANSIT','BLOCKED':'EXCEPTION','COMPLETED':'DELIVERED','CANCELLED':'CANCELLED'}[status]
            if status=='COMPLETED': dispatch.delivered_at=timezone.now(); dispatch.delivery_proof=report or dispatch.delivery_proof
            dispatch.save(update_fields=['status','delivered_at','delivery_proof','updated_at'])
            if dispatch.status!=old_status:
                DispatchEvent.objects.create(dispatch=dispatch,actor=request.user,status=dispatch.status,note=event_note)
                EventLog.objects.create(actor=request.user,action='Dispatch status updated',target=a.emergency.reference,detail={'dispatch_id':dispatch.pk,'driver':a.user.email,'from_status':old_status,'to_status':dispatch.status,'delivery_proof':dispatch.delivery_proof})
                notify(a.emergency.reporter,'Relief dispatch updated',f'{a.emergency.reference} dispatch is now {dispatch.status.lower().replace("_"," ")}.','/citizen.html')
                if a.emergency.accepted_by_id:
                    for coordinator in Profile.objects.filter(organization_id=a.emergency.accepted_by_id,role__in=['GOV','NGO'],approval='APPROVED').select_related('user'):
                        notify(coordinator.user,'Driver trip update',f'{a.user.get_full_name() or a.user.username}: {a.emergency.reference} is now {dispatch.status.lower().replace("_"," ")}.',ROLE_PAGE.get(coordinator.role,'/'))
    pending_delivery=DeliveryRecord.objects.filter(emergency=a.emergency).exclude(status='CONFIRMED').exists()
    if status=='COMPLETED' and not pending_delivery and not a.emergency.assignments.exclude(status__in=['COMPLETED','CANCELLED']).exists():
        transport_satisfied=(not a.emergency.needs_transport) or (a.emergency.assignments.filter(kind='VOL',status='COMPLETED').exists() and a.emergency.assignments.filter(kind='DRIVER',status='COMPLETED').exists())
        if transport_satisfied:
            old_status=a.emergency.status; a.emergency.status='RESOLVED'; a.emergency.save(update_fields=['status'])
            record_emergency_event(a.emergency,request.user,'RESOLVED',old_status,a.emergency.status,'All required assigned work is complete')
            notify(a.emergency.reporter,'Emergency response completed',f'{a.emergency.reference} has been marked resolved.','/citizen.html')
    return JsonResponse({'ok':True,'status':a.status})
@require_http_methods(['GET','POST'])
def shelters(request):
    if request.method=='GET':
        thresholds=shelter_capacity_thresholds()
        rows=[shelter_json(s,thresholds) for s in Shelter.objects.all().select_related('organization').order_by('name')]
        return JsonResponse({'results':rows,'capacity_thresholds':thresholds})
    p=profile(request)
    if not p or p.role not in ('GOV','NGO') or p.approval!='APPROVED' or not p.organization: return error('Approved organization account required.',403)
    d=payload(request)
    try:
        capacity=int(d['capacity']); occupancy=int(d.get('occupancy',0)); latitude=float(d['latitude']); longitude=float(d['longitude'])
        if capacity<1 or occupancy<0 or occupancy>capacity: return error('Shelter occupancy must be between zero and capacity.')
        if not is_punjab_coordinate(latitude,longitude): return error('Shelter coordinates must fall within Punjab.')
        location=format_punjab_address(d.get('address') or d.get('location'),d.get('district'))
        shelter_status=d.get('status','Open')
        if shelter_status not in ('Open','Full','Temporarily Closed'): return error('Choose a valid shelter status.')
        phone=str(d.get('contact_phone','')).strip()
        if not __import__('re').fullmatch(r'\+?[0-9][0-9\s().-]{6,24}',phone): return error('Enter a valid shelter contact phone number.')
        district=str(d['district']).strip(); address=str(d.get('address') or d.get('location') or '').strip()
        s=Shelter.objects.create(name=str(d['name']).strip(),organization=p.organization,location=location,address=address,district=district,contact_phone=phone,shelter_type=str(d.get('type',d.get('shelter_type','Shelter'))).strip()[:40] or 'Shelter',description=str(d.get('description','')).strip(),latitude=latitude,longitude=longitude,capacity=capacity,occupancy=occupancy,status=shelter_status)
        ShelterEvent.objects.create(shelter=s,actor=request.user,event_type='CREATED',changes={'status':s.status,'capacity':capacity,'occupancy':occupancy,'location':s.location})
        EventLog.objects.create(actor=request.user,action='Shelter registered',target=s.name,detail={'organization':p.organization.name,'latitude':latitude,'longitude':longitude})
    except (KeyError,ValueError,TypeError): return error('Provide shelter name, location, coordinates and capacity.')
    return JsonResponse({'ok':True,'shelter':shelter_json(s)},status=201)
def shelter_capacity_thresholds():
    defaults={'high_occupancy_pct':50,'nearly_full_pct':85}
    row=SystemPreference.objects.filter(key='shelter_capacity_thresholds').first()
    values=row.value if row and isinstance(row.value,dict) else {}
    try:
        high=int(values.get('high_occupancy_pct',defaults['high_occupancy_pct'])); near=int(values.get('nearly_full_pct',defaults['nearly_full_pct']))
        if not 1<=high<near<100: return defaults
        return {'high_occupancy_pct':high,'nearly_full_pct':near}
    except (TypeError,ValueError): return defaults

def shelter_json(s,thresholds=None):
    thresholds=thresholds or shelter_capacity_thresholds()
    percent=round(s.occupancy*100/s.capacity) if s.capacity else 0
    if s.status=='Temporarily Closed': band='Closed / inactive'
    elif s.status=='Full' or s.available==0: band='Full'
    elif s.occupancy*100>=s.capacity*thresholds['nearly_full_pct']: band='Nearly full'
    elif s.occupancy*100>=s.capacity*thresholds['high_occupancy_pct']: band='High occupancy'
    else: band='Available'
    return {'id':s.id,'name':s.name,'organization':s.organization.name if s.organization else None,'contact_phone':s.contact_phone,'address':s.address,'district':s.district,'latitude':s.latitude,'longitude':s.longitude,'location':s.location,'type':s.shelter_type,'description':s.description,'capacity':s.capacity,'occupancy':s.occupancy,'occupancy_pct':percent,'occupancy_band':band,'available':s.available,'status':s.status,'updated_at':s.updated_at.isoformat(),'demo':s.demo}
@login_required
@require_http_methods(['PATCH'])
def update_shelter(request,pk):
    p=profile(request); s=Shelter.objects.select_related('organization').filter(pk=pk).first()
    if not s: return error('Shelter not found.',404)
    if not p or p.role not in ('ADMIN','GOV','NGO') or (p.role!='ADMIN' and s.organization_id!=p.organization_id): return error('You cannot update this shelter.',403)
    original={field:getattr(s,field) for field in ('name','location','address','district','contact_phone','shelter_type','description','latitude','longitude','capacity','occupancy','status')}
    d=payload(request)
    if 'district' in d or 'address' in d:
        try: d['location']=format_punjab_address(d.get('address') or d.get('location'),d.get('district'))
        except ValueError as exc: return error(str(exc))
        s.address=str(d.get('address') or d.get('location') or '').strip(); s.district=str(d.get('district') or s.district).strip()
    if 'contact_phone' in d:
        s.contact_phone=str(d['contact_phone']).strip()
        if not __import__('re').fullmatch(r'\+?[0-9][0-9\s().-]{6,24}',s.contact_phone): return error('Enter a valid shelter contact phone number.')
    try: capacity=int(d.get('capacity',s.capacity)); occupancy=int(d.get('occupancy',s.occupancy)); latitude=float(d.get('latitude',s.latitude)); longitude=float(d.get('longitude',s.longitude))
    except (ValueError,TypeError): return error('Capacity, occupancy, latitude and longitude must be numeric.')
    if capacity<1 or occupancy<0 or occupancy>capacity: return error('Shelter occupancy must be between zero and capacity.')
    if not is_punjab_coordinate(latitude,longitude): return error('Shelter coordinates must fall within Punjab.')
    s.capacity=capacity; s.occupancy=occupancy; s.latitude=latitude; s.longitude=longitude
    for key,field,max_length in [('name','name',140),('location','location',180),('type','shelter_type',40)]:
        value=d.get(key)
        if value is not None:
            value=str(value).strip()
            if not value: return error(f'{key.title()} is required.')
            setattr(s,field,value[:max_length])
    if 'description' in d: s.description=str(d['description']).strip()
    if 'status' in d:
        if d['status'] not in ('Open','Full','Temporarily Closed'): return error('Choose a valid shelter status.')
        s.status=d['status']
    changed={}
    for field in ('name','location','address','district','contact_phone','shelter_type','description','latitude','longitude','capacity','occupancy','status'):
        if original[field] != getattr(s,field): changed[field]={'from':original[field],'to':getattr(s,field)}
    s.save()
    if changed: ShelterEvent.objects.create(shelter=s,actor=request.user,event_type='UPDATED',changes=changed)
    EventLog.objects.create(actor=request.user,action='Shelter updated',target=s.name,detail={'occupancy':occupancy,'capacity':capacity,'status':s.status,'latitude':latitude,'longitude':longitude})
    return JsonResponse({'ok':True,'shelter':shelter_json(s)})

@login_required
@require_http_methods(['GET'])
def shelter_history(request,pk):
    p=profile(request); shelter=Shelter.objects.filter(pk=pk).first()
    if not shelter: return error('Shelter not found.',404)
    if not p or p.role not in ('ADMIN','GOV','NGO') or (p.role!='ADMIN' and shelter.organization_id!=p.organization_id): return error('You cannot view this shelter history.',403)
    rows=shelter.history.select_related('actor').order_by('-created_at')[:100]
    return JsonResponse({'results':[{'event_type':row.event_type,'actor':row.actor.get_full_name() or row.actor.email if row.actor else 'System','changes':row.changes,'created_at':row.created_at.isoformat()} for row in rows]})
@require_http_methods(['GET','POST'])
def advisories(request):
    if request.method=='GET':
        p=profile(request) if request.user.is_authenticated else None
        managing=bool(p and p.role in ('ADMIN','GOV') and p.approval=='APPROVED' and request.GET.get('manage')=='1')
        rows=Advisory.objects.all() if managing else Advisory.objects.filter(published=True,archived=False,withdrawn=False).filter(Q(expires_at__isnull=True)|Q(expires_at__gt=timezone.now()))
        return JsonResponse({'results':[advisory_json(a,managing) for a in rows.order_by('-updated_at')[:100]]})
    p=profile(request)
    if not request.user.is_authenticated or not p or p.role not in ('ADMIN','GOV') or p.approval!='APPROVED': return error('Approved Administrator or Government Official access required.',403)
    d=payload(request)
    if not d.get('title') or not d.get('body'): return error('Advisory title and message are required.')
    severity=d.get('severity','MEDIUM')
    if severity not in dict(Advisory.SEVERITIES): return error('Choose a valid advisory severity.')
    action=d.get('action')
    if action is None: action='PUBLISH' if d.get('published',True) else 'SAVE'
    if action not in ('SAVE','DRAFT','PUBLISH'): return error('Choose whether to save a draft or publish the advisory.')
    published=action=='PUBLISH'
    expires_at=None
    if d.get('expires_at'):
        expires_at=parse_datetime(str(d['expires_at']))
        if not expires_at: return error('Advisory expiry must be a valid date and time.')
        if timezone.is_naive(expires_at): expires_at=timezone.make_aware(expires_at,timezone.get_current_timezone())
        if expires_at<=timezone.now(): return error('Advisory expiry must be in the future.')
    category=str(d.get('category','Public safety')).strip()[:80] or 'Public safety'
    a=Advisory.objects.create(title=str(d['title']).strip(),category=category,body=str(d['body']).strip(),location=str(d.get('location','')).strip(),severity=severity,published=published,published_by=request.user if published else None,expires_at=expires_at)
    event_type='PUBLISHED' if published else 'DRAFTED'
    AdvisoryEvent.objects.create(advisory=a,actor=request.user,event_type=event_type,detail={'severity':severity})
    EventLog.objects.create(actor=request.user,action='Advisory published' if published else 'Advisory drafted',target=a.title)
    if a.published:
        notify_advisory_citizens(a)
    return JsonResponse({'ok':True,'advisory':advisory_json(a,True)},status=201)

def advisory_json(advisory,include_history=False):
    row={'id':advisory.id,'title':advisory.title,'category':advisory.category,'body':advisory.body,'location':advisory.location,'severity':advisory.severity,'published':advisory.published,'published_by':advisory.published_by.get_full_name() if advisory.published_by else None,'expires_at':advisory.expires_at.isoformat() if advisory.expires_at else None,'archived':advisory.archived,'withdrawn':advisory.withdrawn,'state':'ARCHIVED' if advisory.archived else 'WITHDRAWN' if advisory.withdrawn else 'PUBLISHED' if advisory.published else 'DRAFT','demo':advisory.demo,'created_at':advisory.created_at.isoformat(),'updated_at':advisory.updated_at.isoformat()}
    if include_history: row['history']=[{'event_type':event.event_type,'actor':event.actor.get_full_name() or event.actor.email if event.actor else 'System','detail':event.detail,'created_at':event.created_at.isoformat()} for event in advisory.history.select_related('actor').order_by('created_at')]
    return row

def notify_advisory_citizens(advisory):
    for citizen in Profile.objects.filter(role='CITIZEN',approval='APPROVED').select_related('user'):
        notify(citizen.user,'New public advisory',f'{advisory.title}: {advisory.body[:240]}','/citizen.html')

@login_required
@require_http_methods(['PATCH'])
def advisory_detail(request,pk):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV') or p.approval!='APPROVED': return error('Approved Administrator or Government Official access required.',403)
    advisory=Advisory.objects.filter(pk=pk).first()
    if not advisory: return error('Advisory not found.',404)
    d=payload(request); action=d.get('action','SAVE')
    if action not in ('SAVE','PUBLISH','WITHDRAW','ARCHIVE'): return error('Choose a valid advisory action.')
    if action=='SAVE':
        if advisory.published or advisory.archived or advisory.withdrawn: return error('Only a draft can be edited.',409)
        title=str(d.get('title',advisory.title)).strip(); body=str(d.get('body',advisory.body)).strip(); location=str(d.get('location',advisory.location)).strip(); category=str(d.get('category',advisory.category)).strip()[:80] or 'Public safety'; severity=d.get('severity',advisory.severity)
        if not title or not body: return error('Advisory title and message are required.')
        if severity not in dict(Advisory.SEVERITIES): return error('Choose a valid advisory severity.')
        expires_at=None
        if d.get('expires_at'):
            expires_at=parse_datetime(str(d['expires_at']))
            if not expires_at: return error('Advisory expiry must be a valid date and time.')
            if timezone.is_naive(expires_at): expires_at=timezone.make_aware(expires_at,timezone.get_current_timezone())
            if expires_at<=timezone.now(): return error('Advisory expiry must be in the future.')
        advisory.title=title; advisory.category=category; advisory.body=body; advisory.location=location; advisory.severity=severity; advisory.expires_at=expires_at; advisory.save()
        AdvisoryEvent.objects.create(advisory=advisory,actor=request.user,event_type='UPDATED',detail={'severity':severity,'category':category,'expires_at':expires_at.isoformat() if expires_at else None})
    elif action=='PUBLISH':
        if advisory.archived or advisory.withdrawn: return error('Archived or withdrawn advisories cannot be published.',409)
        if not advisory.title.strip() or not advisory.body.strip(): return error('Advisory title and message are required.')
        if not advisory.published:
            if advisory.expires_at and advisory.expires_at<=timezone.now(): return error('Expired advisories cannot be published.',409)
            advisory.published=True; advisory.published_by=request.user; advisory.save(update_fields=['published','published_by','updated_at'])
            AdvisoryEvent.objects.create(advisory=advisory,actor=request.user,event_type='PUBLISHED',detail={'severity':advisory.severity})
            EventLog.objects.create(actor=request.user,action='Advisory published',target=advisory.title)
            notify_advisory_citizens(advisory)
    elif action=='WITHDRAW':
        if not advisory.published: return error('Only a published advisory can be withdrawn.',409)
        advisory.published=False; advisory.withdrawn=True; advisory.save(update_fields=['published','withdrawn','updated_at'])
        AdvisoryEvent.objects.create(advisory=advisory,actor=request.user,event_type='WITHDRAWN')
        EventLog.objects.create(actor=request.user,action='Advisory withdrawn',target=advisory.title)
    else:
        if advisory.archived: return error('Advisory is already archived.',409)
        advisory.published=False; advisory.archived=True; advisory.save(update_fields=['published','archived','updated_at'])
        AdvisoryEvent.objects.create(advisory=advisory,actor=request.user,event_type='ARCHIVED')
        EventLog.objects.create(actor=request.user,action='Advisory archived',target=advisory.title)
    return JsonResponse({'ok':True,'advisory':advisory_json(advisory,True)})
@login_required
@require_http_methods(['GET','POST'])
def agencies(request):
    p=profile(request)
    if request.method=='POST':
        if not p or p.role!='ADMIN' or p.approval!='APPROVED': return error('Approved Administrator access required.',403)
        d=payload(request); name=str(d.get('name','')).strip(); kind=d.get('kind'); zone=str(d.get('zone','')).strip()
        if 'district' in d:
            try: zone=format_punjab_address('Response operations',d.get('district'))
            except ValueError as exc: return error(str(exc))
        if not 2<=len(name)<=140: return error('Organization name must be between 2 and 140 characters.')
        if kind not in ('GOV','NGO'): return error('Choose Government or NGO as the organization type.')
        if Organization.objects.filter(name__iexact=name).exists(): return error('An organization with this name already exists.',409)
        try: org=Organization.objects.create(name=name,kind=kind,zone=zone[:120])
        except IntegrityError: return error('An organization with this name already exists.',409)
        EventLog.objects.create(actor=request.user,action='Organization created',target=org.name,detail={'kind':org.kind,'zone':org.zone})
        return JsonResponse({'ok':True,'organization':organization_json(org)},status=201)
    if not p or p.role not in ('ADMIN','GOV') or (p.role=='ADMIN' and p.approval!='APPROVED'): return error('Administrator or Government Official access required.',403)
    rows=[]
    for org in Organization.objects.all().order_by('kind','name'):
        accepted=Emergency.objects.filter(accepted_by=org)
        rows.append({**organization_json(org),'accepted_requests':accepted.count(),'active_assignments':Assignment.objects.filter(organization=org,status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).count(),'active_zones':list(accepted.values_list('location',flat=True).distinct()[:10])})
    return JsonResponse({'results':rows})

def organization_json(org):
    return {'id':org.pk,'name':org.name,'type':org.get_kind_display(),'kind_code':org.kind,'zone':org.zone,'members':org.members.count(),'pending_members':org.members.filter(approval='PENDING').count()}

@login_required
@require_http_methods(['PATCH'])
def update_agency(request,pk):
    p=profile(request)
    if not p or p.role!='ADMIN' or p.approval!='APPROVED': return error('Approved Administrator access required.',403)
    org=Organization.objects.filter(pk=pk).first()
    if not org: return error('Organization not found.',404)
    d=payload(request)
    if 'kind' in d and d['kind']!=org.kind: return error('Organization type cannot change after creation; create a separate organization instead.',409)
    name=str(d.get('name',org.name)).strip(); zone=str(d.get('zone',org.zone)).strip()
    if 'district' in d:
        try: zone=format_punjab_address('Response operations',d.get('district'))
        except ValueError as exc: return error(str(exc))
    if not 2<=len(name)<=140: return error('Organization name must be between 2 and 140 characters.')
    if Organization.objects.filter(name__iexact=name).exclude(pk=org.pk).exists(): return error('An organization with this name already exists.',409)
    previous={'name':org.name,'zone':org.zone}
    org.name=name; org.zone=zone[:120]
    try: org.save(update_fields=['name','zone'])
    except IntegrityError: return error('An organization with this name already exists.',409)
    changed={key:{'from':previous[key],'to':getattr(org,key)} for key in previous if previous[key]!=getattr(org,key)}
    if changed: EventLog.objects.create(actor=request.user,action='Organization updated',target=org.name,detail=changed)
    return JsonResponse({'ok':True,'organization':organization_json(org)})
@login_required
@require_http_methods(['GET','POST'])
def zone_applications(request):
    p=profile(request)
    if request.method=='POST':
        d=payload(request)
        if not p or p.role!='NGO' or p.approval!='APPROVED' or not p.organization: return error('Approved NGO Coordinator access required.',403)
        if not d.get('proposed_support'): return error('Proposed support is required.')
        if 'district' in d:
            try: zone=format_punjab_address('Relief response zone',d.get('district'))
            except ValueError as exc: return error(str(exc))
        else:
            # Keep compatibility for existing API clients while restricting new zone names.
            zone=str(d.get('zone','')).strip()
            if not any(district.lower() in zone.lower() for district in PUNJAB_DISTRICTS) or 'punjab' not in zone.lower(): return error('Choose a Punjab district for the response zone.')
        try: v=max(0,int(d.get('volunteer_availability',0))); cars=max(0,int(d.get('vehicle_availability',0)))
        except (ValueError,TypeError): return error('Volunteer and vehicle availability must be whole numbers.')
        a=ZoneApplication.objects.create(organization=p.organization,zone=zone,proposed_support=d['proposed_support'],volunteer_availability=v,vehicle_availability=cars)
        ZoneApplicationEvent.objects.create(application=a,actor=request.user,event_type='SUBMITTED',detail={'zone':a.zone,'proposed_support':a.proposed_support,'volunteer_availability':v,'vehicle_availability':cars})
        EventLog.objects.create(actor=request.user,action='NGO zone application submitted',target=a.organization.name,detail={'zone':a.zone})
        return JsonResponse({'ok':True,'id':a.id},status=201)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Organization access required.',403)
    qs=ZoneApplication.objects.select_related('organization','reviewed_by').prefetch_related('history__actor').all()
    if p.role=='NGO': qs=qs.filter(organization=p.organization)
    return JsonResponse({'results':[{'id':a.id,'organization':a.organization.name,'zone':a.zone,'proposed_support':a.proposed_support,'volunteer_availability':a.volunteer_availability,'vehicle_availability':a.vehicle_availability,'status':a.status,'review_note':a.review_note,'reviewer':a.reviewed_by.email if a.reviewed_by else None,'created_at':a.created_at.isoformat(),'history':[{'event_type':event.event_type,'actor':event.actor.get_full_name() or event.actor.email if event.actor else 'System','detail':event.detail,'created_at':event.created_at.isoformat()} for event in a.history.all()]} for a in qs.order_by('-created_at')[:100]]})
@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy reviewing this zone application. Refresh and try again.')
@transaction.atomic
def review_zone_application(request,pk):
    p=profile(request); a=ZoneApplication.objects.filter(pk=pk).first()
    if not a: return error('Zone application not found.',404)
    if not p or p.role not in ('ADMIN','GOV') or p.approval!='APPROVED': return error('Approved Government Official access required.',403)
    if a.status!='Pending': return error('This zone application has already been reviewed.',409)
    d=payload(request)
    if d.get('status') not in ('Approved','Rejected'): return error('Decision must be Approved or Rejected.')
    note=str(d.get('review_note','')).strip()
    if d['status']=='Rejected' and not note: return error('A rejection reason is required.')
    a.status=d['status']; a.review_note=note; a.reviewed_by=request.user; a.reviewed_at=timezone.now(); a.save(update_fields=['status','review_note','reviewed_by','reviewed_at'])
    ZoneApplicationEvent.objects.create(application=a,actor=request.user,event_type=a.status.upper(),detail={'status':a.status,'review_note':note})
    EventLog.objects.create(actor=request.user,action='NGO zone application '+a.status.lower(),target=a.organization.name,detail={'zone':a.zone,'note':a.review_note})
    coordinator=a.organization.members.filter(role='NGO').select_related('user').first()
    notify(coordinator.user if coordinator else None,'Zone application reviewed',f'{a.zone} application was {a.status.lower()}.'+(f' {note}' if note else ''),'/ngo.html')
    return JsonResponse({'ok':True,'status':a.status})
@login_required
@require_http_methods(['GET','POST'])
@sqlite_write_conflict('SQLite is busy updating inventory. Refresh and try again.')
def inventory(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Organization operations access required.',403)
    qs=Inventory.objects.select_related('organization').all()
    movements=InventoryMovement.objects.select_related('inventory__organization','destination_inventory','actor').all()
    if p.role in ('GOV','NGO'):
        qs=qs.filter(organization=p.organization)
        movements=movements.filter(inventory__organization=p.organization)
    if request.method=='POST':
        d=payload(request)
        if p.role=='ADMIN' or p.approval!='APPROVED' or not p.organization: return error('Approved organization account required.',403)
        try:
            qty=int(d.get('quantity',0)); minimum=int(d.get('minimum_quantity',10)); kind=d.get('kind'); item_name=str(d['item']).strip(); warehouse=str(d['warehouse']).strip(); warehouse_location=str(d.get('warehouse_location','')).strip()[:180]; destination_location=str(d.get('destination_warehouse_location','')).strip()[:180]; category=str(d.get('category','General')).strip()[:80] or 'General'
        except (ValueError,KeyError,TypeError,AttributeError): return error('Warehouse, item and valid quantities are required.')
        if qty<=0 or minimum<0 or kind not in ('RECEIPT','ISSUE','TRANSFER') or not item_name or not warehouse: return error('Choose a movement and enter valid item, warehouse and quantity details.')
        destination_name=str(d.get('destination_warehouse','')).strip()
        if kind=='TRANSFER' and (not destination_name or destination_name==warehouse): return error('Choose a different destination warehouse for this transfer.')
        linked_emergency=None
        if d.get('emergency_id'):
            if kind!='ISSUE': return error('Emergency allocations must be recorded as stock issues.')
            linked_emergency=Emergency.objects.filter(pk=d['emergency_id'],accepted_by=p.organization,status__in=['ACCEPTED','IN_PROGRESS']).first()
            if not linked_emergency: return error('Choose an active emergency accepted by your organization.',403)
            if p.role=='NGO': return error('Emergency-linked NGO stock issues must be proposed for Government authorization first.',403)
        with transaction.atomic():
            row=Inventory.objects.filter(organization=p.organization,warehouse=warehouse,item=item_name).first()
            if row is None:
                if kind!='RECEIPT': return error('Cannot issue or transfer stock that is not in inventory.')
                row=Inventory.objects.create(organization=p.organization,warehouse=warehouse,warehouse_location=warehouse_location,item=item_name,category=category,quantity=0,minimum_quantity=minimum,unit=str(d.get('unit','units')).strip() or 'units')
            elif 'category' in d and row.quantity==0:
                row.category=category
            if warehouse_location and not row.warehouse_location: row.warehouse_location=warehouse_location
            if kind in ('ISSUE','TRANSFER') and row.quantity<qty: return error('Movement exceeds available stock.')
            if 'minimum_quantity' in d: row.minimum_quantity=minimum
            if kind=='RECEIPT':
                row.quantity+=qty; row.save(update_fields=['quantity','minimum_quantity','category','warehouse_location','updated_at'])
                InventoryMovement.objects.create(inventory=row,actor=request.user,kind=kind,quantity=qty,note=str(d.get('note',''))[:240])
                EventLog.objects.create(actor=request.user,action='Inventory receipt',target=f'{warehouse}/{item_name}',detail={'quantity':qty,'minimum_quantity':row.minimum_quantity})
                result={'quantity':row.quantity}
            elif kind=='ISSUE':
                row.quantity-=qty; row.save(update_fields=['quantity','minimum_quantity','category','warehouse_location','updated_at'])
                InventoryMovement.objects.create(inventory=row,emergency=linked_emergency,actor=request.user,kind=kind,quantity=qty,note=str(d.get('note',''))[:240])
                EventLog.objects.create(actor=request.user,action='Inventory issue',target=f'{warehouse}/{item_name}',detail={'quantity':qty,'emergency':linked_emergency.reference if linked_emergency else None})
                result={'quantity':row.quantity}
            else:
                destination,created=Inventory.objects.get_or_create(organization=p.organization,warehouse=destination_name,item=item_name,defaults={'quantity':0,'minimum_quantity':row.minimum_quantity,'category':row.category,'warehouse_location':destination_location,'unit':row.unit})
                if destination.pk==row.pk: return error('Source and destination must be different inventory records.')
                if destination.unit!=row.unit or destination.category!=row.category: return error('Transfer units and categories must match the destination inventory item.')
                row.quantity-=qty; row.save(update_fields=['quantity','minimum_quantity','category','warehouse_location','updated_at'])
                destination.quantity+=qty; destination.save(update_fields=['quantity','updated_at'])
                InventoryMovement.objects.create(inventory=row,destination_inventory=destination,actor=request.user,kind='TRANSFER',quantity=qty,note=str(d.get('note',''))[:240])
                EventLog.objects.create(actor=request.user,action='Inventory transfer',target=f'{warehouse} → {destination_name}/{item_name}',detail={'quantity':qty,'unit':row.unit})
                result={'quantity':row.quantity,'destination_quantity':destination.quantity}
        return JsonResponse({'ok':True,**result})
    movement_rows=[{'kind':m.kind,'item':m.inventory.item,'organization':m.inventory.organization.name,'warehouse':m.inventory.warehouse,'warehouse_location':m.inventory.warehouse_location,'destination_warehouse':m.destination_inventory.warehouse if m.destination_inventory_id else None,'destination_location':m.destination_inventory.warehouse_location if m.destination_inventory_id else None,'emergency':m.emergency.reference if m.emergency_id else None,'quantity':m.quantity,'unit':m.inventory.unit,'note':m.note,'actor':m.actor.get_full_name() or m.actor.email if m.actor else 'System','created_at':m.created_at.isoformat()} for m in movements.select_related('emergency','destination_inventory','inventory').order_by('-created_at')[:300]]
    return JsonResponse({'results':[{'id':i.id,'organization':i.organization.name,'warehouse':i.warehouse,'warehouse_location':i.warehouse_location,'item':i.item,'category':i.category,'quantity':i.quantity,'minimum_quantity':i.minimum_quantity,'low_stock':i.quantity<=i.minimum_quantity,'unit':i.unit,'updated_at':i.updated_at.isoformat()} for i in qs.order_by('organization__name','warehouse','category','item')],'movements':movement_rows})
@login_required
def approvals(request):
    p=profile(request)
    if not p or p.role!='ADMIN': return error('Administrator access required.',403)
    return JsonResponse({'results':[{'id':x.id,'name':x.user.get_full_name(),'email':x.user.email,'phone':x.phone,'role':x.get_role_display(),'role_code':x.role,'organization':x.organization.name if x.organization else None,'details':public_profile_details(x.details),'created_at':x.user.date_joined.isoformat(),'approval_decided_at':x.approval_decided_at.isoformat() if x.approval_decided_at else None,'decided_by':x.approval_decided_by.get_full_name() if x.approval_decided_by else None,'rejection_reason':x.rejection_reason} for x in Profile.objects.filter(approval='PENDING',role__in=['GOV','NGO']).select_related('user','organization','approval_decided_by')]})
@login_required
@require_http_methods(['POST'])
def approve(request,pk):
    actor=profile(request)
    if not actor or actor.role!='ADMIN': return error('Administrator access required.',403)
    d=payload(request); p=Profile.objects.filter(pk=pk,approval='PENDING',role__in=['GOV','NGO']).first()
    if not p: return error('Pending application not found.',404)
    status=d.get('decision');
    if status not in ('APPROVED','REJECTED'): return error('Decision must be APPROVED or REJECTED.')
    reason=str(d.get('reason','')).strip()
    if status=='REJECTED' and not reason: return error('A rejection reason is required.')
    p.approval=status; p.approval_decided_at=timezone.now(); p.approval_decided_by=request.user; p.rejection_reason=reason if status=='REJECTED' else ''; p.save(update_fields=['approval','approval_decided_at','approval_decided_by','rejection_reason']); EventLog.objects.create(actor=request.user,action='Registration '+status.lower(),target=p.user.email,detail={'reason':reason}); notify(p.user,'Registration status updated',f'Your registration was {status.lower()}.'+(f' Reason: {reason}' if reason else ''),ROLE_PAGE.get(p.role,'/'))
    return JsonResponse({'ok':True,'approval':status})
@login_required
@require_http_methods(['GET','POST'])
def tickets(request):
    if request.method=='POST':
        d=payload(request)
        if not d.get('subject') or not d.get('description'): return error('Subject and description are required.')
        priority=d.get('priority','NORMAL').upper()
        if priority not in {x[0] for x in SupportTicket.PRIORITIES}: return error('Choose a valid ticket priority.')
        t=SupportTicket.objects.create(user=request.user,subject=d['subject'],category=d.get('category','General'),priority=priority,description=d['description']); SupportTicketEvent.objects.create(ticket=t,actor=request.user,event_type='CREATED',detail={'reference':t.reference,'subject':t.subject}); EventLog.objects.create(actor=request.user,action='Support ticket created',target=t.reference)
        for admin in Profile.objects.filter(role='ADMIN',approval='APPROVED').select_related('user'): notify(admin.user,'New support ticket',f'{t.reference}: {t.subject}','/admin.html')
        return JsonResponse({'ok':True,'id':t.id,'reference':t.reference},status=201)
    p=profile(request); qs=SupportTicket.objects.all() if p and p.role=='ADMIN' else SupportTicket.objects.filter(user=request.user)
    return JsonResponse({'results':[{'id':t.id,'reference':t.reference,'subject':t.subject,'category':t.category,'priority':t.priority,'status':t.status,'description':t.description,'assigned_to':t.assigned_to.email if t.assigned_to else None,'created_at':t.created_at.isoformat(),'updated_at':t.updated_at.isoformat(),'user':t.user.email,'role':getattr(getattr(t.user,'profile',None),'get_role_display',lambda:'Citizen')(),'replies':[{'author':r.author.email if r.author else 'System','body':r.body,'created_at':r.created_at.isoformat()} for r in t.replies.all()],'history':[{'event_type':h.event_type,'detail':h.detail,'actor':h.actor.email if h.actor else 'System','created_at':h.created_at.isoformat()} for h in t.history.select_related('actor').order_by('created_at')]} for t in qs.select_related('user','user__profile','assigned_to').prefetch_related('replies__author','history__actor').order_by('-created_at')[:100]]})
@login_required
@require_http_methods(['POST'])
def ticket_reply(request,pk):
    p=profile(request); t=SupportTicket.objects.select_related('user').filter(pk=pk).first()
    if not t: return error('Support ticket not found.',404)
    is_admin=bool(p and p.role=='ADMIN')
    if not is_admin and t.user_id!=request.user.id: return error('You cannot view or reply to this ticket.',403)
    d=payload(request); body=(d.get('body') or '').strip(); status=d.get('status') or None; priority=d.get('priority') or None
    if not is_admin and (status or priority or 'assigned_to' in d): return error('Only Administrators may change ticket workflow or assignment.',403)
    if not is_admin and not body: return error('Reply text is required.')
    if is_admin and status is not None and status not in {x[0] for x in SupportTicket.STATUSES}: return error('Choose a valid ticket status.')
    if is_admin and priority is not None and priority not in {x[0] for x in SupportTicket.PRIORITIES}: return error('Choose a valid ticket priority.')
    if not body and status is None and priority is None and 'assigned_to' not in d: return error('Add a reply or change the ticket workflow.')
    if body: SupportReply.objects.create(ticket=t,author=request.user,body=body)
    changed=[]
    if is_admin and status is not None: t.status=status; changed.append('status')
    if is_admin and priority is not None: t.priority=priority; changed.append('priority')
    if is_admin and 'assigned_to' in d:
        assigned=User.objects.filter(pk=d.get('assigned_to'),is_active=True).first() if d.get('assigned_to') else None
        if d.get('assigned_to') and not assigned: return error('Selected support assignee does not exist.')
        t.assigned_to=assigned; changed.append('assigned_to')
    if changed: t.save(update_fields=[*changed,'updated_at'])
    elif body: t.save(update_fields=['updated_at'])
    if is_admin and status=='Resolved':
        EventLog.objects.create(actor=request.user,action='Support ticket resolved',target=str(t.pk))
    if body or changed: SupportTicketEvent.objects.create(ticket=t,actor=request.user,event_type='REPLIED' if body else 'UPDATED',detail={'status':t.status,'priority':t.priority,'assigned_to':t.assigned_to.email if t.assigned_to else None,'reply':body[:500]})
    if is_admin: notify(t.user,'Support ticket reply',f'New reply on ticket: {t.subject}','/citizen.html')
    else:
        for admin in Profile.objects.filter(role='ADMIN',approval='APPROVED').select_related('user'): notify(admin.user,'New support reply',f'{t.subject} has a new reply.','/admin.html')
    return JsonResponse({'ok':True,'status':t.status})
@login_required
@require_http_methods(['GET'])
def notifications(request):
    rows=request.user.notifications.order_by('-created_at')[:100]
    return JsonResponse({'results':[{'id':n.id,'title':n.title,'body':n.body,'link':n.link,'read':bool(n.read_at),'created_at':n.created_at.isoformat()} for n in rows]})
@login_required
@require_http_methods(['POST'])
def notification_read(request,pk):
    n=Notification.objects.filter(pk=pk,user=request.user).first()
    if not n: return error('Notification not found.',404)
    if not n.read_at: n.read_at=timezone.now(); n.save(update_fields=['read_at'])
    return JsonResponse({'ok':True})
@login_required
def audit(request):
    p=profile(request)
    if not p or p.role!='ADMIN': return error('Administrator access required.',403)
    rows=EventLog.objects.select_related('actor').order_by('-created_at')[:200]
    return JsonResponse({'results':[{'actor':x.actor.email if x.actor else 'System','action':x.action,'target':x.target,'detail':x.detail,'created_at':x.created_at.isoformat()} for x in rows]})
