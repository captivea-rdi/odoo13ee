# See LICENSE file for full copyright and licensing details.
import json
import re
import traceback
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, logging

from .azure_ad_event import AzureADEvent
from . import DATETIME_FORMAT

_logger = logging.getLogger(__name__)

CALENDARGROUPS_TOP_DOMAIN = 'calendargroups'
CALENDARGROUPS_DATA_DOMAIN = 'calendargroups/%s/calendars'

CALENDARS_CREATE_DOMAIN = 'calendars'
CALENDAR_DATA_DOMAIN = 'calendars/%s'

EVENTS_CREATE_DOMAIN = 'calendars/%s/events'
EVENTS_DATA_DOMAIN = 'events/%s'

CALENDAR_CALENDAR_VIEW_DOMAIN = 'calendars/%s/calendarview'


class AzureADCalendar(models.Model):
    _name = 'azure.ad.calendar'

    azure_ad_user_id = fields.Many2one(string='Azure AD User', comodel_name='azure.ad.user', ondelete='cascade')

    uid = fields.Char(string='Unique Calendar Id')
    name = fields.Char(string='Name')
    delta_token = fields.Char(string='Delta Token')

    @api.one
    def to_azure_ad_template(self):
        return {'Name': self.name}

    @api.multi
    def get_events(self, delta_token=None):
        azure_events, delta_token_new = self.get_events_from_azure(delta_token)
        ignore_without_category = self.azure_ad_user_id.calendar_ignore_without_category

        # Dictionary of SeriesMasters, speeds up lookups
        series_masters = {e['Id']: e for e in azure_events if 'Type' in e and e['Type'] == 'SeriesMaster'}

        events = []

        for event in azure_events:
            # Check if deleted
            if 'reason' in event and event['reason'] == 'deleted':
                events.append(AzureADEvent(user=self, uid=AzureADCalendar.extract_deleted_uid(event['id']), is_deleted=True))
                continue

            # Check if series master, ignore (series master parameters equal the first occurrence)
            if event['Type'] == 'SeriesMaster':
                continue

            # Check type, set event to series master if occurrence
            if event['Type'] == 'Occurrence':
                series_master_id = event['SeriesMasterId']

                # Check if it exists in the current masters list
                if series_master_id in series_masters:
                    master = series_masters[series_master_id]
                # Does not exists, get from server
                else:
                    master = self.azure_ad_user_id.get_data(domain=EVENTS_DATA_DOMAIN, data_id=series_master_id)
            else:
                master = event

            if ignore_without_category and self.azure_ad_user_id.outlook_category not in master['Categories']:
                # Ignore, without category not created in Odoo
                events.append(AzureADEvent(user=self, uid=event['Id'], category_removed=True))
                continue

            attendees = {attendee['EmailAddress']['Address']: attendee['EmailAddress']['Name'] for attendee in master['Attendees']}
            attendees.setdefault(master['Organizer']['EmailAddress']['Address'], master['Organizer']['EmailAddress']['Name'])

            events.append(AzureADEvent(
                # Universal parameters, independent of type
                uid=event['Id'],
                ical_uid=master['iCalUId'],
                user=self.azure_ad_user_id,
                categories=list(set((event['Categories'] or []) + [self.azure_ad_user_id.outlook_category])),
                start_date=datetime.strptime(event['Start']['DateTime'][:19], DATETIME_FORMAT),
                end_date=datetime.strptime(event['End']['DateTime'][:19], DATETIME_FORMAT) - (timedelta(days=1) if master['IsAllDay'] else timedelta()),

                # Additional parameters, after master has been redefined to series master if necessary
                subject=master['Subject'],
                ad_body=master['Body']['Content'],
                owner_name=master['Organizer']['EmailAddress']['Name'],
                owner_email=master['Organizer']['EmailAddress']['Address'],
                attendees=attendees,
                reminders=master['ReminderMinutesBeforeStart'],
                location=master['Location']['DisplayName'],
                all_day=master['IsAllDay'],
                last_modified=master['LastModifiedDateTime']
            ))

        self.delta_token = delta_token_new

        return events

    @api.multi
    def get_events_from_azure(self, delta_token):
        start = datetime.utcnow() - timedelta(days=30)
        end = start + timedelta(days=530)

        params = '?startDateTime=%sZ&endDateTime=%sZ' % (start.strftime(DATETIME_FORMAT), end.strftime(DATETIME_FORMAT)) + ('&$deltaToken=%s' % delta_token if delta_token else '')

        try:
            data = self.azure_ad_user_id.sync_request(domain=(CALENDAR_CALENDAR_VIEW_DOMAIN + params) % self.uid)
        except Exception as e:
            exception_type = e.__class__.__name__

            # Calendar deleted, notify user
            if exception_type == 'NotFoundError':
                user_id = self.azure_ad_user_id

                _logger.warning('User %s (%s) deleted synced calendar' % (user_id.email, user_id))

                user_id.calendar_sync_failed = True
                user_id.last_error = _('Calendar was removed. Please pick another one if you want to restart the syncing.')
                user_id.reload_calendar_options()

            raise e

        return data['value'], AzureADCalendar.extract_delta_token(data['@odata.deltaLink'])

    @api.multi
    def get_changes(self):
        return self.get_events(self.delta_token)

    @api.one
    def sync(self):
        updated_count = 0
        created_count = 0
        deleted_count = 0

        # Get changed events
        changes = self.get_changes()
        ignore_without_category = self.azure_ad_user_id.calendar_ignore_without_category

        for ad_event in changes:
            azure_ad_record_link_obj = self.env['azure.ad.user.record.link'].sudo()

            # Check if already linked
            link = azure_ad_record_link_obj.search([('data_id', '=', ad_event.uid)])
            if link and link.record:
                # Already in Odoo, patch
                if ad_event.is_deleted:
                    if not link.record.outlook_owner_email or (link.record.from_outlook and link.record.outlook_owner_email == self.azure_ad_user_id.email):
                        # Originally created in Odoo and current user is the owner, or no owner defined (created in Odoo), remove record
                        link.record.unlink()
                    else:
                        # Created in Odoo or not the owner of the event or category removed, remove link
                        link.unlink()

                    deleted_count += 1
                elif ad_event.category_removed:
                    links = azure_ad_record_link_obj.search(link.record.get_record_link_domain())

                    # Remove record if this is the only link
                    if len(links) == 1:
                        # Unlink link manually, prevents Outlook object deletion
                        record = link.record
                        link.unlink()
                        record.unlink()
                    # Else just remove the link
                    else:
                        link.unlink()
                else:
                    # iCalUID could have changed if type changed from occurrence to exception, update
                    if link.record.from_outlook and ad_event.ical_uid != link.record.outlook_ical_uid:
                        link.record.write({'outlook_ical_uid': ad_event.ical_uid})

                    # Only patch if syncing from azure 2 odoo
                    if link.sync_type in ['none', 'o2a']:
                        pass
                    else:
                        odoo_fields = ad_event.get_odoo_fields(self.env)

                        # Don't update attendees if it wasn't originally created in Odoo
                        if not link.record.from_outlook:
                            del odoo_fields['partner_ids']

                        patch_fields = link.record.extract_changed(odoo_fields)

                        # Patch
                        if len(patch_fields):
                            patch_fields['last_write'] = ad_event.last_modified

                            link.record.with_context(is_external_change=True).write(patch_fields)

                            updated_count += 1

            # New event for current user
            else:
                if ad_event.is_deleted or (ad_event.category_removed and ignore_without_category):
                    continue

                # Check if event already imported from other user (iCalUId and time will match)
                calendar_event_id = self.env['calendar.event'].search([('outlook_ical_uid', '=', ad_event.ical_uid), ('start', '=', fields.Datetime.to_string(ad_event.start_date)), ('stop', '=', fields.Datetime.to_string(ad_event.end_date))]) if ad_event.ical_uid else False

                if calendar_event_id:
                    # All found ids will point to same record, extract it, create link with current event
                    event_id = calendar_event_id
                else:
                    # Find matching partners based on email address, create those who do not exist
                    partner_ids = self.env['res.partner'].get_partners_with_email(ad_event.attendees)

                    # Create odoo calendar event based on parameters provided by outlook calendar event
                    event_id = self.env['calendar.event'].create({
                        'name': ad_event.subject,
                        'description': ad_event.body,
                        'start': ad_event.start_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                        'stop': ad_event.end_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                        'allday': ad_event.all_day,
                        'location': ad_event.location,
                        'state': 'open',
                        # Casting to set to ensure unique ids only, using array instead of tuple for comparison in extract_changed. Json conversion makes all tuples lists
                        'partner_ids': [[6, 0, list(set(partner_ids.ids))]],
                        'outlook_owner_email': ad_event.owner_email,
                        'from_outlook': True,
                        'outlook_ical_uid': ad_event.ical_uid,
                        'outlook_categories': json.dumps(ad_event.categories)
                    })

                # Create record link
                azure_ad_record_link_obj.create({
                    'user_id': ad_event.user.id,
                    'data_domain': EVENTS_DATA_DOMAIN,
                    'data_id': ad_event.uid,
                    'create_domain': EVENTS_CREATE_DOMAIN % self.uid,
                    'record': 'calendar.event,%s' % event_id.id,
                    'sync_type': 'both' if ad_event.owner_email.lower() == ad_event.user.email.lower() else 'a2o'
                })

                created_count += 1

        return updated_count + created_count + deleted_count

    @api.one
    def create_outlook_event(self, odoo_event, ad_event, link_attendees=True):
        ad_event.attendees_in_body = not link_attendees
        template = ad_event.get_azure_template()

        extra_values = odoo_event.get_extra_custom_values()

        if extra_values:
            template = odoo_event.merge_values(template, extra_values)

        self.env['azure.ad.user.record.link'].sudo().create({
            'user_id': self.azure_ad_user_id.id,
            'data_domain': EVENTS_DATA_DOMAIN,
            'create_domain': EVENTS_CREATE_DOMAIN % self.uid,
            'record': 'calendar.event,%s' % ad_event.uid,
            'data': template,
        })

    @api.one
    def post(self):
        self.uid = self.azure_ad_user_id.post_data(CALENDARS_CREATE_DOMAIN, self.to_azure_ad_template(), force=True)['Id']

    @api.multi
    def exists_in_azure(self):
        domain = CALENDAR_DATA_DOMAIN % self.uid

        try:
            self.azure_ad_user_id.get_data(domain=domain)
        except Exception:
            traceback.print_exc()

            return False
        else:
            return True

    # ------
    #  CRUD
    # ------
    @api.multi
    def unlink(self):
        for calendar in self:
            links = self.env['azure.ad.user.record.link'].sudo().search([('create_domain', 'like', calendar.uid)])

            # Remove record if this user was the creator, otherwise unlink
            for link in links:
                if link.record.from_outlook and link.record.outlook_owner_email == link.user_id.email and link.record:
                    link.record.unlink()
                else:
                    link.unlink()

        return super(AzureADCalendar, self).unlink()

    # ---------
    #  HELPERS
    # ---------
    @staticmethod
    def extract_delta_token(link):
        matches = re.findall(r"deltatoken=(.+?)&.+|deltatoken=(.+)$", link, re.IGNORECASE)

        return matches[0][0] or matches[0][1]

    @staticmethod
    def extract_deleted_uid(uid):
        matches = re.findall(r"CalendarView\('(.+)'\)", uid, re.IGNORECASE)

        return matches[0]

    # -------
    #  MODEL
    # -------
    @api.model
    def get_all_calendars(self, user):
        calendar_groups = self.get_calender_groups(user)
        batch_requests = [user.prepare_batch_request(method="GET", domain=CALENDARGROUPS_DATA_DOMAIN % cg.uid) for cg in calendar_groups]

        calendars = []

        for response in user.batch_request(batch_requests=batch_requests):
            for cal in user.process_response(response)['value']:
                calendars.append({'name': cal['Name'], 'uid': cal['Id']})

        return calendars

    @api.model
    def get_calender_groups(self, user):
        data = user.get_data(CALENDARGROUPS_TOP_DOMAIN)

        groups = []

        for group in data['value']:
            groups.append(AzureADCalendarGroup(name=group['Name'], uid=group['Id'], user=user))

        return groups


class AzureADCalendarGroup:
    def __init__(self, name, uid=None, user=None):
        self.name = name
        self.uid = uid
        self.user = user
