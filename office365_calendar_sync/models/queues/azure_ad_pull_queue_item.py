# See LICENSE file for full copyright and licensing details.
import logging
import traceback

from odoo import api, models

_logger = logging.getLogger(__name__)


class AzureAdPullQueueItem(models.Model):
    _inherit = 'azure.ad.pull.queue.item'

    # ---------
    # Overrides
    # ---------
    @api.one
    def process(self, updated=0):
        if self.domain == 'calendar' or not self.domain:
            try:
                updated += sum(self.user_id.calendar_id.sync())
            except Exception:
                # Exception normally catched higher

                traceback.print_exc()

        return super(AzureAdPullQueueItem, self).process(updated)
