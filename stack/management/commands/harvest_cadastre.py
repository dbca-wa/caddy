from django.core.management.base import BaseCommand, CommandError
import logging
from stack.utils import harvest_cadastre

logger = logging.getLogger('caddy')


class Command(BaseCommand):
    help = 'Undertakes harvest of data from cadastre WFS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', action='store', dest='limit', default=None,
            help='Limit of the number of results to query/import')

    def handle(self, *args, **options):
        if options['limit']:
            try:
                limit = int(options['limit'])
            except ValueError:
                raise CommandError('Invalid limit value: {}'.format(options['limit']))
        else:
            limit = None

        self.stdout.write('Starting harvest of cadastre objects')
        logger.info('Starting harvest of cadastre objects')
        harvest_cadastre(limit)
        self.stdout.write('Finished harvest of cadastre objects')
        logger.info('Finished harvest of cadastre objects')

        return
