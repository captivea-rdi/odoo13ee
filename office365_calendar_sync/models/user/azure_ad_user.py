# See LICENSE file for full copyright and licensing details.
from datetime import timedelta, datetime

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError

EVENTS_CREATE_DOMAIN = 'calendars/%s/events'
EVENTS_WEBHOOK_CHANGE_TYPE = 'Deleted,Updated,Created'
AZURE_AD_SCOPE_EXPANSION = 'https://outlook.office.com/calendars.readwrite'


class AzureAdUser(models.Model):
    _inherit = 'azure.ad.user'

    calendar_id = fields.Many2one(string='ID of the synced calendar(s)', comodel_name='azure.ad.calendar', ondelete='set null')
    calendar_option_ids = fields.One2many(string='AzureAD Calendar Options', comodel_name='azure.ad.calendar', inverse_name='azure_ad_user_id')
    calendar_ignore_without_category = fields.Boolean(string='Only Sync Calendar Items With Category', default=True)
    calendar_sync_failed = fields.Boolean(string='Calendar sync has failed', default=False)

    @api.one
    def reload_calendar_options(self):
        # Unlink previous options
        self.calendar_option_ids.unlink()

        # Create new options
        self.create_calendar_options()

    # -------------
    # Azure Objects
    # -------------
    def create_calendar_options(self):
        calendars = self.env['azure.ad.calendar'].get_all_calendars(self)

        for cal in calendars:
            self.env['azure.ad.calendar'].create({
                'azure_ad_user_id': self.id,
                'uid': cal['uid'],
                'name': cal['name'],
            })

    # ---------
    # Overrides
    # ---------
    @api.model
    def get_azure_ad_scope(self):
        return super(AzureAdUser, self).get_azure_ad_scope() + ' ' + AZURE_AD_SCOPE_EXPANSION

    @api.model
    def get_updated_link_data(self, method, data):
        r = super(AzureAdUser, self).get_updated_link_data(method, data)

        if method in ['POST'] and 'iCalUId' in data:
            r.update({'ical_uid': data['iCalUId']})

        return r

    @api.one
    def init_webhook(self):
        super(AzureAdUser, self).init_webhook()
        # WEBHOOK Re-enable after json/http logic in controller has been implemented

        # self.azure_ad_subscription_ids.create({
        #     'user_id': self.id,
        #     'resource': CONTACTS_CREATE_DOMAIN,
        #     'change_type': CONTACTS_WEBHOOK_CHANGE_TYPE
        # })

    @api.one
    def init_sync(self):
        r = super(AzureAdUser, self).init_sync()

        self.start_calendar_sync()

        return r

    @api.one
    def start_calendar_sync(self):
        self.remove_unused_calendar_options()

        # Odoo -> Outlook
        # Get all meetings for this user in Odoo between last month and ten years from now.
        min_date = fields.Datetime.to_string(datetime.now() - timedelta(days=30))
        max_date = fields.Datetime.to_string(datetime.now() + timedelta(days=3650))

        meetings_domain = [('start', '>=', min_date), ('start', '<=', max_date), ('partner_ids', 'in', self.partner_id.id)]
        meetings = self.env['calendar.event'].search(meetings_domain)

        meetings.create_link(self.partner_id)

        self.calendar_sync_failed = False

    @api.one
    def validate_fields(self):
        # Checks if calendar exists
        if not self.calendar_id:
            raise ValidationError('%s\n\n%s' % (_('No Outlook Calendar selected'), _('You have not chosen a calendar yet. Please pick a calendar before starting the synchronisation.')))

        # Ensures correct credentials
        super(AzureAdUser, self).validate_fields()

        # Tests if an outlook category has been defined
        if not self.calendar_id.exists_in_azure():
            raise ValidationError('%s\n\n%s' % (_('Outlook Calendar does not exists'), _('The chosen calendar does not exists (anymore). Please pick another calendar before starting the synchronisation.')))

    @api.multi
    def remove_unused_calendar_options(self):
        ids = self.calendar_option_ids.ids

        try:
            ids.remove(self.calendar_id.id)
        except ValueError:
            pass

        self.env['azure.ad.calendar'].browse(ids).unlink()
