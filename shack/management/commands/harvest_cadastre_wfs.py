from django.core.management.base import BaseCommand, CommandError
import logging
from shack.utils import harvest_cadastre_wfs

logger = logging.getLogger('caddy')


class Command(BaseCommand):
    help = 'Undertakes harvest of address data from cadastre WFS'

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
            if limit < 0:
                raise CommandError('Limit must be zero or greater')
        else:
            limit = None

        self.stdout.write('Starting harvest of cadastre addresses')
        logger.info('Starting harvest of cadastre addresses')
        summary = harvest_cadastre_wfs(limit)
        self.stdout.write(
            'Harvest complete: {created} created, {updated} updated, '
            '{skipped} skipped, {suspect} suspect'.format(**summary)
        )
        logger.info('Finished harvest of cadastre addresses')

        return
