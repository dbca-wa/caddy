from shack.api import AddressResource
from tastypie.api import Api

v1_api = Api(api_name='v1')
v1_api.register(AddressResource())
