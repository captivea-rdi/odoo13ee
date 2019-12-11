# See LICENSE file for full copyright and licensing details.
from odoo.fields import Reference
from odoo.models import BaseModel


class VirtualReference(Reference):
    def convert_to_cache(self, value, record, validate=True):
        # cache format: (res_model, res_id) or False
        def process(res_model, res_id):
            try:
                res_id = int(res_id)
            except ValueError:
                pass

            record._prefetch[res_model].add(res_id)
            return res_model, res_id

        if isinstance(value, BaseModel):
            if not validate or (value._name in self.get_values(record.env) and len(value) <= 1):
                return process(value._name, value.id) if value else False
        elif isinstance(value, str):
            res_model, res_id = value.split(',')
            if record.env[res_model].browse(res_id).exists():
                return process(res_model, res_id)
            else:
                return False
        elif not value:
            return False
        raise ValueError("Wrong value for %s: %r" % (self, value))

    def convert_to_record(self, value, record):
        return value and record.env[value[0]].browse([value[1]], record._prefetch)

    def convert_to_read(self, value, record, use_name_get=True):
        return "%s,%s" % (value._name, value.id) if value else False
