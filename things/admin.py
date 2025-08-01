from django.contrib import admin

from things.models import Thing, Material, Currency, Ownership

# Register your models here.

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('ticker', 'full_name')
    search_fields = ('ticker', 'full_name')

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('ticker', 'full_name')
    search_fields = ('ticker', 'full_name')

@admin.register(Thing)
class ThingAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_name', 'get_ticker', 'get_type')
    list_filter = ('material', 'currency', 'contract')
    search_fields = ('material__ticker', 'currency__ticker', 'contract__id')
    
    def get_name(self, obj):
        if obj.material:
            return obj.material.full_name
        elif obj.currency:
            return obj.currency.full_name
        elif obj.contract:
            return f"Contract {obj.contract.id}"
        return "Unknown"
    get_name.short_description = 'Name'
    
    def get_ticker(self, obj):
        if obj.material:
            return obj.material.ticker
        elif obj.currency:
            return obj.currency.ticker
        elif obj.contract:
            return f"C{obj.contract.id}"
        return "?"
    get_ticker.short_description = 'Ticker'
    
    def get_type(self, obj):
        if obj.material:
            return "Material"
        elif obj.currency:
            return "Currency"
        elif obj.contract:
            return "Contract"
        return "Unknown"
    get_type.short_description = 'Type'

@admin.register(Ownership)
class OwnershipAdmin(admin.ModelAdmin):
    list_display = ('corporation', 'thing', 'amount')
    list_filter = ('thing__material', 'thing__currency')
    search_fields = ('corporation__ticker', 'corporation__full_name')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('corporation', 'thing', 'thing__material', 'thing__currency')
