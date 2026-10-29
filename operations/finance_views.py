import uuid
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, F
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .api_common import error, payload, profile, notify, sqlite_write_conflict
from .models import Organization, FundTransaction, DonationCampaign, Donation, EventLog

def create_demo_donation_ledger_entry(donation, actor=None):
    campaign=donation.campaign
    if not donation.demo or donation.status!='CONFIRMED' or not campaign or not campaign.organization_id: return None
    row,_=FundTransaction.objects.get_or_create(reference='DEMO-'+donation.reference,defaults={'organization':campaign.organization,'kind':'DEMO_DONATION','amount':donation.amount,'source':f'Demo donation · {campaign.name}'[:140],'note':'Simulated citizen transfer; no money was transferred.','actor':actor or donation.donor,'donation':donation,'demo':True})
    return row

@login_required
@require_http_methods(['GET','POST'])
@sqlite_write_conflict('SQLite is busy updating the fund ledger. Refresh and try again.')
@transaction.atomic
def funds(request):
    p=profile(request)
    if not p or p.role not in ('ADMIN','GOV','NGO'): return error('Financial operations access required.',403)
    qs=FundTransaction.objects.select_related('organization','actor').all()
    if p.role in ('GOV','NGO'): qs=qs.filter(organization=p.organization)
    if request.method=='GET':
        rows=[]
        for org in Organization.objects.filter(id__in=qs.values('organization_id')).distinct():
            allocations=FundTransaction.objects.filter(organization=org,kind='ALLOCATION').aggregate(n=Sum('amount'))['n'] or 0
            expenditure=FundTransaction.objects.filter(organization=org,kind='EXPENDITURE').aggregate(n=Sum('amount'))['n'] or 0
            demo_donations=FundTransaction.objects.filter(organization=org,kind='DEMO_DONATION').aggregate(n=Sum('amount'))['n'] or 0
            rows.append({'organization':org.name,'allocated':str(allocations),'expenditure':str(expenditure),'balance':str(allocations-expenditure),'demo_donations':f'{demo_donations:.2f}'})
        return JsonResponse({'balances':rows,'results':[{'organization':x.organization.name,'kind':x.kind,'amount':str(x.amount),'source':x.source,'reference':x.reference,'note':x.note,'demo':x.demo,'created_at':x.created_at.isoformat()} for x in qs.order_by('-created_at')[:200]]})
    if p.role not in ('GOV','NGO') or p.approval!='APPROVED' or not p.organization: return error('Approved organization account required.',403)
    d=payload(request); kind=d.get('kind')
    if kind not in ('ALLOCATION','EXPENDITURE') or (kind=='ALLOCATION' and p.role!='GOV'): return error('NGOs may record expenditures; Government Officials may record allocations or expenditures.',403)
    from decimal import Decimal, InvalidOperation
    try: amount=Decimal(str(d.get('amount','0')))
    except InvalidOperation: amount=Decimal('0')
    if amount<=0 or not d.get('source'): return error('Enter a positive amount and fund source.')
    org=Organization.objects.get(pk=p.organization_id)
    if kind=='EXPENDITURE':
        # Start with a write on SQLite so competing expenditures serialize
        # before either transaction reads the balance.
        Organization.objects.filter(pk=org.pk).update(name=F('name'))
        allocated=FundTransaction.objects.filter(organization=org,kind='ALLOCATION').aggregate(n=Sum('amount'))['n'] or Decimal('0.00')
        spent=FundTransaction.objects.filter(organization=org,kind='EXPENDITURE').aggregate(n=Sum('amount'))['n'] or Decimal('0.00')
        if spent+amount>allocated: return error('Expenditure exceeds the remaining allocated funds.',409)
    import uuid
    row=FundTransaction.objects.create(organization=org,kind=kind,amount=amount,source=d['source'],reference='FND-'+uuid.uuid4().hex[:12].upper(),note=d.get('note',''),actor=request.user)
    EventLog.objects.create(actor=request.user,action='Fund '+kind.lower(),target=row.reference,detail={'amount':str(amount),'organization':org.name})
    return JsonResponse({'ok':True,'reference':row.reference},status=201)

@require_http_methods(['GET','POST'])
def campaigns(request):
    if request.method=='GET':
        rows=DonationCampaign.objects.select_related('organization').all(); p=profile(request) if request.user.is_authenticated else None
        if p and p.role=='ADMIN': pass
        elif p and p.role in ('GOV','NGO'): rows=rows.filter(organization=p.organization) if p.organization else rows.none()
        else: rows=rows.filter(published=True)
        return JsonResponse({'demo_mode':settings.DEMO_PAYMENT_MODE,'results':[{'id':x.id,'name':x.name,'recipient':x.recipient,'organization_id':x.organization_id,'organization':x.organization.name if x.organization else None,'organization_kind':x.organization.kind if x.organization else None,'description':x.description,'goal_amount':str(x.goal_amount),'currency':x.currency,'confirmed_total':str(x.confirmed_total()),'demo_confirmed_total':str(x.demo_confirmed_total()),'demo':x.demo,'published':x.published} for x in rows.order_by('name')]})
    p=profile(request)
    if not request.user.is_authenticated or not p or p.role not in ('ADMIN','GOV','NGO') or p.approval!='APPROVED': return error('Approved organization account required.',403)
    d=payload(request)
    if not d.get('name') or not d.get('recipient') or not d.get('description'): return error('Campaign name, recipient and description are required.')
    try: goal=Decimal(str(d.get('goal_amount','0')))
    except InvalidOperation: goal=Decimal('-1')
    if goal<0: return error('Campaign goal must be zero or greater.')
    campaign=DonationCampaign.objects.create(name=d['name'],recipient=d['recipient'],organization=p.organization,description=d['description'],goal_amount=goal,currency='INR',published=bool(d.get('published',True)))
    EventLog.objects.create(actor=request.user,action='Donation campaign published' if campaign.published else 'Donation campaign drafted',target=campaign.name)
    return JsonResponse({'ok':True,'id':campaign.id},status=201)
@login_required
@require_http_methods(['GET','POST'])
def donations(request):
    p=profile(request)
    if request.method=='GET':
        qs=Donation.objects.select_related('campaign','donor')
        if p.role=='CITIZEN': qs=qs.filter(donor=request.user)
        elif p.role=='NGO': qs=qs.filter(campaign__organization=p.organization)
        elif p.role not in ('ADMIN','GOV'): return error('Donation history access is restricted.',403)
        return JsonResponse({'results':[{'id':x.id,'reference':x.reference,'donor':x.donor.email,'amount':str(x.amount),'currency':x.currency,'status':x.status,'demo':x.demo,'campaign':x.campaign.name if x.campaign else None,'recipient':x.campaign.recipient if x.campaign else None,'organization':x.campaign.organization.name if x.campaign and x.campaign.organization else None,'created_at':x.created_at.isoformat(),'confirmed_at':x.confirmed_at.isoformat() if x.confirmed_at else None,'failure_reason':x.failure_reason,'receipt_url':f'/api/donations/{x.pk}/receipt/'} for x in qs.order_by('-created_at')[:100]]})
    if not p or p.role!='CITIZEN': return error('Only Citizens can submit donations.',403)
    d=payload(request)
    try: amount=Decimal(str(d.get('amount','0')))
    except InvalidOperation: amount=Decimal('0')
    campaign=DonationCampaign.objects.filter(pk=d.get('campaign_id'),published=True).first()
    if not amount.is_finite() or amount<=0: return error('Enter a valid donation amount above zero.')
    if amount>Decimal('9999999999.99') or amount.quantize(Decimal('0.01'))!=amount: return error('Donation amount must be at most INR 9,999,999,999.99 with no more than two decimal places.')
    if not campaign: return error('Choose an available published campaign.')
    import uuid
    donation=Donation.objects.create(donor=request.user,campaign=campaign,amount=amount,currency=campaign.currency,status='PENDING',reference='DON-'+uuid.uuid4().hex[:10].upper(),demo=settings.DEMO_PAYMENT_MODE)
    EventLog.objects.create(actor=request.user,action='Demo donation intent created' if donation.demo else 'Donation intent created',target=donation.reference,detail={'campaign':campaign.name,'amount':str(amount)})
    return JsonResponse({'ok':True,'demo_mode':settings.DEMO_PAYMENT_MODE,'donation':{'id':donation.id,'reference':donation.reference,'amount':str(donation.amount),'currency':donation.currency,'status':donation.status,'demo':donation.demo},'message':'Donation intent saved. No money was charged.'},status=201)

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy saving this demo fund transfer. Refresh and try again.')
@transaction.atomic
def demo_fund_transfer(request):
    p=profile(request)
    if not p or p.role!='CITIZEN': return error('Only Citizens can confirm demo fund transfers.',403)
    if not settings.DEMO_PAYMENT_MODE: return error('Demonstration transfers are currently disabled.',403)
    d=payload(request)
    try: amount=Decimal(str(d.get('amount','0')))
    except InvalidOperation: amount=Decimal('0')
    if not amount.is_finite() or amount<=0 or amount>Decimal('9999999999.99') or amount.quantize(Decimal('0.01'))!=amount:
        return error('Enter a positive amount with no more than two decimal places (maximum INR 9,999,999,999.99).')
    organization_kind=d.get('organization_kind')
    if organization_kind not in ('GOV','NGO'): return error('Choose Government or NGO as the recipient type.')
    campaign=DonationCampaign.objects.select_related('organization').filter(pk=d.get('campaign_id'),organization_id=d.get('organization_id'),published=True,organization__kind=organization_kind).first()
    if not campaign: return error('Choose a published campaign belonging to the selected recipient type.',404)
    donation=Donation.objects.create(donor=request.user,campaign=campaign,amount=amount,currency=campaign.currency,status='CONFIRMED',reference='DON-'+uuid.uuid4().hex[:10].upper(),demo=True,confirmed_at=timezone.now())
    ledger=create_demo_donation_ledger_entry(donation,request.user)
    EventLog.objects.create(actor=request.user,action='Demo fund transfer confirmed',target=donation.reference,detail={'campaign_id':campaign.pk,'organization_id':campaign.organization_id,'amount':str(amount),'ledger_reference':ledger.reference if ledger else None})
    notify(request.user,'Demo fund transfer recorded',f'{donation.reference}: INR {donation.amount} allocated to {campaign.organization.name}. No real money was transferred.','/citizen.html')
    return JsonResponse({'ok':True,'demo':True,'donation_id':donation.pk,'reference':donation.reference,'amount':str(donation.amount),'organization':campaign.organization.name,'campaign':campaign.name,'status':donation.status,'receipt_url':f'/api/donations/{donation.pk}/receipt/','message':'Demo transfer recorded. No real money was transferred.'},status=201)

@login_required
@require_http_methods(['POST'])
@sqlite_write_conflict('SQLite is busy updating this demo donation. Refresh and try again.')
@transaction.atomic
def demo_donation_result(request,pk):
    if not settings.DEMO_PAYMENT_MODE: return error('Demonstration payment mode is disabled.',403)
    donation=Donation.objects.select_related('campaign').filter(pk=pk,donor=request.user,demo=True).first()
    if not donation: return error('Demo donation not found.',404)
    if donation.status!='PENDING': return error('This donation already has a final payment status.',409)
    status=payload(request).get('status')
    if status not in ('CONFIRMED','FAILED'): return error('Choose a simulated successful or failed result.')
    confirmed_at=timezone.now() if status=='CONFIRMED' else None
    failure_reason='Demonstration failure result' if status=='FAILED' else ''
    changed=Donation.objects.filter(pk=pk,donor=request.user,demo=True,status='PENDING').update(status=status,confirmed_at=confirmed_at,failure_reason=failure_reason)
    if not changed: return error('This donation already has a final payment status.',409)
    donation=Donation.objects.select_related('campaign').get(pk=pk)
    if status=='CONFIRMED' and donation.demo: create_demo_donation_ledger_entry(donation,request.user)
    EventLog.objects.create(actor=request.user,action='Demo donation '+status.lower(),target=donation.reference,detail={'campaign':donation.campaign.name if donation.campaign else None})
    notify(request.user,'Demo donation status updated',f'{donation.reference}: simulated {status.lower()} result. No real funds were transferred.','/citizen.html')
    return JsonResponse({'ok':True,'status':status,'message':f'Demo payment marked {status.lower()}; this is not a real payment.'})
@login_required
@require_http_methods(['GET'])
def donation_receipt(request,pk):
    donation=Donation.objects.select_related('campaign').filter(pk=pk,donor=request.user,status='CONFIRMED').first()
    if not donation: return error('Confirmed donation receipt not found.',404)
    if donation.demo:
        text_body=f'DRRAS DEMONSTRATION RECEIPT\nSIMULATED PAYMENT — NO MONEY WAS TRANSFERRED\nNot a tax receipt or proof of payment.\nReference: {donation.reference}\nCampaign: {donation.campaign.name if donation.campaign else "Relief"}\nAmount: {donation.currency} {donation.amount}\nDate: {donation.confirmed_at}\n'
    else:
        text_body=f'DRRAS PAYMENT RECEIPT\nReference: {donation.reference}\nCampaign: {donation.campaign.name if donation.campaign else "Relief"}\nAmount: {donation.currency} {donation.amount}\nDate: {donation.confirmed_at}\n'
    response=HttpResponse(text_body,content_type='text/plain; charset=utf-8'); response['Content-Disposition']=f'attachment; filename="{donation.reference}.txt"'; return response
