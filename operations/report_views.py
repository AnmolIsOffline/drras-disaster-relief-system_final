import csv
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.utils.dateparse import parse_date
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from .api_common import error, profile
from .models import Emergency, EmergencyEvent, Profile, Donation, FundTransaction, Assignment, Dispatch, InventoryMovement, SupportTicket, Shelter, Inventory, Organization

def date_filtered_csv_queryset(request, queryset, field='created_at'):
    start_text=request.GET.get('start','').strip(); end_text=request.GET.get('end','').strip()
    start=parse_date(start_text) if start_text else None; end=parse_date(end_text) if end_text else None
    if (start_text and not start) or (end_text and not end): return None,error('Dates must use YYYY-MM-DD format.')
    if start and end and start>end: return None,error('Start date must be on or before end date.')
    if start: queryset=queryset.filter(**{field+'__date__gte':start})
    if end: queryset=queryset.filter(**{field+'__date__lte':end})
    return queryset,None

def csv_response(filename,headers,rows):
    response=HttpResponse(content_type='text/csv; charset=utf-8'); response['Content-Disposition']=f'attachment; filename="{filename}"'
    def safe_cell(value):
        if isinstance(value,str) and value[:1] in ('=','+','-','@','\t','\r'): return "'"+value
        return value
    writer=csv.writer(response); writer.writerow(headers); writer.writerows(([safe_cell(value) for value in row] for row in rows))
    return response

@login_required
def reports(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Administrator or organization coordinator access required.',403)
    start_text=request.GET.get('start','').strip(); end_text=request.GET.get('end','').strip()
    start=parse_date(start_text) if start_text else None; end=parse_date(end_text) if end_text else None
    if (start_text and not start) or (end_text and not end): return error('Dates must use YYYY-MM-DD format.')
    if start and end and start>end: return error('Start date must be on or before end date.')
    def date_scope(qs,field='created_at'):
        if start: qs=qs.filter(**{field+'__date__gte':start})
        if end: qs=qs.filter(**{field+'__date__lte':end})
        return qs
    emergencies=date_scope(Emergency.objects.all())
    donations=date_scope(Donation.objects.all())
    profiles=Profile.objects.all()
    if start: profiles=profiles.filter(user__date_joined__date__gte=start)
    if end: profiles=profiles.filter(user__date_joined__date__lte=end)
    funds=date_scope(FundTransaction.objects.all())
    assignments=date_scope(Assignment.objects.all())
    dispatches=date_scope(Dispatch.objects.all())
    inventory_movements=date_scope(InventoryMovement.objects.all())
    tickets=date_scope(SupportTicket.objects.all())
    resolution_events=date_scope(EmergencyEvent.objects.filter(event_type='RESOLVED'))
    shelters=Shelter.objects.all()
    inventory=Inventory.objects.all()
    if p.role in ('GOV','NGO'):
        if not p.organization: return error('Coordinator account is not linked to an organization.',403)
        emergencies=emergencies.filter(accepted_by=p.organization)
        profiles=profiles.filter(organization=p.organization)
        donations=donations.filter(campaign__organization=p.organization)
        funds=funds.filter(organization=p.organization)
        assignments=assignments.filter(organization=p.organization)
        dispatches=dispatches.filter(organization=p.organization)
        inventory_movements=inventory_movements.filter(inventory__organization=p.organization)
        tickets=tickets.filter(user__profile__organization=p.organization) if p.role=='NGO' else tickets.none()
        resolution_events=resolution_events.filter(emergency__accepted_by=p.organization)
        shelters=shelters.filter(organization=p.organization)
        inventory=inventory.filter(organization=p.organization)
    real_total=donations.filter(status='PAYMENT_VERIFIED',demo=False,provider_reference__gt='').aggregate(amount=Sum('amount'))['amount'] or 0
    demo_total=donations.filter(status='DEMO_RECORDED',demo=True).aggregate(amount=Sum('amount'))['amount'] or 0
    organizations=Organization.objects.all()
    if p.role in ('GOV','NGO'): organizations=organizations.filter(pk=p.organization_id)
    org_activity=[]
    for org in organizations.order_by('kind','name'):
        org_emergencies=emergencies.filter(accepted_by=org)
        org_assignments=assignments.filter(organization=org)
        org_dispatches=dispatches.filter(organization=org)
        org_activity.append({'organization':org.name,'kind':org.kind,'requests':org_emergencies.count(),'assignments':org_assignments.count(),'active_assignments':org_assignments.filter(status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']).count(),'dispatches':org_dispatches.count()})
    return JsonResponse({
        'filters':{'start':start_text,'end':end_text},
        'emergency_status':list(emergencies.values('status').annotate(total=Count('id')).order_by('status')),
        'emergency_priority':list(emergencies.values('priority').annotate(total=Count('id')).order_by('priority')),
        'emergency_category':list(emergencies.values('category').annotate(total=Count('id')).order_by('category')),
        'emergencies_by_day':list(emergencies.annotate(day=TruncDate('created_at')).values('day').annotate(total=Count('id')).order_by('day')),
        'resolutions_by_day':list(resolution_events.annotate(day=TruncDate('created_at')).values('day').annotate(total=Count('id')).order_by('day')),
        'users_by_role':list(profiles.values('role').annotate(total=Count('id')).order_by('role')),
        'registrations_by_day':list(profiles.annotate(day=TruncDate('user__date_joined')).values('day').annotate(total=Count('id')).order_by('day')),
        'assignments_by_kind_status':list(assignments.values('kind','status').annotate(total=Count('id')).order_by('kind','status')),
        'dispatches_by_status':list(dispatches.values('status').annotate(total=Count('id')).order_by('status')),
        'organization_activity':org_activity,
        'donations_by_status':list(donations.values('status','demo').annotate(total=Count('id'),amount=Sum('amount')).order_by('status','demo')),
        'real_confirmed_donations':str(real_total),'demo_confirmed_donations':str(demo_total),
        'funds_by_kind':list(funds.values('kind').annotate(total=Count('id'),amount=Sum('amount')).order_by('kind')),
        'shelter_capacity':{'capacity':shelters.aggregate(n=Sum('capacity'))['n'] or 0,'occupancy':shelters.aggregate(n=Sum('occupancy'))['n'] or 0,'shelters':shelters.count()},
        'inventory_items':inventory.aggregate(total=Sum('quantity'))['total'] or 0,
        'inventory_by_organization':list(inventory.values('organization__name').annotate(units=Sum('quantity'),items=Count('id')).order_by('organization__name')),
        'inventory_movements':list(inventory_movements.values('kind').annotate(total=Count('id'),quantity=Sum('quantity')).order_by('kind')),
        'tickets_by_status':list(tickets.values('status').annotate(total=Count('id')).order_by('status')),
        'tickets_by_priority':list(tickets.values('priority').annotate(total=Count('id')).order_by('priority')),
    })
@login_required
def export_emergencies(request):
    p=profile(request); qs=Emergency.objects.all()
    if not p or p.role not in ('ADMIN','GOV','NGO','CITIZEN'): return error('You cannot export emergency reports.',403)
    start=parse_date(request.GET.get('start','')) if request.GET.get('start') else None; end=parse_date(request.GET.get('end','')) if request.GET.get('end') else None
    if request.GET.get('start') and not start or request.GET.get('end') and not end: return error('Dates must use YYYY-MM-DD format.')
    if start: qs=qs.filter(created_at__date__gte=start)
    if end: qs=qs.filter(created_at__date__lte=end)
    if p and p.role=='CITIZEN': qs=qs.filter(reporter=request.user)
    elif p and p.role=='NGO': qs=qs.filter(accepted_by=p.organization)
    rows=([e.reference,e.category,e.description,e.priority,e.location,e.affected,e.status,e.accepted_by.name if e.accepted_by else '',e.demo,e.created_at.isoformat()] for e in qs.select_related('accepted_by'))
    return csv_response('drras-emergencies.csv',['reference','category','description','priority','location','affected','status','organization','demo','created_at'],rows)

@login_required
@require_http_methods(['GET'])
def export_donations(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Financial operations access required.',403)
    qs=Donation.objects.select_related('campaign','donor')
    if p.role=='NGO': qs=qs.filter(campaign__organization=p.organization)
    start=parse_date(request.GET.get('start','')) if request.GET.get('start') else None; end=parse_date(request.GET.get('end','')) if request.GET.get('end') else None
    if request.GET.get('start') and not start or request.GET.get('end') and not end: return error('Dates must use YYYY-MM-DD format.')
    if start: qs=qs.filter(created_at__date__gte=start)
    if end: qs=qs.filter(created_at__date__lte=end)
    rows=([d.reference,d.donor.email,d.campaign.name if d.campaign else '',d.campaign.recipient if d.campaign else '',d.amount,d.currency,d.status,d.demo,d.created_at.isoformat(),d.confirmed_at.isoformat() if d.confirmed_at else '',d.failure_reason] for d in qs.order_by('-created_at'))
    return csv_response('drras-donations.csv',['reference','donor','campaign','recipient','amount','currency','status','demo','created_at','confirmed_at','failure_reason'],rows)

@login_required
@require_http_methods(['GET'])
def export_funds(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Financial operations access required.',403)
    qs=FundTransaction.objects.select_related('organization','actor')
    if p.role in ('GOV','NGO'): qs=qs.filter(organization=p.organization)
    start=parse_date(request.GET.get('start','')) if request.GET.get('start') else None; end=parse_date(request.GET.get('end','')) if request.GET.get('end') else None
    if request.GET.get('start') and not start or request.GET.get('end') and not end: return error('Dates must use YYYY-MM-DD format.')
    if start: qs=qs.filter(created_at__date__gte=start)
    if end: qs=qs.filter(created_at__date__lte=end)
    rows=([f.reference,f.organization.name,f.kind,f.amount,f.source,f.note,f.demo,f.actor.email if f.actor else '',f.created_at.isoformat()] for f in qs.order_by('-created_at'))
    return csv_response('drras-funds.csv',['reference','organization','kind','amount','source','note','demo','actor','created_at'],rows)

@login_required
@require_http_methods(['GET'])
def export_assignments(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Operational report access required.',403)
    qs=Assignment.objects.select_related('organization','emergency','user','assigned_by')
    if p.role in ('GOV','NGO'):
        if not p.organization: return error('Coordinator account is not linked to an organization.',403)
        qs=qs.filter(organization=p.organization)
    qs,problem=date_filtered_csv_queryset(request,qs)
    if problem: return problem
    rows=([a.emergency.reference,a.organization.name,a.user.email,a.kind,a.status,a.task_instructions,a.completion_report,a.blocked_note,a.assigned_by.email if a.assigned_by else '',a.created_at.isoformat(),a.updated_at.isoformat()] for a in qs.order_by('-created_at'))
    return csv_response('drras-assignments.csv',['emergency','organization','responder_email','kind','status','instructions','completion_report','blocked_note','assigned_by_email','created_at','updated_at'],rows)

@login_required
@require_http_methods(['GET'])
def export_dispatches(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Operational report access required.',403)
    qs=Dispatch.objects.select_related('organization','emergency','driver','vehicle')
    if p.role in ('GOV','NGO'):
        if not p.organization: return error('Coordinator account is not linked to an organization.',403)
        qs=qs.filter(organization=p.organization)
    qs,problem=date_filtered_csv_queryset(request,qs)
    if problem: return problem
    rows=([d.emergency.reference,d.organization.name,d.driver.email,d.vehicle.registration if d.vehicle else '',d.vehicle.capacity if d.vehicle else '',d.pickup_location,d.destination,d.cargo_details,d.status,d.delivery_proof,d.created_at.isoformat(),d.delivered_at.isoformat() if d.delivered_at else ''] for d in qs.order_by('-created_at'))
    return csv_response('drras-dispatches.csv',['emergency','organization','driver_email','vehicle','vehicle_capacity','pickup_location','destination','cargo','status','delivery_proof','created_at','delivered_at'],rows)

@login_required
@require_http_methods(['GET'])
def export_inventory(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Operational report access required.',403)
    qs=Inventory.objects.select_related('organization')
    if p.role in ('GOV','NGO'):
        if not p.organization: return error('Coordinator account is not linked to an organization.',403)
        qs=qs.filter(organization=p.organization)
    qs,problem=date_filtered_csv_queryset(request,qs,'updated_at')
    if problem: return problem
    rows=([i.organization.name,i.warehouse,i.warehouse_location,i.category,i.item,i.quantity,i.unit,i.minimum_quantity,i.quantity<=i.minimum_quantity,i.updated_at.isoformat()] for i in qs.order_by('organization__name','warehouse','item'))
    return csv_response('drras-inventory.csv',['organization','warehouse','warehouse_location','category','item','quantity','unit','minimum_quantity','low_stock','updated_at'],rows)

@login_required
@require_http_methods(['GET'])
def export_inventory_movements(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Operational report access required.',403)
    qs=InventoryMovement.objects.select_related('inventory__organization','destination_inventory','emergency','actor')
    if p.role in ('GOV','NGO'):
        if not p.organization: return error('Coordinator account is not linked to an organization.',403)
        qs=qs.filter(inventory__organization=p.organization)
    qs,problem=date_filtered_csv_queryset(request,qs)
    if problem: return problem
    rows=([m.kind,m.inventory.organization.name,m.inventory.warehouse,m.inventory.warehouse_location,m.inventory.category,m.inventory.item,m.quantity,m.inventory.unit,m.destination_inventory.warehouse if m.destination_inventory_id else '',m.destination_inventory.warehouse_location if m.destination_inventory_id else '',m.emergency.reference if m.emergency_id else '',m.actor.email if m.actor else '',m.note,m.created_at.isoformat()] for m in qs.order_by('-created_at'))
    return csv_response('drras-inventory-movements.csv',['kind','organization','warehouse','warehouse_location','category','item','quantity','unit','destination_warehouse','destination_location','emergency','actor_email','note','created_at'],rows)

@login_required
@require_http_methods(['GET'])
def export_shelters(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Operational report access required.',403)
    qs=Shelter.objects.select_related('organization')
    if p.role in ('GOV','NGO'):
        if not p.organization: return error('Coordinator account is not linked to an organization.',403)
        qs=qs.filter(organization=p.organization)
    qs,problem=date_filtered_csv_queryset(request,qs,'updated_at')
    if problem: return problem
    rows=([s.name,s.organization.name if s.organization else '',s.location,s.shelter_type,s.description,s.latitude,s.longitude,s.status,s.capacity,s.occupancy,s.available,s.updated_at.isoformat(),s.demo] for s in qs.order_by('name'))
    return csv_response('drras-shelters.csv',['name','organization','address','type','description','latitude','longitude','status','capacity','occupancy','available','updated_at','demo'],rows)
