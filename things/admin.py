from django.contrib import admin

from things.models import Thing, Material, Currency

# Register your models here.

admin.site.register(Material)
admin.site.register(Currency)
admin.site.register(Thing)
