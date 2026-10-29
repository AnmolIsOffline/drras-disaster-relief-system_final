from django.conf import settings
from django.db import models
from django.db.models import Q
import uuid

def delivery_photo_path(instance, filename):
    extension=filename.rsplit('.',1)[-1].lower() if '.' in filename else 'jpg'
    return f'delivery_proofs/{uuid.uuid4().hex}.{extension}'

class Organization(models.Model):
    name=models.CharField(max_length=140, unique=True)
    kind=models.CharField(max_length=12, choices=[('GOV','Government'),('NGO','NGO')])
    zone=models.CharField(max_length=120, blank=True)
    demo=models.BooleanField(default=False)
    def __str__(self): return self.name

class Profile(models.Model):
    ROLES=[('ADMIN','Administrator'),('GOV','Government Official'),('NGO','NGO Coordinator'),('GOV_VOL','Government Volunteer'),('NGO_VOL','NGO Volunteer'),('GOV_DRIVER','Government Driver'),('NGO_DRIVER','NGO Driver'),('CITIZEN','Citizen')]
    APPROVAL=[('PENDING','Pending'),('APPROVED','Approved'),('REJECTED','Rejected'),('SUSPENDED','Suspended')]
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='profile')
    role=models.CharField(max_length=16,choices=ROLES,default='CITIZEN')
    organization=models.ForeignKey(Organization,null=True,blank=True,on_delete=models.SET_NULL,related_name='members')
    approval=models.CharField(max_length=12,choices=APPROVAL,default='APPROVED')
    approval_decided_at=models.DateTimeField(null=True,blank=True)
    approval_decided_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='profile_approval_decisions')
    rejection_reason=models.TextField(blank=True)
    phone=models.CharField(max_length=30,blank=True); details=models.JSONField(default=dict,blank=True)

class SystemPreference(models.Model):
    key=models.CharField(max_length=80,unique=True); value=models.JSONField(default=dict); updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); updated_at=models.DateTimeField(auto_now=True)

class SafetyTraining(models.Model):
    code=models.CharField(max_length=48,unique=True); title=models.CharField(max_length=160); category=models.CharField(max_length=80); content=models.TextField(); required_roles=models.JSONField(default=list); active=models.BooleanField(default=True); demo=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)

class TrainingCompletion(models.Model):
    training=models.ForeignKey(SafetyTraining,on_delete=models.CASCADE,related_name='completions'); user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='training_completions'); acknowledged_at=models.DateTimeField(null=True,blank=True); completed_at=models.DateTimeField(null=True,blank=True); note=models.TextField(blank=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['training','user'],name='unique_training_completion_per_user')]

class Emergency(models.Model):
    TYPES=[('Flood','Flood'),('Fire','Fire'),('Medical','Medical'),('Landslide','Landslide'),('Cyclone','Cyclone'),('Other','Other')]
    PRIORITIES=[('CRITICAL','Critical'),('HIGH','High'),('MEDIUM','Medium'),('LOW','Low')]
    SEVERITIES=[('LOW','Low'),('MODERATE','Moderate'),('SEVERE','Severe'),('CRITICAL','Critical')]
    STATUSES=[('OPEN','Open'),('ACCEPTED','Accepted'),('IN_PROGRESS','In progress'),('RESOLVED','Resolved'),('CANCELLED','Cancelled')]
    reference=models.CharField(max_length=16,unique=True); reporter=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='emergencies')
    category=models.CharField(max_length=24,choices=TYPES); severity=models.CharField(max_length=12,choices=SEVERITIES,default='MODERATE'); priority=models.CharField(max_length=12,choices=PRIORITIES,default='MEDIUM'); description=models.TextField()
    location=models.CharField(max_length=180); address=models.CharField(max_length=180,blank=True); district=models.CharField(max_length=40,blank=True); latitude=models.FloatField(null=True,blank=True); longitude=models.FloatField(null=True,blank=True); affected=models.PositiveIntegerField(null=True,blank=True,default=1); injured=models.PositiveIntegerField(null=True,blank=True,default=0); vulnerable_counts=models.JSONField(default=dict,blank=True); required_skills=models.CharField(max_length=240,blank=True); needs_transport=models.BooleanField(default=False); required_vehicle_capacity=models.PositiveIntegerField(default=0)
    priority_override_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='emergency_priority_overrides'); priority_override_reason=models.TextField(blank=True); priority_overridden_at=models.DateTimeField(null=True,blank=True)
    status=models.CharField(max_length=16,choices=STATUSES,default='OPEN',db_index=True); verification=models.CharField(max_length=20,default='Pending'); demo=models.BooleanField(default=False)
    accepted_by=models.ForeignKey(Organization,null=True,blank=True,on_delete=models.SET_NULL,related_name='accepted_emergencies'); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    def __str__(self): return self.reference

class EventLog(models.Model):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL); action=models.CharField(max_length=80); target=models.CharField(max_length=100); detail=models.JSONField(default=dict); created_at=models.DateTimeField(auto_now_add=True)

class EmergencyEvent(models.Model):
    emergency=models.ForeignKey(Emergency,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); event_type=models.CharField(max_length=40); from_status=models.CharField(max_length=16,blank=True); to_status=models.CharField(max_length=16,blank=True); note=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='notifications'); title=models.CharField(max_length=180); body=models.TextField(); link=models.CharField(max_length=240,blank=True); read_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class Assignment(models.Model):
    emergency=models.ForeignKey(Emergency,on_delete=models.CASCADE,related_name='assignments'); user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='assignments'); organization=models.ForeignKey(Organization,on_delete=models.PROTECT,related_name='assignments'); assigned_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='created_assignments'); kind=models.CharField(max_length=12,choices=[('VOL','Volunteer'),('DRIVER','Driver')]); status=models.CharField(max_length=20,default='ASSIGNED'); task_instructions=models.TextField(blank=True); completion_report=models.TextField(blank=True); blocked_note=models.TextField(blank=True); acknowledged_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    def save(self,*args,**kwargs):
        if not self.organization_id and self.emergency_id:
            emergency=self.emergency
            organization_id=emergency.accepted_by_id
            if not organization_id:
                organization_id=Profile.objects.filter(user_id=self.user_id).values_list('organization_id',flat=True).first()
            if organization_id: self.organization_id=organization_id
        super().save(*args,**kwargs)
    class Meta: constraints=[
        models.UniqueConstraint(fields=['emergency','user','kind'],name='unique_emergency_assignment'),
        models.UniqueConstraint(fields=['user'],condition=Q(status__in=['ASSIGNED','ACKNOWLEDGED','IN_PROGRESS','BLOCKED']),name='unique_active_assignment_per_user'),
    ]

class AssignmentEvent(models.Model):
    assignment=models.ForeignKey(Assignment,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); status=models.CharField(max_length=20); note=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)

class AllocationAuthorization(models.Model):
    STATUSES=[('PENDING','Pending'),('APPROVED','Approved'),('REJECTED','Rejected'),('EXECUTED','Executed')]
    emergency=models.ForeignKey(Emergency,on_delete=models.CASCADE,related_name='allocation_authorizations'); organization=models.ForeignKey(Organization,on_delete=models.PROTECT,related_name='allocation_authorizations'); requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='allocation_authorizations'); kind=models.CharField(max_length=12,choices=[('VOL','Volunteer team'),('DRIVER','Driver team'),('STOCK','Relief supplies')]); user_ids=models.JSONField(default=list); vehicle_ids=models.JSONField(default=list); inventory=models.ForeignKey('Inventory',null=True,blank=True,on_delete=models.SET_NULL,related_name='allocation_authorizations'); requested_quantity=models.PositiveIntegerField(null=True,blank=True); task_instructions=models.TextField(blank=True); pickup_location=models.CharField(max_length=180,blank=True); cargo_details=models.TextField(blank=True); status=models.CharField(max_length=12,choices=STATUSES,default='PENDING',db_index=True); reviewed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='reviewed_allocation_authorizations'); reviewed_at=models.DateTimeField(null=True,blank=True); decision_note=models.TextField(blank=True); executed_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class AllocationAuthorizationEvent(models.Model):
    authorization=models.ForeignKey(AllocationAuthorization,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); event_type=models.CharField(max_length=24); detail=models.JSONField(default=dict); created_at=models.DateTimeField(auto_now_add=True)

class Vehicle(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='vehicles'); registration=models.CharField(max_length=24,unique=True); kind=models.CharField(max_length=80,default='Relief van'); capacity=models.PositiveIntegerField(default=0); demo=models.BooleanField(default=False)
    def __str__(self): return self.registration

class Dispatch(models.Model):
    STATUSES=[('ASSIGNED','Assigned'),('ACCEPTED','Accepted'),('IN_TRANSIT','In transit'),('DELIVERED','Delivered'),('EXCEPTION','Exception'),('CANCELLED','Cancelled')]
    emergency=models.ForeignKey(Emergency,on_delete=models.CASCADE,related_name='dispatches'); driver=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='dispatches'); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='dispatches'); vehicle=models.ForeignKey(Vehicle,null=True,blank=True,on_delete=models.SET_NULL,related_name='dispatches'); pickup_location=models.CharField(max_length=180,blank=True); destination=models.CharField(max_length=180); cargo_details=models.TextField(blank=True); trip_instructions=models.TextField(blank=True); delivery_proof=models.TextField(blank=True); status=models.CharField(max_length=16,choices=STATUSES,default='ASSIGNED'); delivered_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: constraints=[
        models.UniqueConstraint(fields=['emergency','driver'],name='unique_emergency_driver_dispatch'),
        models.UniqueConstraint(fields=['vehicle'],condition=Q(status__in=['ASSIGNED','ACCEPTED','IN_TRANSIT','EXCEPTION']),name='unique_active_dispatch_per_vehicle'),
    ]

class DispatchEvent(models.Model):
    dispatch=models.ForeignKey(Dispatch,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); status=models.CharField(max_length=16,choices=Dispatch.STATUSES); note=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)

class DeliveryRecord(models.Model):
    STATUSES=[('WAITING_CONFIRMATION','Waiting for citizen confirmation'),('CONFIRMED','Received by citizen'),('ISSUE_REPORTED','Issue reported by citizen')]
    dispatch=models.OneToOneField(Dispatch,on_delete=models.CASCADE,related_name='delivery_record'); emergency=models.ForeignKey(Emergency,on_delete=models.CASCADE,related_name='delivery_records'); driver=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='submitted_deliveries'); vehicle=models.ForeignKey(Vehicle,null=True,blank=True,on_delete=models.SET_NULL,related_name='delivery_records'); organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='delivery_records'); recipient_name=models.CharField(max_length=160); address=models.CharField(max_length=240); items=models.JSONField(default=list); delivered_at=models.DateTimeField(); photo=models.FileField(upload_to=delivery_photo_path,blank=True); remarks=models.TextField(blank=True); demo=models.BooleanField(default=False); status=models.CharField(max_length=24,choices=STATUSES,default='WAITING_CONFIRMATION',db_index=True); citizen_responded_at=models.DateTimeField(null=True,blank=True); issue_details=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)

class FundTransaction(models.Model):
    KINDS=[('ALLOCATION','Allocation'),('EXPENDITURE','Expenditure'),('DEMO_DONATION','Demo donation')]
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='fund_transactions'); kind=models.CharField(max_length=16,choices=KINDS); amount=models.DecimalField(max_digits=14,decimal_places=2); source=models.CharField(max_length=140); reference=models.CharField(max_length=48,unique=True); note=models.TextField(blank=True); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL); donation=models.OneToOneField('Donation',null=True,blank=True,on_delete=models.SET_NULL,related_name='fund_ledger_entry'); demo=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)

class Shelter(models.Model):
    name=models.CharField(max_length=140,unique=True); organization=models.ForeignKey(Organization,null=True,blank=True,on_delete=models.SET_NULL,related_name='shelters'); location=models.CharField(max_length=180); address=models.CharField(max_length=180,blank=True); district=models.CharField(max_length=40,blank=True); contact_phone=models.CharField(max_length=30,blank=True); shelter_type=models.CharField(max_length=40,default='Shelter'); description=models.TextField(blank=True); latitude=models.FloatField(); longitude=models.FloatField(); capacity=models.PositiveIntegerField(); occupancy=models.PositiveIntegerField(default=0); status=models.CharField(max_length=20,default='Open'); demo=models.BooleanField(default=False); updated_at=models.DateTimeField(auto_now=True)
    @property
    def available(self): return max(0,self.capacity-self.occupancy) if self.status=='Open' else 0
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(occupancy__lte=models.F('capacity')),name='shelter_occupancy_lte_capacity')]

class ShelterEvent(models.Model):
    shelter=models.ForeignKey(Shelter,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); event_type=models.CharField(max_length=32); changes=models.JSONField(default=dict); created_at=models.DateTimeField(auto_now_add=True)

class Inventory(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE); warehouse=models.CharField(max_length=140); warehouse_location=models.CharField(max_length=180,blank=True); item=models.CharField(max_length=120); category=models.CharField(max_length=80,default='General'); quantity=models.PositiveIntegerField(default=0); minimum_quantity=models.PositiveIntegerField(default=10); unit=models.CharField(max_length=30,default='units'); updated_at=models.DateTimeField(auto_now=True)
    class Meta: unique_together=[('organization','warehouse','item')]

class InventoryMovement(models.Model):
    inventory=models.ForeignKey(Inventory,on_delete=models.CASCADE,related_name='movements'); destination_inventory=models.ForeignKey(Inventory,null=True,blank=True,on_delete=models.SET_NULL,related_name='incoming_transfers'); emergency=models.ForeignKey(Emergency,null=True,blank=True,on_delete=models.SET_NULL,related_name='inventory_movements'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL); kind=models.CharField(max_length=12,choices=[('RECEIPT','Receipt'),('ISSUE','Issue'),('TRANSFER','Transfer')]); quantity=models.PositiveIntegerField(); note=models.CharField(max_length=240,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class DonationCampaign(models.Model):
    name=models.CharField(max_length=150); recipient=models.CharField(max_length=150); organization=models.ForeignKey(Organization,null=True,blank=True,on_delete=models.SET_NULL,related_name='donation_campaigns'); description=models.TextField(); goal_amount=models.DecimalField(max_digits=14,decimal_places=2,default=0); currency=models.CharField(max_length=3,default='INR'); published=models.BooleanField(default=False); demo=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)
    def confirmed_total(self): return self.donations.filter(status='PAYMENT_VERIFIED',demo=False).aggregate(total=models.Sum('amount'))['total'] or 0
    def submitted_total(self): return self.donations.filter(status='SUBMITTED',demo=False).aggregate(total=models.Sum('amount'))['total'] or 0
    def accepted_total(self): return self.donations.filter(status='ACCEPTED',demo=False).aggregate(total=models.Sum('amount'))['total'] or 0
    def demo_confirmed_total(self): return self.donations.filter(status='DEMO_RECORDED',demo=True).aggregate(total=models.Sum('amount'))['total'] or 0

class Donation(models.Model):
    STATUSES=[('SUBMITTED','Submitted for review'),('ACCEPTED','Accepted by recipient'),('REJECTED','Rejected by recipient'),('PAYMENT_VERIFIED','Payment verified'),('DEMO_RECORDED','Demo ledger transaction'),('PENDING','Legacy pending'),('CONFIRMED','Legacy confirmed'),('FAILED','Legacy failed')]
    donor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='donations'); organization=models.ForeignKey(Organization,null=True,blank=True,on_delete=models.PROTECT,related_name='contributions'); campaign=models.ForeignKey(DonationCampaign,null=True,blank=True,on_delete=models.PROTECT,related_name='donations'); amount=models.DecimalField(max_digits=12,decimal_places=2); currency=models.CharField(max_length=3,default='INR'); status=models.CharField(max_length=24,choices=STATUSES,default='SUBMITTED',db_index=True); reference=models.CharField(max_length=40,unique=True); provider_reference=models.CharField(max_length=120,blank=True); failure_reason=models.CharField(max_length=240,blank=True); demo=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True); confirmed_at=models.DateTimeField(null=True,blank=True)

class DonationEvent(models.Model):
    donation=models.ForeignKey(Donation,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); event_type=models.CharField(max_length=32); from_status=models.CharField(max_length=24,blank=True); to_status=models.CharField(max_length=24); note=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)

class Advisory(models.Model):
    SEVERITIES=[('LOW','Low'),('MEDIUM','Medium'),('HIGH','High'),('CRITICAL','Critical')]
    title=models.CharField(max_length=180); category=models.CharField(max_length=80,default='Public safety'); body=models.TextField(); location=models.CharField(max_length=160,blank=True); severity=models.CharField(max_length=12,choices=SEVERITIES,default='MEDIUM'); published=models.BooleanField(default=False); archived=models.BooleanField(default=False); withdrawn=models.BooleanField(default=False); demo=models.BooleanField(default=False); published_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='published_advisories'); expires_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)

class AdvisoryEvent(models.Model):
    EVENTS=[('DRAFTED','Drafted'),('UPDATED','Draft updated'),('PUBLISHED','Published'),('WITHDRAWN','Withdrawn'),('ARCHIVED','Archived')]
    advisory=models.ForeignKey(Advisory,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); event_type=models.CharField(max_length=16,choices=EVENTS); detail=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class ZoneApplication(models.Model):
    organization=models.ForeignKey(Organization,on_delete=models.CASCADE,related_name='zone_applications'); zone=models.CharField(max_length=140); proposed_support=models.TextField(); volunteer_availability=models.PositiveIntegerField(default=0); vehicle_availability=models.PositiveIntegerField(default=0); status=models.CharField(max_length=20,default='Pending'); review_note=models.TextField(blank=True); reviewed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); created_at=models.DateTimeField(auto_now_add=True); reviewed_at=models.DateTimeField(null=True,blank=True)

class ZoneApplicationEvent(models.Model):
    application=models.ForeignKey(ZoneApplication,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); event_type=models.CharField(max_length=24); detail=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class SupportTicket(models.Model):
    PRIORITIES=[('LOW','Low'),('NORMAL','Normal'),('HIGH','High'),('URGENT','Urgent')]
    STATUSES=[('Open','Open'),('In Progress','In Progress'),('Resolved','Resolved')]
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE); reference=models.CharField(max_length=24,unique=True); assigned_to=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='assigned_support_tickets'); subject=models.CharField(max_length=180); category=models.CharField(max_length=80,default='General'); priority=models.CharField(max_length=12,choices=PRIORITIES,default='NORMAL'); description=models.TextField(); status=models.CharField(max_length=20,choices=STATUSES,default='Open'); demo=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    def save(self,*args,**kwargs):
        if not self.reference: self.reference='SUP-'+uuid.uuid4().hex[:12].upper()
        super().save(*args,**kwargs)

class SupportTicketEvent(models.Model):
    ticket=models.ForeignKey(SupportTicket,on_delete=models.CASCADE,related_name='history'); actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); event_type=models.CharField(max_length=32); detail=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)

class SupportReply(models.Model):
    ticket=models.ForeignKey(SupportTicket,on_delete=models.CASCADE,related_name='replies'); author=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL); body=models.TextField(); created_at=models.DateTimeField(auto_now_add=True)
