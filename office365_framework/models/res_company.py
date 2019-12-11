# See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    aad_oauth_enabled = fields.Boolean(string='Allow users to connect with Office 365', compute='_compute_aad_values', inverse='_set_aad_values', readonly=False)
    aad_enable_webhooks = fields.Boolean(string='Enable WebHooks', compute='_compute_aad_values', inverse='_set_aad_values')
    aad_oauth_client_id = fields.Char(string='Application Id', compute='_compute_aad_values', inverse='_set_aad_values')
    aad_oauth_client_secret = fields.Char(string='Password', compute='_compute_aad_values', inverse='_set_aad_values')

    @api.one
    def _set_aad_values(self):
        config = self.env['ir.config_parameter'].sudo()

        config.set_param('office365.oauth.enabled', self.aad_oauth_enabled)
        config.set_param('office365.webhooks.enabled', self.aad_enable_webhooks)
        config.set_param('office365.oauth.client.id', self.aad_oauth_client_id)
        config.set_param('office365.oauth.client.secret', self.aad_oauth_client_secret)

    def _compute_aad_values(self):
        config = self.env['ir.config_parameter'].sudo()

        for company in self:
            company.aad_oauth_enabled = config.get_param('office365.oauth.enabled', False)
            company.aad_enable_webhooks = config.get_param('office365.webhooks.enabled', False)
            company.aad_oauth_client_id = config.get_param('office365.oauth.client.id', False)
            company.aad_oauth_client_secret = config.get_param('office365.oauth.client.secret', False)

    def write(self, vals):
        to_update = []

        for company in self:
            if 'aad_enable_webhooks' in vals and vals['aad_enable_webhooks'] != company.aad_enable_webhooks:
                to_update.append(company)

        res = super(ResCompany, self).write(vals)

        for company in to_update:
            if company.aad_enable_webhooks:
                self.env['azure.ad.user'].search([]).init_webhook()
            else:
                self.env['azure.ad.user'].search([]).remove_webhook()

        return res

    @api.onchange('aad_oauth_enabled')
    def onchange_aad_oauth_enabled(self):
        if not self.aad_oauth_enabled:
            self.env['azure.ad.user'].unlink()
