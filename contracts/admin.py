from django.contrib import admin
from django.utils.html import format_html

from contracts.models import TimelyAction, RepaymentTemplate, Contract, ScheduledPayment

# Register your models here.

@admin.register(TimelyAction)
class TimelyActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_regularity_display', 'get_schedule_summary')
    list_filter = ('regularity',)
    
    def get_schedule_summary(self, obj):
        return str(obj)
    get_schedule_summary.short_description = 'Schedule Summary'

class RepaymentTemplateInline(admin.TabularInline):
    model = Contract.repayments.through
    extra = 1

@admin.register(RepaymentTemplate)
class RepaymentTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_variability_display', 'get_amount_display', 'traded_thing', 'timely_action')
    list_filter = ('variability', 'traded_thing__material', 'traded_thing__currency')
    search_fields = ('traded_thing__material__ticker', 'traded_thing__currency__ticker')
    
    def get_amount_display(self, obj):
        if obj.variability == RepaymentTemplate.Variability.FIXED:
            return format_html('<strong>{}</strong>', obj.fixed_amount)
        else:
            return format_html('<em>Variable: {}</em>', obj.variable_amount)
    get_amount_display.short_description = 'Amount'

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('id', 'nominal_price', 'emitter', 'receiver', 'activated', 'get_status')
    list_filter = ('activated', 'emitter', 'receiver')
    search_fields = ('emitter__ticker', 'receiver__ticker')
    readonly_fields = ('activated',)
    filter_horizontal = ('repayments',)
    
    def get_status(self, obj):
        if obj.activated:
            return format_html('<span style="color: green;">Active</span>')
        else:
            return format_html('<span style="color: orange;">Inactive</span>')
    get_status.short_description = 'Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('emitter', 'receiver')

@admin.register(ScheduledPayment)
class ScheduledPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'contract', 'execution_order', 'ts', 'get_amount', 'get_status')
    list_filter = ('was_processed', 'paid', 'missed_payment', 'ts')
    search_fields = ('contract__id', 'contract__emitter__ticker', 'contract__receiver__ticker')
    readonly_fields = ('was_processed', 'paid', 'missed_payment')
    date_hierarchy = 'ts'
    
    def get_amount(self, obj):
        try:
            amount = obj.absolutize_amount()
            return format_html('<strong>{}</strong>', amount)
        except Exception as e:
            return format_html('<span style="color: red;">Error: {}</span>', str(e))
    get_amount.short_description = 'Amount'
    
    def get_status(self, obj):
        if obj.paid:
            return format_html('<span style="color: green;">✓ Paid</span>')
        elif obj.missed_payment:
            return format_html('<span style="color: red;">✗ Missed</span>')
        elif obj.was_processed:
            return format_html('<span style="color: orange;">⚠ Processed</span>')
        else:
            return format_html('<span style="color: blue;">⏳ Pending</span>')
    get_status.short_description = 'Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('contract', 'contract__emitter', 'contract__receiver', 'repayment')