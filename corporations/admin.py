from django.contrib import admin

from corporations.models import Corporation, TransactionLog

# Register your models here.

@admin.register(Corporation)
class CorporationAdmin(admin.ModelAdmin):
    list_display = ('ticker', 'full_name', 'bankrupt')
    list_filter = ('bankrupt',)
    search_fields = ('ticker', 'full_name')
    readonly_fields = ('bankrupt',)
    
    def get_queryset(self, request):
        return super().get_queryset(request)

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'giver', 'taker', 'thing', 'amount_scheduled', 'amount_actually_given', 'causal')
    list_filter = ('timestamp', 'causal', 'thing')
    search_fields = ('giver__ticker', 'taker__ticker', 'causal')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('giver', 'taker', 'thing')