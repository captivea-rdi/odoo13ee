# See LICENSE file for full copyright and licensing details.
from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def get_partners_with_email(self, emails):
        partner_ids = self.browse()

        emails = emails or {}

        for email, name in emails.items():
            partner_id = self.search(['|', ('email', '=ilike', email), ('azure_ad_user_id.email', '=ilike', email)])

            if partner_id:
                partner_ids += partner_id
            else:
                partner_ids += self.create({'name': name, 'email': email})

        return partner_ids
