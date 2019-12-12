# See LICENSE file for full copyright and licensing details.
import json
import traceback
from datetime import timedelta

from odoo import models, fields, api, _, SUPERUSER_ID
from odoo.exceptions import UserError

from .objects.azure_ad_event import AzureADEvent


class CalendarEvent(models.Model):
    _name = 'calendar.event'
    _inherit = ['calendar.event', 'azure.ad.change.queuer']

    # Outlook owner is char field instead of direct reference to azure users, because it is not necessarily created by a user in Odoo
    outlook_ical_uid = fields.Char(string='Outlook unique iCalUID')
    outlook_owner_email = fields.Char(string='Owner of the event in Outlook')
    from_outlook = fields.Boolean(string='Created from an event in Outlook')

    outlook_categories = fields.Char('Categories from Outlook')

    
    def write(self, vals):
        # Check if from outlook, prevent changes if original user not logged in
        if len(self) == 1 and self.from_outlook and self.outlook_owner_email:
            record_link_ids = self.env['azure.ad.user.record.link'].sudo().search(self.get_record_link_domain())

            # If not superuser, and record link does not exists with owner email
            #if self.env.user.id != SUPERUSER_ID and len([r for r in record_link_ids if r.user_id.email == self.outlook_owner_email]) != 1:
            #    raise UserError(_('The event can not be changed because it has been created in Outlook, and the original owner has not synced the item.'))

        removed_partners = []
        added_partners = []

        # Calculate Removed Partners
        if 'partner_ids' in (vals or {}):
            original_partners = set(self.partner_ids.ids)
            new_partners = set(vals['partner_ids'][0][2])

            removed_partners = original_partners - new_partners
            added_partners = new_partners - original_partners

        # Fix for stop/start values being processed twice, probably onchange
        if not self._context.get('is_change_push'):
            if len(vals) == 1:
                if 'stop' in vals or 'start' in vals:
                    return self

        res = super(CalendarEvent, self).write(vals)

        # If recurrent rule has changed, links need to recreate, no need to check added or removed partners
        if 'rrule' in (vals or {}):
            # Recurrence Rule changed
            for event in self:
                virtual_ids = event.get_recurrent_ids([])
                link_ids = event.get_links()
                linked_record_ids = [link.record.id for link in link_ids]

                should_remove_links = [link for link in link_ids if link.record.id not in virtual_ids]
                should_create_ids = [record_id for record_id in virtual_ids if record_id not in linked_record_ids]

                for link in should_remove_links:
                    link.delete()

                for record in should_create_ids:
                    self.browse(record).create_link()
        else:
            for event in self:
                if added_partners:
                    self.create_link(self.env['res.partner'].browse(added_partners))
                if removed_partners:
                    link_ids = event.get_links()
                    should_remove_links = [link for link in link_ids if link.user_id.partner_id in removed_partners]

                    for link in should_remove_links:
                        link.delete()

        return res

    @api.model
    def create(self, vals):
        # Check origin of event
        from_outlook = 'from_outlook' in vals and vals['from_outlook']

        res = super(CalendarEvent, self).create(vals)

        # Event has been created in Odoo, make event in Outlook, link
        if not from_outlook:
            self.browse(res.get_recurrent_ids([])).create_link()

        return res

    def create_link(self, partner_id=None):
        for record in self:
            # Make eventTemplate
            ad_event = AzureADEvent(
                uid=record.id,
                subject=record.name,
                body=record.description,
                start_date=record.start,
                end_date=record.stop if not record.allday else (record.stop + timedelta(days=1)),
                all_day=record.allday,
                location=record.location,
                attendees={p.email: p.name for p in record.sudo().partner_ids},
                require_response=False,
                categories=json.loads(record.outlook_categories) if record.outlook_categories else [],
            )
    
            to_sync = partner_id or record.sudo().partner_ids
    
            for partner in to_sync:
                # TODO Check if link exists
                azure_ad_user_id = partner.sudo().azure_ad_user_id
    
                if azure_ad_user_id:
                    # No link yet
                    if not azure_ad_user_id.record_link_ids.filtered(lambda r: r.record._name == record._name and r.record.id == record.id):
                        try:
                            ad_event.categories = list(set(ad_event.categories + [azure_ad_user_id.outlook_category]))
    
                            azure_ad_user_id.calendar_id.create_outlook_event(record, ad_event, link_attendees=False)
                        except Exception:
                            traceback.print_exc()

    # ---------
    # Overrides
    # ---------
    
    def detach_recurring_event(self, values=None):
        res = super(CalendarEvent, self).detach_recurring_event(values=values)

        # Remove link with virtual event, real event and its links will have been created by super
        self.remove_links()

        return res

    
    def unlink(self, can_be_deleted=True):
        self.remove_links()

        return super(CalendarEvent, self).unlink(can_be_deleted)

    # ------------------
    # Abstract Overrides
    # ------------------
    
    def prepare_azure_ad_template(self, change, is_child=False):
        return AzureADEvent.get_azure_change_template(change, self)

    @api.model
    def get_change_observed_values(self):
        return ['id', 'name', 'description', 'start', 'stop', 'allday', 'location', 'partner_ids', 'outlook_categories']

    
    def get_record_link_domain(self):
        return ['|', ('record', '=', '%s,%s' % (self._name, self.id)), ('record', '=like', '%s,%s-%%' % (self._name, self.id))]
