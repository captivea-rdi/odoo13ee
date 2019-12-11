# See LICENSE file for full copyright and licensing details.
import traceback

from ..exceptions import *
from odoo import models, fields, api


MAX_PUSH_AMOUNT = 50


class AzureAdPushQueueItem(models.Model):
    _name = 'azure.ad.push.queue.item'
    _description = 'Azure AD Queue Item'

    user_id = fields.Many2one(comodel_name='azure.ad.user', string='User', index=True, required=True, ondelete='cascade')
    data_domain = fields.Char(string="Azure AD Domain")
    data_id = fields.Char(string="Azure AD ID")
    data = fields.Char(string='Data')
    last_error = fields.Char(string='Last Error')
    link = fields.Many2one(comodel_name='azure.ad.user.record.link', string='Record Link')
    headers = fields.Char(string='Extra Applied Headers')
    method = fields.Selection(selection=[
        ('POST', 'POST'),
        ('GET', 'GET'),
        ('DELETE', 'DELETE'),
        ('PATCH', 'PATCH')], required=True)

    status = fields.Selection(selection=[
        ('waiting', 'Awaiting Processing'),
        ('processing', 'Processing'),
        ('cancelled', 'Cancelled'),
        ('processed', 'Processed'),
        ('failed', 'Processing Failed'),
        ('retrying', 'Processing Failed - Awaiting New Attempt')], default='waiting')

    # ---------------------
    # Process Push for User
    # ---------------------
    @api.model
    def process(self, user):
        if isinstance(user, int):
            user = self.env['azure.ad.user'].browse(user)

        # Limit to Office 365 Maximum Request Amount
        queue_items = user.push_queue_item_ids.filtered(lambda i: i.status in ['waiting', 'retrying'])
        queue_items.write({'status': 'processing'})

        processed = 0

        try:
            results = user.batch_request(push_items=queue_items)
        except Exception as e:
            queue_items.write({'status': 'retrying', 'last_error': str(e)})
        else:
            if len(results) != len(queue_items):
                raise Exception("Batch Request Failed, returned result and queue item length does not match!")

            for item, result in zip(queue_items, results):
                try:
                    user.process_response(result)

                    item.unlink()

                    processed += 1
                except (ThrottleError, ServerError, AuthenticationError) as recoverable_error:
                    item.write({'status': 'retrying', 'last_error': recoverable_error.message})
                except Exception as e:
                    item.write({'status': 'failed', 'last_error': str(e)})

        return processed

    # ----------------------
    # Cron Triggered Methods
    # ----------------------
    @api.model
    def process_queue(self):
        queue_users = self.env['azure.ad.user'].search([('push_queue_item_ids', '!=', False), ('azure_ad_sync_started', '=', True)])

        for user in queue_users:
            try:
                self.process(user)
            except Exception:
                traceback.print_exc()
