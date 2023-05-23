from django.core.management.base import BaseCommand
import logging

from shack.utils import prune_addresses


class Command(BaseCommand):
    help = "Delete any Addresses having an object_id value that doesn't match any current Cadastre object PIN"

    def handle(self, *args, **options):
        logger = logging.getLogger('caddy')
        logger.info('Pruning cadastre addresses')
        prune_addresses()
