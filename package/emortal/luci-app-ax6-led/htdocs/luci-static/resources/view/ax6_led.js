'use strict';
'require form';
'require ui';
'require view';

function addChoices(option, choices) {
	for (var i = 0; i < choices.length; i++)
		option.value(choices[i][0], choices[i][1]);
	return option;
}

function toStringList(value) {
	var values = L.toArray(value);
	var list = [];

	for (var i = 0; i < values.length; i++) {
		var item = values[i];
		if (item == null)
			continue;
		if (typeof(item) == 'string') {
			item = item.trim();
			if (item == '')
				continue;
			list = list.concat(item.split(/\s+/));
		}
		else {
			list.push(String(item));
		}
	}
	return list;
}

/* UCI stores these multi-select values as a space separated option. */
var SpaceSeparatedMultiValue = form.MultiValue.extend({
	renderWidget: function(section_id, option_index, cfgvalue) {
		var choices = this.transformChoices();
		var widget = new ui.Select(toStringList((cfgvalue != null) ? cfgvalue : this.default), choices, {
			id: this.cbid(section_id),
			sort: this.keylist,
			multiple: true,
			widget: 'checkbox',
			orientation: this.orientation || 'horizontal',
			disabled: (this.readonly != null) ? this.readonly : this.map.readonly
		});
		var node = widget.render();
		var inputs = node.querySelectorAll('input[type="checkbox"]');
		var items = node.querySelectorAll('.cbi-checkbox');

		for (var i = node.childNodes.length - 1; i >= 0; i--)
			if (node.childNodes[i].nodeType == 3)
				node.removeChild(node.childNodes[i]);

		for (var i = 0; i < items.length; i++)
			items[i].style.setProperty('display', 'inline-flex', 'important');

		widget.getValue = function() {
			var values = [];
			for (var i = 0; i < inputs.length; i++)
				if (inputs[i].checked)
					values.push(inputs[i].value);
			return values;
		};
		widget.setValue = function(value) {
			var values = toStringList(value);
			for (var i = 0; i < inputs.length; i++)
				inputs[i].checked = (values.indexOf(inputs[i].value) > -1);
		};
		for (var i = 0; i < inputs.length; i++) {
			widget.setUpdateEvents(inputs[i], 'change', 'click', 'blur');
			widget.setChangeEvents(inputs[i], 'change');
		}
		return node;
	},

	cfgvalue: function(section_id, set_value) {
		if (arguments.length == 2)
			return this.super('cfgvalue', [ section_id, set_value ]);
		return toStringList(this.super('cfgvalue', [ section_id ]));
	},

	write: function(section_id, value) {
		return this.super('write', [ section_id, toStringList(value).join(' ') ]);
	}
});

function addTimeChoices(option) {
	for (var h = 0; h < 24; h++)
		for (var m = 0; m < 60; m += 30)
			option.value(('0' + h).slice(-2) + ':' + ('0' + m).slice(-2));
	return option;
}

return view.extend({
	render: function() {
		var m, s, o;

		m = new form.Map('ax6_led', _('AX6 LED 定时开关'),
			_('按周定时全部开启或关闭 AX6 的 LED。开启时间内所有选中的 LED 点亮，关闭时间内全部熄灭。'));

		s = m.section(form.NamedSection, 'schedule', 'schedule', _('定时设置'));
		s.anonymous = true;
		s.addremove = false;

		o = s.option(form.Flag, 'enabled', _('启用定时'),
			_('关闭后不会改变当前 LED 行为，并恢复调度前的 LED 状态。'));
		o.default = '0';
		o.rmempty = false;

		o = s.option(form.ListValue, 'on_time', _('全部开启时间'),
			_('到达该时间后，所有选中的 LED 全部点亮。'));
		o.default = '07:00';
		o.rmempty = false;
		addTimeChoices(o);

		o = s.option(form.ListValue, 'off_time', _('全部关闭时间'),
			_('到达该时间后，所有选中的 LED 全部熄灭。'));
		o.default = '23:00';
		o.rmempty = false;
		addTimeChoices(o);

		o = s.option(SpaceSeparatedMultiValue, 'days', _('生效星期'),
			_('选择每周哪几天执行；全选表示每天。'));
		o.default = '1 2 3 4 5 6 7';
		o.rmempty = true;
		addChoices(o, [
			[ '1', _('周一') ],
			[ '2', _('周二') ],
			[ '3', _('周三') ],
			[ '4', _('周四') ],
			[ '5', _('周五') ],
			[ '6', _('周六') ],
			[ '7', _('周日') ]
		]);

		o = s.option(SpaceSeparatedMultiValue, 'leds', _('控制的 LED'),
			_('默认全部四个 LED。blue:system 为电源/系统灯。'));
		o.default = 'blue:system blue:network yellow:system yellow:network';
		o.rmempty = false;
		addChoices(o, [
			[ 'blue:system', _('电源/系统灯 (blue:system)') ],
			[ 'blue:network', _('蓝色网络灯 (blue:network)') ],
			[ 'yellow:system', _('黄色系统灯 (yellow:system)') ],
			[ 'yellow:network', _('黄色网络灯 (yellow:network)') ]
		]);

		return m.render();
	}
});
