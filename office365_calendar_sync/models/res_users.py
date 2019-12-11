# See LICENSE file for full copyright and licensing details.
from odoo import models, api, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    azure_ad_calendar_id = fields.Many2one(string='Outlook Calendar', comodel_name='azure.ad.calendar', related='azure_ad_user_id.calendar_id', readonly=False)
    azure_ad_calendar_ignore_without_category = fields.Boolean(string='Only Sync Calendar Items With Category', related='azure_ad_user_id.calendar_ignore_without_category', readonly=False)
    azure_ad_calendar_sync_failed = fields.Boolean(string='Calendar Sync Has Failed', related='azure_ad_user_id.calendar_sync_failed', readonly=False)

    @api.multi
    def action_reload_calendars(self):
        self.ensure_one()

        self.azure_ad_user_id.reload_calendar_options()

        return {
            'type': 'ir.actions.act_do_nothing'
        }

    @api.multi
    def action_start_calendar_sync(self):
        self.azure_ad_user_id.validate_fields()
        self.azure_ad_user_id.start_calendar_sync()

        self.azure_ad_user_id.last_error = ''
        self.action_sync_azure()

    # -----------------------
    # Azure AD Setup Override
    # -----------------------
    @api.multi
    def aad_setup(self):
        res = super(ResUsers, self).aad_setup()

        if not self.azure_ad_calendar_id and not self.azure_ad_user_id.authentication_failure:
            self.azure_ad_user_id.reload_calendar_options()

        return res

    # ---------
    # Overrides
    # ---------
    def __init__(self, pool, cr):
        """ Override of __init__ to add access rights. Access rights are disabled by default, but allowed
            on some specific fields defined in self.SELF_{READ/WRITE}ABLE_FIELDS.
        """
        init_res = super(ResUsers, self).__init__(pool, cr)

        type(self).SELF_WRITEABLE_FIELDS = list(set(self.SELF_WRITEABLE_FIELDS + ['azure_ad_calendar_id', 'azure_ad_calendar_ignore_without_category']))

        return init_res