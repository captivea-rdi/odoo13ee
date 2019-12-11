# -*- coding: utf-8 -*-
# Odoo Proprietary License v1.0
#
# This software and associated files (the "Software") may only be used (executed, modified,
# executed after modifications) if you have purchased a valid license from the authors, typically
# via Odoo Apps, or if you have received a written agreement from the authors of the Software (see
# the COPYRIGHT file).
#
# You may develop Odoo modules that use the Software as a library (typically by depending on it,
# importing it and using its resources), but without copying any source code or material from the
# Software. You may distribute those modules under the license of your choice, provided that this
# license is compatible with the terms of the Odoo Proprietary License (For example: LGPL, MIT, or
# proprietary licenses similar to this one).
#
# It is forbidden to publish, distribute, sublicense, or sell copies of the Software or modified
# copies of the Software.
#
# The above copyright notice and this permission notice must be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
# BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
{
    'name': 'Office 365 OAuth Client',
    'version': '12.0.1.0',
    'author': 'Somko',
    'category': 'Productivity',
    'description': """Handles the connection to Microsoft Office 365 API. This module does not provide any functional use on its own, but should be used in combination with other modules.""",
    'summary': """Framework for syncing with Microsoft Office 365 API""",
    'website': 'https://www.somko.be',
    'images': ['static/description/cover.png',],
    'license': "OPL-1",
    'depends': ['base', 'base_setup'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/security.xml',

        'views/res_config_settings.xml',
        'views/res_users.xml',

        'views/azure_ad_push_queue_item.xml',
        'views/azure_ad_change_queue_item.xml',
        'views/azure_ad_pull_queue_item.xml',
        'views/azure_ad_user_record_link.xml',
        'views/azure_ad_user.xml',
        'views/custom_sync_value.xml',
        'views/menu.xml',

        'data/ir_cron_jobs.xml',
    ],
    'qweb': [],
    'demo': [],
    'test': [],
    "auto_install": False,
    'application': False,
    "installable": True,
    "price": 99,
    "currency": "EUR",
}
