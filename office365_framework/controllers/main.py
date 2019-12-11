# See LICENSE file for full copyright and licensing details.
import logging
import werkzeug

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class OfficeOAuthLogin(http.Controller):

    @http.route('/aad_api_oauth/login', type='http', auth='user', csrf=False)
    def login(self, **kwargs):
        sec_code = kwargs['state']
        user = request.env['res.users'].browse(request.uid)
        azure_ad_user = user.azure_ad_user_id

        if azure_ad_user and sec_code == azure_ad_user.sudo().security_code:
            azure_ad_user.sudo().write({'authentication_code': kwargs['code']})
            user.aad_setup()

            _logger.info("New Office365 User login with email address: %s" % user.azure_ad_user_id.email)

            return werkzeug.utils.redirect("/web", 303)

    # @http.route('/aad_webhook', type='http', auth='none', csrf=False)
    # def webhook_validate(self, validationtoken=None, **kwargs):
    #     print 'validate'
    #     # WEBHOOK Logic for creating pull queue items
    #
    #     print self, kwargs
    #
    #     # Database?
    #     # Which user?
    #     # Is the webhook locked?
    #
    #     if validationtoken:
    #         return validationtoken
    #     else:
    #         return ''
    #
    # @http.route('/aad_webhook', type='json', auth='none', csrf=False)
    # def webhook_test(self, validationtoken=None, **kwargs):
    #     print 'validate'
    #     # WEBHOOK Logic for creating pull queue items
    #
    #     print self, kwargs
    #
    #     # Database?
    #     # Which user?
    #     # Is the webhook locked?
    #
    #     if validationtoken:
    #         return validationtoken
    #     else:
    #         return ''
