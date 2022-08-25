from django.core.management.base import BaseCommand, CommandError
import logging

from cddp.models import CptCadastreScdb
from shack.utils import copy_cddp_cadastre, prune_addresses


class Command(BaseCommand):
    help = 'Undertakes copy of cadastre data from a database connection'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', action='store', dest='limit', default=None,
            help='Limit of the number of results to query/import')

    def handle(self, *args, **options):
        logger = logging.getLogger('caddy')
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
        logger.info('Starting copy of {} cadastre addresses'.format(qs.count()))
        copy_cddp_cadastre(qs)
        logger.info('Finished copy of cadastre addresses')
        prune_addresses()
