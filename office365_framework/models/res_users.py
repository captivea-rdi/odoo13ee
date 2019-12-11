# See LICENSE file for full copyright and licensing details.
import traceback
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    azure_ad_user_id = fields.One2many(comodel_name='azure.ad.user', string='Azure AD User', inverse_name='partner_id')

    aad_email = fields.Char(string="Azure AD Email", related='azure_ad_user_id.email', readonly=False)
    outlook_category = fields.Char('Outlook Category', related='azure_ad_user_id.outlook_category', readonly=False)
    azure_ad_sync_started = fields.Boolean(string='Synchronisation of Azure', related='azure_ad_user_id.azure_ad_sync_started', readonly=False)
    azure_ad_authentication_failure = fields.Boolean(string='Authentication Failure', related='azure_ad_user_id.authentication_failure', readonly=False)
    azure_ad_last_error = fields.Char(string="Last Error", related='azure_ad_user_id.last_error', readonly=False)
    azure_ad_last_sync = fields.Char(string="Last Sync", related='azure_ad_user_id.last_sync', readonly=False)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # azure_ad_user_id = fields.One2many(string='Azure AD User', related='partner_id.azure_ad_user_id', readonly=False)
    azure_ad_allow_ad_login = fields.Boolean(string='Allow Azure AD login', related='company_id.aad_oauth_enabled', readonly=False)

    def __init__(self, pool, cr):
        """ Override of __init__ to add access rights. Access rights are disabled by default, but allowed
            on some specific fields defined in self.SELF_{READ/WRITE}ABLE_FIELDS.
        """
        init_res = super(ResUsers, self).__init__(pool, cr)

        type(self).SELF_WRITEABLE_FIELDS = list(set(self.SELF_WRITEABLE_FIELDS + ['azure_ad_user_id', 'aad_email', 'outlook_category', 'azure_ad_sync_started', 'azure_ad_authentication_failure', 'azure_ad_last_error', 'azure_ad_last_sync']))

        return init_res

    # ------------------------
    # Azure AD OAuth Actions
    # ------------------------
    @api.multi
    def action_oauth_aad_login(self):
        self.ensure_one()

        if self.azure_ad_user_id and not self.azure_ad_sync_started:
            self.azure_ad_user_id.unlink()

        if not self.azure_ad_user_id:
            self.env['azure.ad.user'].create({
                'oauth_client_id': self.company_id.aad_oauth_client_id,
                'oauth_client_secret': self.company_id.aad_oauth_client_secret,
                'partner_id': self.partner_id.id
            })

        return {
            'type': 'ir.actions.act_url',
            'url': self.azure_ad_user_id.sudo().get_authorize_url(),
            'target': 'self',
            'res_id': self.id,
        }

    @api.multi
    def action_oauth_aad_logout(self):
        self.ensure_one()

        self.azure_ad_user_id.sudo().unlink()

        return self.action_open_preferences()

    @api.multi
    def action_start_sync_azure(self):
        """Starts Syncing"""

        self.ensure_one()

        try:
            self.azure_ad_user_id.validate_fields()
        except ValidationError as v:
            raise v
        except Exception as e:
            raise ValidationError(msg='%s: %s' % (_('Unknown Error'), str(e)))

        self.azure_ad_user_id.sudo().init_sync()

        if self.company_id.aad_enable_webhooks:
            self.azure_ad_user_id.sudo().init_webhook()

        return self.action_open_preferences()

    @api.multi
    def action_sync_azure(self):
        self.sync_azure()

        return self.action_open_preferences()

    @api.multi
    def sync_azure(self):
        updated = {}

        if self.azure_ad_user_id:
            # Pull Changes and apply changes
            updated['pulled'] = self.sudo().env['azure.ad.pull.queue.item'].pull_for_user(self.azure_ad_user_id.id)

            # Process changes
            updated['changed'] = self.sudo().env['azure.ad.change.queue.item'].process_change_for_user(self.azure_ad_user_id.id)

            # Push items for current user
            updated['pushed'] = self.sudo().env['azure.ad.push.queue.item'].process(self.azure_ad_user_id.id)

            self.azure_ad_last_sync = _("Last Sync: %s - pulled %s change(s) from and pushed %s update(s) to Outlook") % (fields.Datetime.to_string(datetime.now()), updated['pulled'], updated['pushed'])

        return updated

    @api.multi
    def action_open_preferences(self):
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'res.users',
            'res_id': self.id,
            'view_id': self.env.ref('base.view_users_form_simple_modif').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    # ----------------------
    # Azure AD Setup Logic
    # ----------------------
    @api.multi
    def aad_setup(self):
        """Runs after user connects Azure AD Account (Office 365, Outlook, etc.)"""

        self.ensure_one()

        try:
            self.azure_ad_user_id.sudo().set_refresh_token()
        except Exception:
            traceback.print_exc()
