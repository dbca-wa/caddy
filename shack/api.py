from django.conf.urls import url
from tastypie.authentication import Authentication
from tastypie.authorization import Authorization
from tastypie.cache import SimpleCache
from tastypie.http import HttpResponse
from tastypie.resources import ModelResource, ALL
from tastypie.serializers import Serializer
from tastypie.throttle import CacheThrottle
from tastypie.utils import trailing_slash
from .models import Address


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
        if not q:
            return HttpResponse('[]')

        # This is to allow for partial address searching
        words = []
        for word in q.split():
            try:
                int(word)
                words.append(word)
            except:
                words.append(word+':*')
        words = ' & '.join(words)

        # Partial address searching
        raw_query = "SELECT * FROM shack_address WHERE tsv @@ to_tsquery('{}')".format(words)

        if limit and limit > 0:
            # Note qs is a RawQuerySet, hence we evaluate it here.
            qs = Address.objects.raw(raw_query)[:limit]
        else:
            qs = Address.objects.raw(raw_query)[:]

        if len(qs) == 0:
            return HttpResponse('[]')

        objects = []

        for obj in qs:
            objects.append({
                'id': obj.pk,
                'address': obj.address_nice,
                'lat': obj.centroid.y,
                'lon': obj.centroid.x,
                'bounds': list(obj.envelope.extent) if obj.envelope else []
            })

        self.log_throttled_access(request)
        return self.create_response(request, objects)
