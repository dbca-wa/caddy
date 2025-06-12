from django.contrib.gis.admin import GISModelAdmin, register

from .models import Address


@register(Address)
class AddressAdmin(GISModelAdmin):
    actions = None
    fields = ("object_id", "address_nice", "owner", "boundary")
    list_display = (
        "object_id",
        "address_nice",
        "owner",
    )
    readonly_fields = ("object_id", "address_nice", "owner")
    search_fields = ("object_id", "address_nice", "owner")

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        pass

    def response_change(self, request, obj):
        return self.response_post_save_change(request, obj)
