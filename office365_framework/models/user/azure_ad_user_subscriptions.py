# See LICENSE file for full copyright and licensing details.
from odoo import fields, api, models

SUBSCRIPTION_DATA_DOMAIN = 'subscriptions/%s'
SUBSCRIPTION_CREATE_DOMAIN = 'subscriptions'


class AzureAdUserSubscription(models.Model):
    _name = 'azure.ad.user.subscription'

    user_id = fields.Many2one(string='Azure AD User', comodel_name='azure.ad.user', ondelete='cascade')
    subscription_id = fields.Char(string='Outlook Push Notification ID')
    resource = fields.Char(string='Outlook Push Notification Resource')
    change_type = fields.Char(string='Outlook Push Notification Change Types')

    @api.model
    def process_subscription_renewal(self):
        subscriptions = self.search([])

        for sub in subscriptions:
            # WEBHOOK Logic for exceptions
            # If subscription does not exist it should be recreated
            # What is user authentication timed out?
            # Logic if subscription timed out
            sub.user_id.patch_data(domain=SUBSCRIPTION_DATA_DOMAIN, data_id=sub.subscription_id, data={'@odata.type': '#Microsoft.OutlookServices.PushSubscription'})

    @api.model
    def create(self, vals):
        self.env['azure.ad.user'].browse([vals['user_id']]).azure_ad_subscription_ids.filtered(lambda r: r.resource == vals['resource'] and r.change_type == vals['change_type']).unlink()

        res = super(AzureAdUserSubscription, self).create(vals)

        res.user_id.security_code = self.user_id.get_secret()

        params = {
            "@odata.type": "#Microsoft.OutlookServices.PushSubscription",
            "Resource": "https://outlook.office.com/api/v2.0/me/" + res.resource,
            "NotificationURL": res.user_id.get_webhook_url(),
            "ChangeType": res.change_type,
            "ClientState": res.user_id.security_code
        }

        res.subscription_id = res.user_id.post_data(domain=SUBSCRIPTION_CREATE_DOMAIN, data=params, force=True)['Id']

        return res

    @api.multi
    def unlink(self):
        for sub in self:
            try:
                sub.user_id.delete_data(domain=SUBSCRIPTION_DATA_DOMAIN, data_id=sub.subscription_id, force=True)
            except:
                pass

        return super(AzureAdUserSubscription, self).unlink()
