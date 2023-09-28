from django.core.management.base import BaseCommand, CommandError
import logging
from shack.utils import import_cpt_cadastre_scdb

logger = logging.getLogger('caddy')


class Command(BaseCommand):
    help = 'Undertakes harvest of address data from CPT_CADASTRE_SCDB.gpkg'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path', action='store', dest='path', default=None,
            help='File path to the Geopackage file',
        )

    def handle(self, *args, **options):
        if options['path']:
            path = options['path']
        else:
            path = None

        logger.info('Starting harvest of cadastre addresses')
        import_cpt_cadastre_scdb(path)
        self.stdout.write('Finished harvest of cadastre addresses')

        return
