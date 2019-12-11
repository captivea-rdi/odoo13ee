# See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    aad_oauth_enabled = fields.Boolean(related="company_id.aad_oauth_enabled", string='Allow users to connect Odoo with Office 365', readonly=False)
    aad_enable_webhooks = fields.Boolean(related="company_id.aad_enable_webhooks", string='Enable WebHooks', help='Enables usage of WebHooks for efficiency, requires public DNS address', readonly=False)
    aad_oauth_client_id = fields.Char(related="company_id.aad_oauth_client_id", string='Client ID', help="Client ID of the registered app on https://apps.dev.microsoft.com", readonly=False)
    aad_oauth_client_secret = fields.Char(related="company_id.aad_oauth_client_secret", string='Client Secret', help="Password type Application Secret of the registered app on https://apps.dev.microsoft.com", readonly=False)
