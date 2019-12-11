# See LICENSE file for full copyright and licensing details.
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AzureAdPullQueueItem(models.Model):
    _name = 'azure.ad.pull.queue.item'
    _description = 'Azure AD Users to Pull'

    user_id = fields.Many2one(comodel_name='azure.ad.user', string='User', index=True, required=True, ondelete='cascade')
    last_error = fields.Char(string='Last Error')
    domain = fields.Char(string='Changed Domain')

    status = fields.Selection(selection=[
        ('waiting', 'Awaiting Pull'),
        ('pulling', 'Pulling Deltas'),
        ('failed', 'Pull Failed')], default='waiting')

    # ----------------
    # Queue Processing
    # ----------------
    @api.one
    def process(self, updated=0):
        """Method that get's triggered with cron jobs. Should be overridden in other modules"""

        if self.status != 'failed':
            self.unlink()

        return updated

    # ----------------------
    # Cron Triggered Methods
    # ----------------------
    @api.model
    def pull_for_user(self, user_id):
        """Pulls changes from outlook for a specified AzureAdUser. Returns the amount of items changed."""
        res = self.search([('user_id', '=', user_id)])

        if len(res) == 0:
            res = self.create({'user_id': user_id})

        if res.status != 'pulling':
            res.write({'status': 'pulling'})

            processed = res.process()

            try:
                return sum([sum(u) for u in processed])
            except TypeError:
                pass

        return 0

    @api.model
    def process_queue(self):
        """Pulls and processes the delta's for the users in the list"""

        # WEBHOOK Lock

        queue_items = self.search([])
        queue_items.write({'status': 'pulling'})
        queue_items.process()

        # WEBHOOK Unlock

        # After all deltas have been received, process them
        self.env['azure.ad.change.queue.item'].sudo().process_queue()

    @api.model
    def process_for_all_users(self):
        users = self.env['azure.ad.user'].search([('azure_ad_sync_started', '=', True)])

        for user in users:
            self.create({'user_id': user.id})

        self.process_queue()
