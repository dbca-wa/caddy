from django.conf.urls import url
from django.core.paginator import Paginator, InvalidPage
from django.http import Http404
from shack.models import Address
from tastypie.api import Api
from tastypie.authentication import Authentication
from tastypie.authorization import Authorization
from tastypie.cache import SimpleCache
from tastypie.resources import ModelResource, ALL
from tastypie.serializers import Serializer
from tastypie.throttle import CacheThrottle
from tastypie.utils import trailing_slash

v1_api = Api(api_name='v1')


class AddressResource(ModelResource):
    class Meta:
        queryset = Address.objects.all()
        authentication = Authentication()  # No-op authentication.
        authorization = Authorization()  # No-op authorization.
        list_allowed_methods = ['get']   # Read-only API.
        detail_allowed_methods = ['get']
        excludes = ['cadastre_id', 'search_index', 'address_text']
        filtering = {
            'id': ALL,
            'cadastre_id': ALL,
            'address': ALL,
            'centroid': ALL,
            'envelope': ALL,
        }
        cache = SimpleCache()
        serializer = Serializer(formats=['json', 'jsonp'])
        throttle = CacheThrottle(throttle_at=60, timeframe=60)

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>{})/geocode{}$'.format(
                    self._meta.resource_name, trailing_slash()),
                self.wrap_view('geocode'), name='api_geocode'
            ),
        ]

    def geocode(self, request, **kwargs):
        """Custom view to allow full text search of AddressResource.
        Accepts a query parameter ``q`` containing urlencoded text.
        Returns a custom response (JSON).
        """
        self.method_check(request, allowed=['get'])
        self.throttle_check(request)
        limit = request.GET.get('limit', '')

        try:
            limit = int(limit)
        except ValueError:
            limit = None

        q = request.GET.get('q', '')
        qs = Address.objects.search(q)

        if qs.count() == 0:
            return '[]'

        if limit and limit > 0:
            qs = qs[0:limit]

        objects = []

        for obj in qs:
            objects.append({
                'id': obj.id,
                'address': obj.address_nice,
                'lat': obj.centroid.y,
                'lon': obj.centroid.x,
                'bounds': list(obj.envelope.extent) if obj.envelope else []
            })

        self.log_throttled_access(request)
        return self.create_response(request, objects)

v1_api.register(AddressResource())
