# See LICENSE file for full copyright and licensing details.
import json
import logging
from datetime import datetime

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AzureADChangeQueuer(models.AbstractModel):
    _name = 'azure.ad.change.queuer'

    change_last_write = fields.Datetime(string="Change Queue Last Write")
    change_original_values = fields.Char(string="JSON Object which holds the previously synced values")

    def write(self, vals):
        is_o_value_update = self.env.context.get('is_o_value_update')
        is_external_change = self.env.context.get('is_external_change')
        is_change_push = self.env.context.get('is_change_push')

        # -- Actions to perform before Write --
        # Logic if regular write, should save changed fields since last change push
        if not (is_o_value_update or is_external_change or is_change_push):
            for record in self:
                changed_values = {}
                original_values = json.loads(record.change_original_values or '{}')
                observed_keys = self.get_change_observed_values()

                for k, v in vals.items():
                    if k in observed_keys and k not in original_values:
                        if hasattr(record[k], 'ids') and type(v) == list and len(v) and len(v[0]) == 3:
                            ids = v[0][2]
                            if record[k].ids != ids:
                                changed_values[k] = [(6, 0, record[k].ids)]
                        elif hasattr(record[k], 'id'):
                            if record[k].id != v:
                                changed_values[k] = record[k].id
                        elif type(record[k]) == datetime:
                            changed_values[k] = fields.Datetime.to_string(record[k])
                        else:
                            changed_values[k] = record[k]

                if changed_values:
                    original_values.update(changed_values)

                    record.with_context(is_o_value_update=True).write({'change_original_values': json.dumps(original_values)})

        # -- Write --
        # Don't save if change is coming from an external system
        if not is_external_change:
            r = super(AzureADChangeQueuer, self).write(vals)

            # If this write was a changed fields update, pass
            if is_o_value_update:
                pass

            # If change_push, push to links
            elif is_change_push:
                _logger.info('AzureAD Links patched for record %s,%s' % (self.ids, self._name))

                for record in self:
                    record.get_links().patch(record.get_azure_ad_template(vals))

                    # Parent changed, update children
                    if hasattr(record, 'child_ids') and record.child_ids:
                        for child in record.child_ids:
                            self.env['azure.ad.user.record.link'].sudo().search([('record', '=', '%s,%s' % (self._name, child.id))]).patch(record.get_azure_ad_template(vals, is_child=True))

                    record.with_context(is_o_value_update=True).write({'change_original_values': ''})

            # Make change items
            else:
                for record in self:
                    self.create_changed_item(vals, record.write_date, record)

            return r
        else:
            last_write = vals.pop('last_write', None)

            # Make change item
            for record in self:
                self.create_changed_item(vals, last_write, record)

            return self

    def unlink(self):
        self.remove_links()

        return super(AzureADChangeQueuer, self).unlink()

    def remove_links(self):
        for record in self:
            domain = record.get_record_link_domain()

            self.env['azure.ad.user.record.link'].sudo().search(domain).delete()
            self.env['azure.ad.change.queue.item'].sudo().search(domain).unlink()

    def extract_changed(self, data):
        self.ensure_one()

        patch_fields = {}
        original_values = json.loads(self.change_original_values or '{}')

        for name, value in data.items():
            # Code should continue to next for iteration if
            #  - Field does not exist in self
            #  - Original_value same as current value
            #  - Single Relation field value same as current value
            #  - Many Relation field set has no difference as current value
            #  - Regular field value same as current value

            if name in self:
                if name in original_values:
                    # Saved in original_values, compare with original_values

                    if original_values[name] == value:
                        continue
                else:
                    # Not saved in original_values, compare with self
                    if hasattr(self[name], 'ids'):
                        # Relation type
                        if len(set(self[name].ids) ^ set(value[0][2])) == 0:
                            continue
                    elif hasattr(self[name], 'id'):
                        # Relation type
                        if self[name]['id'] == value:
                            continue
                    else:
                        # Simple type
                        if self[name] == value:
                            continue
            else:
                continue

            patch_fields[name] = value or ''

        return patch_fields

    def create_changed_item(self, vals, time, record):
        observed_keys = self.get_change_observed_values()
        changes = {k: v for k, v in vals.items() if k in observed_keys}

        if not changes:
            return

        self.sudo().env['azure.ad.change.queue.item'].create({
            'change': json.dumps(changes),
            'time': time,
            'record': '%s,%s' % (self._name, record.id),
        })
        _logger.info('AzureAD Change item created for %s' % record)


    def get_links(self):
        return self.env['azure.ad.user.record.link'].sudo().search(self.get_record_link_domain())

    def get_extra_custom_values(self):
        customs = self.env['custom.sync.value'].sudo().search([('model_id.model', '=', self._name), ('active', '=', True)])

        if not customs:
            return False

        if len(customs) == 1:
            return customs.get_custom_value_dict()

        result = customs[0].code

        for custom in customs[1:]:
            result = self.merge_values(result, custom.get_custom_value_dict())

        return result

    @api.model
    def merge_values(self, a, b):
        # If dictionary, run over all the keys
        if type(a) is dict:
            result = {}
            keys = list(a.keys()) + list(b.keys())

            for k in keys:
                if k in a and k in b:
                    result[k] = self.merge_values(a[k], b[k])
                else:
                    result[k] = a[k] if k in a else b[k]

            return result

        # If list, combine
        elif type(a) is list:
            try:
                return list(set(a + b))
            except:
                return a + b

        # Else, b wins
        else:
            return b

    def get_azure_ad_template(self, change, is_child=False):
        template = self.prepare_azure_ad_template(change, is_child)
        extra_values = self.get_extra_custom_values()

        if extra_values:
            template = self.merge_values(template, extra_values)

        return template

    # -----------
    # Overridable
    # -----------
    def prepare_azure_ad_template(self, change, is_child=False):
        return {}

    @api.model
    def get_change_observed_values(self):
        return []

    def get_record_link_domain(self):
        return [('record', '=', '%s,%s' % (self._name, self.id))]

