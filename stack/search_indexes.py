from haystack import indexes
from stack.models import Cadastre


class CadastreIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    address = indexes.CharField(model_attr='address_nice')
    geocode_json = indexes.CharField(use_template=True, indexed=False)

    def get_model(self):
        return Cadastre
