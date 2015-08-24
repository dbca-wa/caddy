from django.conf.urls import url
from django.core.paginator import Paginator, InvalidPage
from django.http import Http404
from shack.models import Address
from tastypie.api import Api
from tastypie.cache import SimpleCache
from tastypie.resources import ModelResource, ALL
from tastypie.utils import trailing_slash

v1_api = Api(api_name='v1')


class AddressResource(ModelResource):
    class Meta:
        queryset = Address.objects.all()
        list_allowed_methods = ['get']
        detail_allowed_methods = ['get']
        excludes = ['cadastre_id', 'search_index', 'address_text']
        filtering = {
            'id': ALL,
            'cadastre_id': ALL,
            'address': ALL,
            'centroid': ALL,
        }
        cache = SimpleCache()

    def prepend_urls(self):
        return [
            url(
                r'^(?P<resource_name>{})/search{}$'.format(
                    self._meta.resource_name, trailing_slash()),
                self.wrap_view('address_search'), name='api_address_search'
            ),
        ]

    def address_search(self, request, **kwargs):
        """Custom view to allow full text search of AddressResource.
        Accepts a query parameter ``q`` containing urlencoded text.
        """
        self.method_check(request, allowed=['get'])
        self.is_authenticated(request)
        self.throttle_check(request)
        # Do the search query.
        q = request.GET.get('q', '')
        qs = Address.objects.search(q)
        paginator = Paginator(qs, 20)

        try:
            page = paginator.page(int(request.GET.get('page', 1)))
        except InvalidPage:
            raise Http404('No results.')

        objects = []

        for obj in page.object_list:
            bundle = self.build_bundle(obj=obj, request=request)
            bundle = self.full_dehydrate(bundle)
            objects.append(bundle)

        object_list = {'objects': objects}

        self.log_throttled_access(request)
        return self.create_response(request, object_list)

v1_api.register(AddressResource())
