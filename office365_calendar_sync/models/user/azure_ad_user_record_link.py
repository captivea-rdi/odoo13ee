# See LICENSE file for full copyright and licensing details.
from odoo import api, models


class AzureAdUserRecordLink(models.Model):
    _inherit = 'azure.ad.user.record.link'

    @api.multi
    def write(self, vals):
        # Check if ical_uid update is necessary
        if 'ical_uid' in vals and self.record.from_outlook:
            self.record.with_context(is_o_value_update=True).write({'outlook_ical_uid': vals['ical_uid']})

        # Remove ical_uid if it exists
        vals.pop('ical_uid', None)

        return super(AzureAdUserRecordLink, self).write(vals)
