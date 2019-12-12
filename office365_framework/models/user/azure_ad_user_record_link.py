# See LICENSE file for full copyright and licensing details.
import json
import logging

from odoo import fields, models, api

from odoo.fields import Reference

_logger = logging.getLogger(__name__)


class AzureAdUserRecordLink(models.Model):
    _name = 'azure.ad.user.record.link'

    user_id = fields.Many2one(comodel_name='azure.ad.user', string='Azure AD User', required=True, ondelete='cascade')
    data_domain = fields.Char(string="Azure AD Access Domain")
    data_id = fields.Char(string="Azure AD ID")
    create_domain = fields.Char(string="Azure AD Create Domain")
    push_queue_ids = fields.One2many(comodel_name='azure.ad.push.queue.item', string='Push Queue Items', inverse_name='link')
    record = Reference(string="Reference", selection='_select_objects')
    sync_type = fields.Selection(string="Sync Way", default='both', selection=[
        ('both', 'Odoo <-> Azure'),
        ('o2a',  'Odoo --> Azure'),
        ('a2o',  'Odoo <-- Azure'),
        ('none', 'Odoo -/- Azure (Handled by other link)'),
    ])

    @api.model
    def _select_objects(self):
        records = self.env['ir.model'].search([])
        return [(record.model, record.name) for record in records] + [('', '')]

    def patch(self, change):
        if not change:
            return

        for link in self:
            # If link only syncs from Azure to Odoo, don't patch
            if link.sync_type in ['none', 'a2o']:
                continue

            prev = self.env['azure.ad.push.queue.item'].search([('link', '=', link.id), ('status', 'in', ['waiting', 'retrying']), ('method', 'in', ['PATCH', 'POST', 'DELETE'])])

            if prev and prev[0].method in ['POST', 'PATCH']:
                # Merge multilevel dictionaries
                prev.data = json.dumps(self.merge(json.loads(prev[0].data), change))
            elif prev and prev[0].method == 'DELETE':
                return False
            else:
                link.user_id.patch_data(domain=link.data_domain, data_id=link.data_id, data=change, link=link)

    @api.model
    def create(self, vals):
        data = vals.pop('data') if 'data' in vals else None

        res = self.search([('record', '=', vals['record']), ('user_id', '=', vals['user_id'])])

        if not res:
            res = super(AzureAdUserRecordLink, self).create(vals)

            if not res.data_id:
                res.user_id.post_data(domain=res.create_domain, data=data, link=res)
            else:
                res.patch(data)

            _logger.info('Created new record link for user %s: %s' % (res.user_id, res.id))
        else:
            res.write(vals)

        return res

    def delete(self):
        for link in self:
            # If link only syncs from azure to odoo, remove it without deleting data in azure
            if link.sync_type == 'a2o':
                link.unlink()
            else:
                # Remove pushes in queue
                link.push_queue_ids.unlink()
                # Make a deletion request
                link.user_id.delete_data(domain=link.data_domain, data_id=link.data_id, link=link)

    # -------
    # HELPERS
    # -------
    def merge(self, data_1, data_2):
        """Merges dictionaries with sub arrays, works recursively"""
        try:
            data = {}

            # Loop over first dict, if key in both dict merge, else set value
            for key, value in data_1.items():
                if key in data_2:
                    if key == 'Categories':
                        data[key] = list(set(value + data_2[key]))
                    else:
                        data[key] = self.merge(value, data_2[key])
                else:
                    data[key] = value

            # Loop over second dict, if key not in return yet, add it
            for key, value in data_2.items():
                if key not in data:
                    data[key] = value

            return data
        except AttributeError:
            pass

        # Wasn't a dictionary, could be array with dictionary, only care about first result
        try:
            if type(data_1) is list:
                if data_1 and not data_2:
                    return data_1
                elif data_2 and not data_1:
                    return data_2
                elif len(data_1) > 0 and len(data_2) > 0:
                    return [self.merge(data_1[0], data_2[0])]
                else:
                    return []
        except (TypeError, AttributeError):
            pass

        # Not a dictionary nor was it a dictionary embedded in array, return value that isn't False, data_2 get's priority
        if data_1 and not data_2:
            return data_1
        else:
            return data_2

