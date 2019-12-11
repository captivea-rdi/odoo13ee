import datetime
import time

import dateutil
from pytz import timezone

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import test_python_expr, safe_eval


class CustomSyncValue(models.Model):
    _name = 'custom.sync.value'
    _order = 'model_id,sequence,id'

    model_id = fields.Many2one(string='Document Model', comodel_name='ir.model', ondelete='cascade')
    name = fields.Char(string="Short Description")
    code = fields.Text(string="Object",
                       default="""# Available variables:
#  - env: Odoo Environment on which the action is triggered
#  - model: Odoo Model of the record on which the action is triggered; is a void recordset
#  - record: record on which the action is triggered; may be be void
#  - time, datetime, dateutil, timezone: useful Python libraries
# When using Extended Properties, ensure that the Property GUID is a newly generated one.
# To return custom values, assign: custom = {...}
custom = {
    'SingleValueExtendedProperties': [{
        'PropertyId': 'String {c05e7d2e-2e5b-4c66-a210-d3e3859cc416} Name SomeProp',
        'Value': 'Something'
    }]
}"""
                       )

    sequence = fields.Integer(string='Sequence')
    active = fields.Boolean(string='Active')

    # Constraints
    @api.constrains('code')
    def _check_python_code(self):
        for action in self.sudo().filtered('code'):
            msg = test_python_expr(expr=action.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    # Context parser
    @api.multi
    def get_custom_value_dict(self):
        eval_context = self._get_eval_context()

        safe_eval(self.sudo().code.strip(), eval_context, mode="exec", nocopy=True)  # nocopy allows to return 'action'

        if 'custom' in eval_context:
            return eval_context['custom']
        else:
            return False

    @api.multi
    def _get_eval_context(self):
        return {
            'env': self.env,
            'model': self.browse([]),
            'record': self,
            'time': time,
            'datetime': datetime,
            'dateutil': dateutil,
            'timezone': timezone,
        }

