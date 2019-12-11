# See LICENSE file for full copyright and licensing details.
import base64
import hashlib
import json
import re
import time
import traceback
import uuid
from random import random

import requests
import werkzeug

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from ..exceptions import *

AZURE_AD_AUTH_ENDPOINT = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
AZURE_AD_TOKEN_ENDPOINT = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
AZURE_AD_SCOPE = 'openid offline_access profile email'
OUTLOOK_ENDPOINT = 'https://outlook.office.com/api/v2.0/me/'

_logger = logging.getLogger(__name__)


class AzureAdUser(models.Model):
    _name = 'azure.ad.user'

    oauth_client_id = fields.Char(string="Application Id")
    oauth_client_secret = fields.Char(string="Password")

    security_code = fields.Char(string="Security Code for OAuth Request")
    authentication_code = fields.Char(string="Oauth Authentication Code")
    authentication_failure = fields.Boolean(string='Authentication Failure', default=False)

    last_sync = fields.Char(string="Last Sync")
    last_error = fields.Char(string="Last Error")

    id_token = fields.Char(string="ID Token")
    access_token = fields.Char(string="Access Token")
    refresh_token = fields.Char(string="Refresh Token")

    email = fields.Char(string="Email")
    outlook_category = fields.Char('Outlook Category Name', default="Odoo")
    azure_ad_sync_started = fields.Boolean(string='Synchronisation of Outlook')
    record_link_ids = fields.One2many(comodel_name='azure.ad.user.record.link', inverse_name='user_id', string='Azure AD Record Links')
    azure_ad_subscription_ids = fields.One2many(comodel_name='azure.ad.user.subscription', inverse_name='user_id', string='Azure AD Subscriptions')

    push_queue_item_ids = fields.One2many(comodel_name='azure.ad.push.queue.item', inverse_name='user_id', string='Azure AD Push Queue Items')
    pull_queue_item_ids = fields.One2many(comodel_name='azure.ad.pull.queue.item', inverse_name='user_id', string='Azure AD Pull Queue Items')

    partner_id = fields.Many2one(comodel_name='res.partner', string='Odoo User', ondelete='cascade')

    # -----------
    # Token Logic
    # -----------
    def set_refresh_token(self):
        """Sets the Refresh Token for an Azure AD OAuth Login"""

        self.set_token('authorization_code', 'code', self.authentication_code)

    def set_access_token(self):
        """Sets the Access Token for an Azure AD OAuth Login"""

        self.set_token('refresh_token', 'refresh_token', self.refresh_token)

    def set_token(self, grant_type, code_type, code):
        """Sets the Tokens for an Azure AD OAuth Login"""
        self.ensure_one()

        try:
            response = self.get_token(grant_type, code_type, code)
        except Exception as e:
            _logger.warning('GetToken - Authentication failure for user %s: %s' % (self.id, str(e)))

            try:
                if json.loads(str(e)[3:])['error'] == 'invalid_client':
                    self.last_error = 'Contact your Administrator with the following message: AADSTS50012: Invalid client secret is provided'
            except:
                self.last_error

            self.authentication_failure = True
            return

        try:
            jwt = self.decode_jwt(response['id_token'])
        except Exception as e:
            _logger.warning('JWT - Authentication failure for user %s: %s --- %s' % (self.id, str(e), str(response)))

            self.authentication_failure = True
            return

        try:
            self.write({
                'refresh_token': response['refresh_token'],
                'access_token': response['access_token'],
                'id_token': response['id_token'],
                'email': jwt['payload']['preferred_username'],
                'authentication_failure': False
            })
        except Exception as e:
            _logger.debug(response)
            _logger.debug(jwt)
            _logger.warning('Write - Authentication failure for user %s: %s' % (self.id, str(e)))

            self.authentication_failure = True
            return

    @api.model
    def get_token(self, grant_type, code_type, code):
        """Calls the Azure AD Token Endpoint"""
        params = {
            'grant_type': grant_type,
            'client_id': self.oauth_client_id,
            'client_secret': self.oauth_client_secret,
            'scope': self.get_azure_ad_scope(),
            code_type: code,
            'redirect_uri': self.get_login_redirect_url(),
        }

        response = requests.post(AZURE_AD_TOKEN_ENDPOINT, data=params)

        try:
            body = response.json()
        except ValueError:
            body = response.text

        self.raise_exception_for_response(AzureResponse(method="POST", body=body, status_code=response.status_code))

        return response.json()

    # --------
    # Requests
    # --------
    # GET
    def get_data(self, domain=None, url=None, data_id=None, headers=None):
        """Performs a GET Request to the Azure AD Endpoint for this user."""

        return self.aad_request(method='GET', url=url, domain=domain, data_id=data_id, headers=headers, force=True)

    # POST
    def post_data(self, domain, data, data_id=None, link=None, force=False):
        """Performs a POST Request to the Azure AD Endpoint for this user."""

        return self.aad_request(method='POST', domain=domain, data_id=data_id, data=data, link=link, force=force)

    # DELETE
    def delete_data(self, domain, data_id=None, link=None, force=False, escalate=True):
        """Performs a DELETE Request to the Azure AD Endpoint for this user."""

        data_id = data_id or link.data_id

        # Find Links depending on data_id, remove them
        if data_id:
            # Find queue items for this data_id, cancel them
            self.env['azure.ad.push.queue.item'].search([('data_domain', 'like', data_id), ('status', 'in', ['waiting', 'retrying'])]).write({'status': 'cancelled', 'last_error': 'Parent deleted by AadRequest'})
            self.env['azure.ad.push.queue.item'].search([('data_id', '=', data_id), ('status', 'in', ['waiting', 'retrying'])]).write({'status': 'cancelled', 'last_error': 'Deleted by AadRequest'})

            if escalate:
                self.env['azure.ad.user.record.link'].sudo().search([('create_domain', 'like', data_id)]).delete()
            else:
                self.env['azure.ad.user.record.link'].sudo().search([('create_domain', 'like', data_id)]).unlink()

            return self.aad_request(method='DELETE', domain=domain, data_id=data_id, force=force, link=link)
        else:
            return False

    # PATCH
    def patch_data(self, domain, data, data_id=None, link=None, force=False):
        """Performs a PATCH Request to the Azure AD Endpoint for this user."""

        return self.aad_request(method='PATCH', domain=domain, data_id=data_id, data=data, link=link, force=force)

    # SYNC
    def sync_request(self, domain=None, url=None, data=None, headers=None):
        sync_headers = {'Prefer': 'odata.track-changes, odata.maxpagesize=200, outlook.body-content-type="text"'}

        if headers:
            sync_headers.update(headers)

        try:
            sync_data = self.aad_request(method='GET', domain=domain, url=url, force=True, headers=sync_headers)
        except NotFoundError as e:
            # Check if sync point is gone
            if e.status_code == 410:
                # Do request again, without deltatoken
                delta_removed = re.sub(r'&?(%24|&)?deltatoken=[^&]*', '', url or domain, 1, re.IGNORECASE)

                sync_data = self.aad_request(method='GET', domain=delta_removed if domain else None, url=delta_removed if url else None, force=True, headers=sync_headers)
            else:
                raise e

        if data:
            sync_data['value'].extend(data['value'])

        # NextLink, more results found
        if u'@odata.nextLink' in sync_data:
            return self.sync_request(url=sync_data[u'@odata.nextLink'], data=sync_data, headers=headers)

        # First sync without deltatoken
        if (url and 'deltaToken' not in url) and (domain and 'deltaToken' not in domain):
            return self.sync_request(url=sync_data[u'@odata.deltaLink'], data=sync_data, headers=headers)

        return sync_data

    # Perform Batch Request
    def batch_request(self, push_items=None, batch_requests=None):
        if push_items is None:
            push_items = []
        if batch_requests is None:
            batch_requests = []

        batch_requests.extend([self.prepare_batch_request(method=i.method, data=i.data, domain=i.data_domain, data_id=i.data_id, link=i.link) for i in push_items])

        if not batch_requests:
            return []

        # Splits into groups of 20
        batch_groups = [batch_requests[i:i + 20] for i in range(0, len(batch_requests), 20)]
        returns = []

        for group in batch_groups:
            batch_id = uuid.uuid4().hex
            body = ""

            for req in group:
                body += "--batch_%s\n" % batch_id + req.body

            # Newlines required, otherwise microsoft returns JSON parse error
            body += "--batch_%s--\n\n\n" % batch_id

            response = self.aad_request(method="POST", domain="$batch", data=body, force=True, headers={"Content-Type": "multipart/mixed; charset=utf-8; boundary=batch_%s " % batch_id, "Prefer": "odata.continue-on-error"})

            # Returns individual responses, with the response lines split and empty lines removed
            responses = [[l for l in r.splitlines() if l != ''] for r in response.split(response.split('\n', 1)[0])[1:]]

            # Removes final "--batchresponse_[id]--"
            responses[-1] = responses[-1][:-1]

            # Converts response to list with status/response dict, and adds these to the return list
            returns.extend([AzureResponse(status_code=int(next(x for x in res if x.startswith("HTTP/1.1"))[9:12]), body=res[-1], method=req.method, link=req.link) for req, res in zip(group, responses)])

        return returns

    # Perform Request
    def aad_request(self, method, domain, data_id=None, data=None, link=None, url=None, headers=None, force=False):
        """Performs a Request to the Azure AD Endpoint for the provided user."""

        # Create an item for future processing. If request was forced, execute it immediately
        if not force:
            return self.env['azure.ad.push.queue.item'].create({
                'user_id': self.id,
                'data_domain': domain,
                'data_id': data_id,
                'headers': headers,
                'data': json.dumps(data),
                'method': method,
                'link': link.id if link else None
            })

        # Get access token
        try:
            if not self.is_token_valid(self.access_token) and self.refresh_token:
                self.set_access_token()
        except Exception as e:
            _logger.warning('Set token failed for user %s' % self.id)

            self.authentication_failure = True

            raise e

        # Do request, raise exception if something went wrong
        response = self.do_http_method_request(method, self.form_url(url, domain, data_id, link, method), headers, data)

        try:
            return_data = response.json()
        except ValueError:
            return_data = response.text

        return self.process_response(AzureResponse(response.status_code, return_data, method, link))

    def process_response(self, response):
        try:
            self.raise_exception_for_response(response)
        except (AuthenticationError, ScopeError)as e:
            # Authentication failed, or insufficient permissions. notify user
            _logger.warning('User %s' % self.id)

            self.last_error = str(e)

            self.authentication_failure = True

            raise e
        except NotFoundError as e:
            if response.link and response.method == 'DELETE':
                pass
            else:
                raise e
        except (ThrottleError, AlreadyExistsError) as e:
            # Request failed because of errors not handled here, continue
            raise e
        except ParameterError as e:
            # Request failed because of wrong parameters
            raise e
        except ServerError as e:
            raise e
        except Exception as e:
            _logger.warning('Unknown exception for user %s' % self.id)

            traceback.print_exc()

            raise e

        # Update link
        if response.link:
            if response.method == 'DELETE':
                response.link.unlink()

            if response.body:
                updates = self.get_updated_link_data(response.method, response.body)

                if updates:
                    response.link.write(updates)

        return response.body

    def do_http_method_request(self, method, url, headers=None, data=None):
        default_headers = {'Authorization': 'Bearer %s' % self.access_token}

        # FOR DEBUGGING PURPOSE ONLY
        # print method, url, (data or '').replace('\n', '')

        # If data is not a string yet, convert it to json
        if data and not isinstance(data, str):
            data = json.dumps(data)

        if method == 'GET':
            if headers:
                default_headers.update(headers)

            return requests.get(url, headers=default_headers)
        elif method == 'DELETE':
            return requests.delete(url, headers=default_headers)
        elif method == 'POST':
            default_headers.update({'Content-Type': 'application/json'})

            if headers:
                default_headers = dict(list(default_headers.items()) + list(headers.items()))

            return requests.post(url, headers=default_headers, data=data)
        elif method == 'PATCH':
            default_headers.update({'Content-Type': 'application/json'})
            return requests.patch(url, headers=default_headers, data=data)
        raise NotImplementedError('HTTP Method not Implemented: %s' % method)

    # -------
    # Helpers
    # -------
    # Secret
    @api.model
    def get_secret(self):
        """Returns Random Secret"""

        return hashlib.sha256(str(random()).encode('utf-8')).hexdigest()

    # URL
    def get_authorize_url(self):
        """Returns the Azure AD Authorize URL"""

        self.ensure_one()

        params = {
            'client_id': self.oauth_client_id,
            'scope': self.get_azure_ad_scope(),
            'response_type': 'code',
            'response_mode': 'form_post',
            'redirect_uri': self.get_login_redirect_url(),
            'state': self.security_code,
        }

        if self.email:
            params.update({
                'login_hint': self.email,
            })

        url = AZURE_AD_AUTH_ENDPOINT + '?' + werkzeug.url_encode(params)

        return url

    @api.model
    def get_base_url(self):
        """Returns the Web Base URL"""

        return self.env['ir.config_parameter'].sudo().get_param('web.base.url')

    @api.model
    def get_login_redirect_url(self):
        """Returns the  URL"""

        return self.get_base_url() + '/aad_api_oauth/login'

    @api.model
    def get_webhook_url(self):
        """Returns the  URL"""

        return self.get_base_url() + '/aad_webhook'

    @api.model
    def get_updated_link_data(self, method, data):
        """Returns the fields to update in the link for the current request"""

        if method in ['POST']:
            return {'data_id': data['Id']}
        else:
            return {}
    
    @api.model
    def prepare_batch_request(self, method, url=None, domain=None, data_id=None, link=None, data=None):
        body = "Content-Type: application/http\nContent-Transfer-Encoding: binary\n\n"

        body += "%s %s HTTP/1.1\n" % (method, self.form_url(url, domain, data_id, link, method))
        if data:
            body += "Content-Type: application/json\n\n"
        else:
            body += "\n"
        body += data or ''
        body += "\n\n"
        
        return BatchRequest(body=body, method=method, link=link)

    # JWT
    @staticmethod
    def decode_jwt(jwt):
        """Parses Json Web Token String to Object"""
        s = jwt.split('.')

        if len(s) != 3:
            raise ValueError("JWT does not have three parts!")

        return {
            'header': AzureAdUser.decode_jwt_base64(s[0]),
            'payload': AzureAdUser.decode_jwt_base64(s[1]),
            'signature': s[2],
        }

    @staticmethod
    def decode_jwt_base64(s):
        """Returns decoded base64 string"""
        missing_padding = len(s) % 4

        if missing_padding != 0:
            s += '=' * (4 - missing_padding)

        return json.loads(base64.b64decode(s).decode())

    #  Time
    @staticmethod
    def check_epoch_time_still_valid(t):
        """Checks if time of access token is still valid"""
        cur_time = int(time.time())

        return t and cur_time < (t - 1)

    @staticmethod
    def get_token_expiration_time(token):
        """Returns the epoch expiration time"""
        try:
            return AzureAdUser.decode_jwt(token)['payload']['exp']
        except AttributeError:
            _logger.debug("Malformed jwt token: %s" % token)

            return False

    @staticmethod
    def is_token_valid(token):
        exp_time = AzureAdUser.get_token_expiration_time(token)

        return exp_time and AzureAdUser.check_epoch_time_still_valid(exp_time)

    @staticmethod
    def form_url(url, domain, data_id, link, method):
        """Forms the url used for the current request"""
        if url:
            return url

        if data_id:
            domain %= data_id
        elif link and link.data_id:
            domain %= link.data_id

        return OUTLOOK_ENDPOINT + domain

    # ---------
    # Overrides
    # ---------
    def name_get(self):
        return [(user.id, user.email) for user in self]

    @api.model
    def create(self, vals):
        res = super(AzureAdUser, self).create(vals)

        res.security_code = self.get_secret()

        return res

    def unlink(self):
        # Cancel Push Queue, other queues and links get unlinked automatically

        for user in self:
            user.push_queue_item_ids.filtered(lambda r: r.status in ['waiting', 'retrying']).write({'status': 'cancelled', 'last_error': 'Azure AD User Removed'})

        return super(AzureAdUser, self).unlink()

    # ----------
    # Exceptions
    # ----------
    @staticmethod
    def raise_exception_for_response(response):
        if response.status_code in [200, 201, 202, 204]:
            return

        message = str(response.status_code) + json.dumps(response.body or '')

        if response.status_code in [400, 405, 406, 415]:
            raise ParameterError(message, response.status_code)

        if response.status_code in [404, 410]:
            raise NotFoundError(message, response.status_code)

        if response.status_code in [401]:
            raise AuthenticationError(message, response.status_code)

        if response.status_code in [403]:
            raise ScopeError(message, response.status_code)

        if response.status_code in [429]:
            raise ThrottleError(message, response.status_code)

        if response.status_code in [500, 501, 503]:
            raise ServerError(message, response.status_code)

        if response.status_code in [409]:
            raise AlreadyExistsError(message, response.status_code)

    # ---------------
    # Webhook Removal
    # ---------------
    def remove_webhook(self):
        """Setup Syncing, should be extended in other modules."""
        self.ensure_one()

        # Remove Subscriptions
        self.azure_ad_subscription_ids.unlink()

        return

    # ------------
    # Cron Methods
    # ------------
    @api.model
    def refresh_access(self):
        for user in self:
            try:
                user.set_access_token()
            except:
                pass

    # -----------
    # Overridable
    # -----------
    @api.model
    def get_azure_ad_scope(self):
        return AZURE_AD_SCOPE

    def init_webhook(self):
        """Setup Syncing, should be extended in other modules."""
        self.ensure_one()
        return

    def init_sync(self):
        """Setup Syncing, should be extended in other modules."""
        self.ensure_one()
        self.azure_ad_sync_started = True

        self.env['azure.ad.pull.queue.item'].create({
            'user_id': self.id
        }).process()

        return

    def validate_fields(self):
        """Validates field if they are correctly filled in, should be extended in other modules."""
        self.ensure_one()
        
        # Tests if user is logged in correctly
        self.set_access_token()
        if self.authentication_failure:
            raise ValidationError('%s\n\n%s' % (_('Login failed'), _('Please retry login in with your Office 365 account.')))

        # Tests if an outlook category has been defined
        if not self.outlook_category:
            raise ValidationError('%s\n\n%s' % (_('No outlook category defined'), _('An outlook category name has not been defined. Please enter the category name to use before starting the synchronisation.')))


class BatchRequest:
    def __init__(self, method, body, link=None):
        self.link = link
        self.method = method
        self.body = body
    
    
class AzureResponse:
    def __init__(self, status_code, body, method, link=None):
        self.link = link
        self.method = method
        self.status_code = status_code

        try:
            self.body = json.loads(body)
        except:
            self.body = body
