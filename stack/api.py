from django.conf.urls import url
from haystack.query import SearchQuerySet
import logging
from tastypie.authentication import Authentication
from tastypie.authorization import Authorization
from tastypie.cache import SimpleCache
from tastypie.http import HttpResponse
from tastypie.resources import ModelResource, ALL
from tastypie.serializers import Serializer
from tastypie.throttle import CacheThrottle
from tastypie.utils import trailing_slash
from .models import Cadastre

logger = logging.getLogger('caddy')


class CadastreResource(ModelResource):
    class Meta:
        queryset = Cadastre.objects.all()
        authentication = Authentication()  # No-op authentication.
        authorization = Authorization()  # No-op authorization.
        list_allowed_methods = ['get']  # Read-only API.
        detail_allowed_methods = ['get']  # Read-only API.
        filtering = {
            'id': ALL,
            'object_id': ALL,
            'address_nice': ALL,
            'survey_lot': ALL,
            'strata': ALL,
            'reserve': ALL,
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
        """View to allow search of CadastreResources via Haystack.
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
        logger.info('Cadastre geocode query start: {}'.format(q))
        if limit and limit > 0:
            sqs = SearchQuerySet().filter(content=q)[:limit]
        else:
            sqs = SearchQuerySet().filter(content=q)

        if not sqs:
            logger.info('Returning empty cadastre geocode query response')
            return HttpResponse('[]')

        objects = []

        for result in sqs:
            objects.append({
                'object_id': result.object.object_id,
                'address': result.address,
                'lat': result.object.centroid.y,
                'lon': result.object.centroid.x,
                'bounds': list(result.object.envelope.extent),
            })

        self.log_throttled_access(request)
        logger.info('Returning cadastre geocode query response')
        return self.create_response(request, objects)
