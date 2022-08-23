from django.contrib.gis.db import models


class CptCadastreScdb(models.Model):
    """This is an auto-generated Django model.
    """
    objectid = models.AutoField(primary_key=True)
    cad_pin = models.IntegerField(blank=True, null=True)
    cad_usage_codes = models.CharField(max_length=12, blank=True, null=True)
    cad_calc_area = models.FloatField(blank=True, null=True)
    cad_cent_latitude = models.FloatField(blank=True, null=True)
    cad_cent_longitude = models.FloatField(blank=True, null=True)
    cad_unit_type = models.CharField(max_length=4, blank=True, null=True)
    cad_level_type = models.CharField(max_length=4, blank=True, null=True)
    cad_level_number = models.CharField(max_length=1, blank=True, null=True)
    cad_address_si = models.CharField(max_length=50, blank=True, null=True)
    cad_lot_number = models.CharField(max_length=6, blank=True, null=True)
    cad_land_type = models.CharField(max_length=5, blank=True, null=True)
    cad_house_number = models.CharField(max_length=7, blank=True, null=True)
    cad_road_name = models.CharField(max_length=50, blank=True, null=True)
    cad_road_type = models.CharField(max_length=4, blank=True, null=True)
    cad_road_suffix = models.CharField(max_length=4, blank=True, null=True)
    cad_locality = models.CharField(max_length=50, blank=True, null=True)
    cad_postcode = models.FloatField(blank=True, null=True)
    cad_pitype_1 = models.CharField(max_length=17, blank=True, null=True)
    cad_pitype_2 = models.CharField(max_length=17, blank=True, null=True)
    cad_pitype_3_1 = models.CharField(max_length=17, blank=True, null=True)
    cad_pitype_3_2 = models.CharField(max_length=54, blank=True, null=True)
    cad_land_name = models.CharField(max_length=17, blank=True, null=True)
    cad_reg_number = models.CharField(max_length=50, blank=True, null=True)
    cad_reg_number_formated = models.CharField(max_length=50, blank=True, null=True)
    cad_owner_name = models.CharField(max_length=500, blank=True, null=True)
    cad_owner_count = models.FloatField(blank=True, null=True)
    cad_sale_date = models.CharField(max_length=10, blank=True, null=True)
    cad_doc_number = models.CharField(max_length=15, blank=True, null=True)
    cad_gprpfx = models.CharField(max_length=30, blank=True, null=True)
    cad_gprsfx = models.CharField(max_length=30, blank=True, null=True)
    cad_strata = models.CharField(max_length=1, blank=True, null=True)
    cad_ownership = models.CharField(max_length=8, blank=True, null=True)
    cad_legend = models.CharField(max_length=50, blank=True, null=True)
    cad_unit_number = models.CharField(max_length=50, blank=True, null=True)
    shape_length = models.FloatField(blank=True, null=True)
    shape_area = models.FloatField(blank=True, null=True)
    shape = models.MultiPolygonField(srid=4283, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cpt_cadastre_scdb'

    def __str__(self):
        return str(self.cad_pin) or 'NULL PIN'
