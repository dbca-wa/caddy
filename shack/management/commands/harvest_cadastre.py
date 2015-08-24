from django.core.management.base import BaseCommand, CommandError
from shack.utils import harvest_cadastre


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

            self.stdout.write('Harvesting cadastre addresses.')
            harvest_cadastre(limit)
            self.stdout.write('Finished harvest of cadastre addresses.')

            return
