# See LICENSE file for full copyright and licensing details.
import json

from odoo import models, fields, api


class AzureAdChangeQueueItem(models.Model):
    _name = 'azure.ad.change.queue.item'
    _description = 'Azure AD Change Queue Item'

    change = fields.Char(string='Change, JSON Object')
    time = fields.Datetime(string='Change DateTime')
    record = fields.Reference(string="Reference", selection='_select_objects')
    user_id = fields.Many2one(comodel_name='azure.ad.user', string='User', ondelete='cascade')

    status = fields.Selection(selection=[
        ('waiting', 'Awaiting Processing'),
        ('processing', 'Processing')],
        default='waiting')

    # -------------------
    # Reference Selection
    # -------------------
    @api.model
    def _select_objects(self):
        records = self.env['ir.model'].search([])
        return [(record.model, record.name) for record in records] + [('', '')]

    # ---------
    # Overrides
    # ---------
    def create(self, vals):
        return super(AzureAdChangeQueueItem, self).create(vals)

    # ---------------------
    # Process Push for User
    # ---------------------
    def process_change_for_user(self, user_id):
        # Get records that the user is subscribed to
        links = self.env['azure.ad.user'].browse(user_id).record_link_ids

        record_changes = {}

        # Get changes for individual records
        for link in links:
            if link.record:
                changes = self.search(['&', ('status', '!=', 'processing'), ('record', '=', '%s,%s' % (link.record._name, link.record.id))])

                if changes:
                    record_changes[link.record] = changes
                    record_changes[link.record].write({'status': 'processing'})

        # Process those changes
        for record, changes in record_changes.items():
            self.process_record_changes(record, changes)

        return len(record_changes)

    # -------------------------
    # Process Change for Record
    # -------------------------
    @api.model
    def process_record_changes(self, record, changes):
        last_write = record['change_last_write']
        new_last_write = None
        field_changes = {}

        for change in changes:
            fields_in_change = json.loads(change.change)
            change_time = change.time

            for name, value in fields_in_change.items():
                # Last change wins

                # Check if change time of field is not smaller than last write time, and bigger than last change time of field in current dictionary
                if not (name in field_changes and last_write and field_changes[name][1] > change_time and change_time < last_write):
                    field_changes[name] = (value, change_time)

                    if not new_last_write or new_last_write < change_time:
                        new_last_write = change_time

            change.unlink()

        if field_changes:
            record.with_context(is_change_push=True).write({k: v[0] for k, v in field_changes.items()})

    # -----------------
    # Triggered Methods
    # -----------------
    @api.model
    def process_queue(self):
        queue_items = self.search([('status', '!=', 'processing')])
        queue_items.write({'status': 'processing'})

        record_changes = {}

        for item in queue_items:
            record_changes.setdefault(item.record, [])
            record_changes[item.record].append(item)

        for record, changes in record_changes.items():
            self.process_record_changes(record, changes)
