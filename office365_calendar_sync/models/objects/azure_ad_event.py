# See LICENSE file for full copyright and licensing details.
import json
import re
from datetime import timedelta

from odoo import fields, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

from . import DATETIME_FORMAT


class AzureADEvent:

    def __init__(self, user=None, uid=None, ical_uid=None, link=None, subject=None, body=None, ad_body=None, start_date=None, end_date=None, attendees=None, reminders=None, owner_name=None, owner_email=None, location=None, all_day=False, is_deleted=False, category_removed=False, require_response=True, last_modified=None, attendees_in_body=False, categories=None):
        self.uid = uid
        self.ical_uid = ical_uid
        self.subject = subject
        self.owner_name = owner_name
        self.owner_email = owner_email
        self.start_date = start_date
        self.end_date = end_date
        self.attendees = attendees
        self.reminders = reminders
        self.location = location
        self.all_day = all_day
        self.last_modified = last_modified
        self.body = self.clean_body(ad_body) if ad_body else body
        self.categories = categories or []

        self.user = user
        self.link = link
        self.is_deleted = is_deleted
        self.category_removed = category_removed
        self.require_response = require_response
        self.attendees_in_body = attendees_in_body

    @staticmethod
    def clean_body(body):
        last_match = None

        for m in re.finditer(r'\s*Attendees:.+', body):
            last_match = m

        return body[:last_match.start()] if last_match else body

    @staticmethod
    def form_body(body, attendees):
        if not attendees:
            return body or ''
        else:
            return (body or '') \
                   + '\n\n' \
                   + _('Attendees: ') + ', '.join([('%s (%s)' % (name or '', email or '')) for email, name in attendees.items()]) \
                   + '\n\n' \
                   + _('Synced from a calendar event in Odoo')

    def get_odoo_fields(self, env):
        return {
            'name': self.subject,
            'description': self.body,
            'start': self.start_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            'stop': self.end_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            'allday': self.all_day,
            'location': self.location,
            'outlook_categories': json.dumps(self.categories),
            'partner_ids': [(6, 0, list(set(env['res.partner'].get_partners_with_email(self.attendees).ids)))]
        }

    def get_azure_template(self):
        return {
            'Subject': self.subject or '',
            'Body': {
                'Content': (self.body or '') + '' if not self.attendees_in_body else self.form_body(self.body, self.attendees)
            },
            'Start': {
                'DateTime': self.start_date.strftime(DATETIME_FORMAT),
                'TimeZone': 'UTC',
            },
            'End': {
                'DateTime': self.end_date.strftime(DATETIME_FORMAT),
                'TimeZone': 'UTC',
            },
            'Attendees': [
                {
                    'EmailAddress': {
                        'Address': email or '',
                        'Name': name or '',
                    }
                } for email, name in self.attendees.items()
                ] if self.attendees and not self.attendees_in_body else [],
            "Location": {
                "DisplayName": self.location or '',
            },
            'ResponseRequested': self.require_response,
            'IsAllDay': bool(self.all_day),
            'Categories': self.categories
        }

    @staticmethod
    def get_azure_change_template(change, original):
        if original.outlook_categories:
            r = {'Categories': json.loads(original.outlook_categories)}
        else:
            r = {}

        if 'name' in change:
            r['Subject'] = change['name']
        if 'description' in change:
            if original.from_outlook:
                r['Body'] = {'Content': change['description']}
            else:
                partner_ids = original.env['res.partner'].browse(change['partner_ids'][0][2]) if 'partner_ids' in change else original.partner_ids

                r['Body'] = {'Content': AzureADEvent.form_body(change['description'], {partner.email:  partner.name for partner in partner_ids})}
        if 'start' in change:
            r['Start'] = {
                'DateTime': fields.Datetime.from_string(change['start']).strftime(DATETIME_FORMAT),
                'TimeZone': 'UTC',
            }
        if 'stop' in change:
            r['End'] = {
                'DateTime': ((fields.Datetime.from_string(change['stop']) + timedelta(seconds=1)) if 'allday' in change and change['allday'] or original['allday'] else fields.Datetime.from_string(change['stop'])).strftime(DATETIME_FORMAT),
                'TimeZone': 'UTC',
            }
        if 'allday' in change:
            r['IsAllDay'] = bool(change['allday'])

            if 'Start' not in r:
                r['Start'] = {
                    'DateTime': original.start.replace(hour=0, minute=0, second=0, microsecond=0).strftime(DATETIME_FORMAT) if r['IsAllDay'] else original.start.strftime(DATETIME_FORMAT),
                    'TimeZone': 'UTC',
                }

            if 'End' not in r:
                r['End'] = {
                    'DateTime': (original.stop.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=1)).strftime(DATETIME_FORMAT) if r['IsAllDay'] else (original.stop + timedelta(days=1)).strftime(DATETIME_FORMAT),
                    'TimeZone': 'UTC',
                }
        if 'location' in change:
            r['Location'] = {
                "DisplayName": change['location']
            }
        if 'partner_ids' in change:
            if original.from_outlook:
                r['Attendees'] = [
                    {
                        'EmailAddress': {
                            'Address': partner.email or '',
                            'Name': partner.name or '',
                        }
                    } for partner in original.env['res.partner'].browse(change['partner_ids'][0][2])
                ]
            elif 'description' not in change:
                partner_ids = original.env['res.partner'].browse(change['partner_ids'][0][2])

                r['Body'] = {'Content': AzureADEvent.form_body(original.description, {partner.email:  partner.name for partner in partner_ids})}

        return r

