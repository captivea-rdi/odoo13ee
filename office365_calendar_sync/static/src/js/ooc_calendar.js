odoo.define('office365_calendar_sync.action_manager', function(require) {
    var action_manager = require('web.ActionManager');

    return action_manager.include({
        ir_actions_act_do_nothing: function (action, options) {
            return $.Deferred().reject();
        }
    });
});

odoo.define('office365_calendar_sync.ooc_calendar', function (require) {
    "use strict";

    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var framework = require('web.framework');
    var CalendarRenderer = require('web.CalendarRenderer');
    var CalendarController = require('web.CalendarController');

    var _t = core._t;

    CalendarController.include({
        custom_events: _.extend({}, CalendarController.prototype.custom_events, {
            syncOocCalendar: '_onSyncOocCalendar'
        }),

        _onSyncOocCalendar: function (event) {
            var self = this;
            var context = this.getSession().user_context;

            this._rpc({
                route: '/office365_calendar_sync/sync',
                params: {
                    model: this.modelName,
                    fromurl: window.location.href,
                    local_context: context
                }
            }).then(function (o) {
                if (o.status === "no_user") {
                    Dialog.confirm(self, _t("Your Office account needs to be configured before you can synchronize, do you want to do it now?"), {
                        confirm_callback: function() {
                            $('a[data-menu="settings"]').trigger('click')
                        },
                        title: _t('Configuration')
                    });
                } else if (o.status === "auth_failure") {
                    Dialog.alert(self, _t("Synchronization with your Office account failed because of authentication failure. Please login (again) to synchronize."), {
                        confirm_callback: function() {
                            $('a[data-menu="settings"]').trigger('click')
                        },
                        title: _t('Authentication Error')
                    });
                } else if (o.status === "not_allowed") {
                    Dialog.alert(self, _t("Your administrator has not yet configured Office 365 synchronisation yet."), {
                        title: _t('Authentication Error')
                    });
                } else if (o.status === "sync_not_started") {
                    Dialog.alert(self, _t("Synchronization with your Office account has not started yet. Please confirm your Office 365 settings and press sync to start synchronization in your user preferences."), {
                        confirm_callback: function() {
                            $('a[data-menu="settings"]').trigger('click')
                        },
                        title: _t('Authentication Error')
                    });
                } else if (o.status === "no_calendar") {
                    Dialog.alert(self, _t("Synchronization with your Outlook calendar failed because it was removed. Please pick another calendar in your Office 365 settings."), {
                        confirm_callback: function() {
                            $('a[data-menu="settings"]').trigger('click')
                        },
                        title: _t('Calendar Removed')
                    });
                } else if (o.status === "failed") {
                    Dialog.alert(self, _t("Synchronization with your Office account failed because of an unknown error. Please try again in a few minutes, or contact an administrator."), {
                        title: _t('Unknown Error')
                    });
                } else if (o.status === "success") {
                    self.reload();

                    Dialog.alert(self, _.str.sprintf(_t("Updated %s events. If you expected changes but do not see them, try again after a few seconds."), o.update_count['pulled'] + o.update_count['changed'] ), {
                        title: _t('Finished Sync')
                    });
                }
            }).always(function () {
                event.data.on_always();
            });
        }
    });

    CalendarRenderer.include({
        events: _.extend({}, CalendarRenderer.prototype.events, {
            'click .o_ooc_calendar_sync_button': '_onSyncOocCalendar'
        }),

        //--------------------------------------------------------------------------
        // Private
        //--------------------------------------------------------------------------
        _initSidebar: function () {
            var self = this;
            this._super.apply(this, arguments);
            this.$ooc_sync_button = $();
            if (this.model === "calendar.event") {
                this.$ooc_sync_button = $('<button/>', {type: 'button', html: _t("  Sync with <b>Outlook</b>")})
                    .addClass('o_ooc_calendar_sync_button oe_button btn btn-sm btn-default')
                    .prepend($('<i class="fa fa-refresh"/>'))
                    .appendTo(self.$sidebar);
            }
        },

        //--------------------------------------------------------------------------
        // Handlers
        //--------------------------------------------------------------------------
        _onSyncOocCalendar: function () {
            var self = this;
            var context = this.getSession().user_context;
            this.$ooc_sync_button.prop('disabled', true);
            this.trigger_up('syncOocCalendar', {
                on_always: function () {
                    self.$ooc_sync_button.prop('disabled', false);
                }
            });
        }
    });
});