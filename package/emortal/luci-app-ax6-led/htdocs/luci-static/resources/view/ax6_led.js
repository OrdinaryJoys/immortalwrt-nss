'use strict';
'require form';
'require view';

return view.extend({
	render: function() {
		var m, s, o;

		m = new form.Map('ax6_led', _('AX6 LED 定时开关'),
			_('按周定时全部开启或关闭 AX6 的 LED。开启时间内所有 LED 点亮，关闭时间内所有 LED 熄灭。'));

		s = m.section(form.NamedSection, 'schedule', 'schedule', _('定时设置'));
		s.anonymous = true;
		s.addremove = false;

		o = s.option(form.Flag, 'enabled', _('启用定时'),
			_('关闭后不会改变当前 LED 行为，并恢复调度前的 LED 状态。'));
		o.default = '0';
		o.rmempty = false;

		o = s.option(form.Value, 'on_time', _('全部开启时间'),
			_('24 小时制，格式 HH:MM。到达该时间后全部 LED 点亮。'));
		o.default = '07:00';
		o.placeholder = '07:00';
		o.rmempty = false;
		o.validate = function(section_id, value) {
			if (!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(value))
				return _('时间格式必须为 HH:MM');
			return true;
		};

		o = s.option(form.Value, 'off_time', _('全部关闭时间'),
			_('24 小时制，格式 HH:MM。到达该时间后全部 LED 熄灭。'));
		o.default = '23:00';
		o.placeholder = '23:00';
		o.rmempty = false;
		o.validate = function(section_id, value) {
			if (!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(value))
				return _('时间格式必须为 HH:MM');
			return true;
		};

		o = s.option(form.Value, 'days', _('生效星期'),
			_('1=周一 … 7=周日，用空格分隔；留空表示每天。'));
		o.default = '1 2 3 4 5 6 7';
		o.placeholder = '1 2 3 4 5 6 7';
		o.rmempty = true;
		o.validate = function(section_id, value) {
			if (value == '')
				return true;
			var parts = value.trim().split(/\s+/);
			for (var i = 0; i < parts.length; i++)
				if (!/^[1-7]$/.test(parts[i]))
					return _('星期只能使用 1 到 7，空格分隔');
			return true;
		};

		o = s.option(form.Value, 'leds', _('LED 列表'),
			_('要控制的 LED sysfs 名称，空格分隔。默认 AX6 四个 LED。'));
		o.default = 'blue:system blue:network yellow:system yellow:network';
		o.rmempty = false;

		return m.render();
	}
});
