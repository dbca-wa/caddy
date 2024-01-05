from django.core.management.base import BaseCommand
import logging
from shack.utils import import_cpt_cadastre_scdb

logger = logging.getLogger('caddy')


class Command(BaseCommand):
    help = 'Undertakes import of address data from the Cadastre Geopackage blob'

    def add_arguments(self, parser):
        parser.add_argument(
            '--blob-name', action='store', dest='blob_name', default='CPT_CADASTRE_SCDB.gpkg',
            help='Blob name (optional)',
        )

    def handle(self, *args, **options):
        if options['blob_name']:
            blob_name = options['blob_name']
        else:
            blob_name = None

        logger.info('Starting import of Cadastre addresses from blob store')
        import_cpt_cadastre_scdb(blob_name)
        self.stdout.write('Finished import of Cadastre addresses')

        return
