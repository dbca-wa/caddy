from django.core.management.base import BaseCommand, CommandError
from shack.utils import copy_cddp_cadastre
from cddp.models import CptCadastreScdb


class Command(BaseCommand):
    help = 'Undertakes copy of cadastre data from a database connection'

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

        qs = CptCadastreScdb.objects.all()
        if limit:
            qs = qs[0:limit]
        self.stdout.write('Starting copy of {} cadastre addresses'.format(qs.count()))
        copy_cddp_cadastre(qs)
        self.stdout.write('Finished copy of cadastre addresses')
