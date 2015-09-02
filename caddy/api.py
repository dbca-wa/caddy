from shack.api import AddressResource
#from stack.api import CadastreResource
from tastypie.api import Api

v1_api = Api(api_name='v1')
v1_api.register(AddressResource())
#v1_api.register(CadastreResource())
