import { describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api/client';
import {
	changedValues,
	dangerFields,
	fieldLabel,
	MASK,
	precisionMeters,
	pskKind,
	sectionValues,
	unreadCount,
	type BoardMessage,
	type ConfigField
} from './radio';

const field = (f: Partial<ConfigField> & Pick<ConfigField, 'name' | 'type'>): ConfigField => ({
	danger: false,
	secret: false,
	readonly: false,
	...f
});

const MQTT: ConfigField[] = [
	field({ name: 'enabled', type: 'bool', value: true, danger: true }),
	field({ name: 'address', type: 'string', value: 'mqtt.example' }),
	field({ name: 'password', type: 'string', value: MASK, secret: true }),
	field({ name: 'admin_key', type: 'list', value: [], readonly: true }),
	field({
		name: 'map_report_settings',
		type: 'object',
		fields: [
			field({ name: 'publish_interval_secs', type: 'int', value: 900 }),
			field({ name: 'position_precision', type: 'int', value: 13 })
		]
	})
];

describe('configuración de la placa', () => {
	it('aplana los valores por ruta', () => {
		expect(sectionValues(MQTT)).toEqual({
			enabled: true,
			address: 'mqtt.example',
			password: MASK,
			admin_key: [],
			'map_report_settings.publish_interval_secs': 900,
			'map_report_settings.position_precision': 13
		});
	});

	it('manda solo lo que cambió, con los objetos anidados', () => {
		const original = sectionValues(MQTT);
		const draft = {
			...original,
			address: 'otro',
			'map_report_settings.position_precision': 15,
			admin_key: ['x']
		};
		expect(changedValues(MQTT, original, draft)).toEqual({
			address: 'otro',
			map_report_settings: { position_precision: 15 }
		});
	});

	it('no reenvía una clave guardada si no se escribió otra', () => {
		const original = sectionValues(MQTT);
		expect(changedValues(MQTT, original, { ...original, password: MASK })).toEqual({});
		expect(changedValues(MQTT, original, { ...original, password: '' })).toEqual({});
		expect(changedValues(MQTT, original, { ...original, password: 'nueva' })).toEqual({
			password: 'nueva'
		});
	});

	it('PIN numérico enmascarado', () => {
		const fields = [field({ name: 'fixed_pin', type: 'int', value: MASK, secret: true })];
		const original = sectionValues(fields);
		expect(changedValues(fields, original, { fixed_pin: MASK })).toEqual({});
		expect(changedValues(fields, original, { fixed_pin: 123456 })).toEqual({ fixed_pin: 123456 });
	});

	it('ignora números vacíos', () => {
		const original = sectionValues(MQTT);
		const draft = { ...original, 'map_report_settings.publish_interval_secs': null };
		expect(changedValues(MQTT, original, draft)).toEqual({});
	});

	it('nombres legibles', () => {
		expect(fieldLabel('screen_on_secs')).toBe('Screen on secs');
	});
});

describe('historial de mensajes', () => {
	const msg = (seq: number, conv: string, direction: 'in' | 'out' = 'in'): BoardMessage => ({
		seq,
		id: seq,
		ts: seq,
		direction,
		from: '!11112222',
		to: '^all',
		dm: conv.startsWith('dm:'),
		conv,
		channel_index: 0,
		channel: 'MediumFast',
		text: 't',
		snr: null,
		rssi: null,
		hops: null,
		reply_id: null,
		emoji: false,
		status: null
	});

	it('cuenta sin leer solo los recibidos posteriores a lo leído', () => {
		const msgs = [msg(1, 'ch:0'), msg(2, 'ch:0'), msg(3, 'ch:0', 'out'), msg(4, 'dm:!11112222')];
		expect(unreadCount(msgs, {}, 'ch:0')).toBe(2);
		expect(unreadCount(msgs, { 'ch:0': 1 }, 'ch:0')).toBe(1);
		expect(unreadCount(msgs, { 'ch:0': 3 }, 'ch:0')).toBe(0);
		expect(unreadCount(msgs, { 'ch:0': 3 }, 'dm:!11112222')).toBe(1);
	});
});

describe('confirmación de cambios peligrosos', () => {
	it('reconoce el 409 del servidor', () => {
		const err = new ApiError({
			title: 'Conflict',
			status: 409,
			code: 'danger_confirmation_required',
			fields: ['region']
		});
		expect(dangerFields(err)).toEqual(['region']);
		expect(dangerFields(new ApiError({ title: 'Conflict', status: 409 }))).toBeNull();
		expect(dangerFields(new Error('x'))).toBeNull();
	});

	it('precisión de posición en metros', () => {
		expect(precisionMeters(0)).toBeNull();
		expect(precisionMeters(32)).toBe(0);
		expect(precisionMeters(13)).toBe(2913);
		expect(precisionMeters(16)).toBe(364);
		expect(precisionMeters(19)).toBe(46);
	});

	it('tipo de clave del canal', () => {
		expect(pskKind({ psk: 'secret' })).toBe('private');
		expect(pskKind({ psk: 'default' })).toBe('public');
		expect(pskKind({ psk: 'simple' })).toBe('public');
		expect(pskKind({ psk: 'none' })).toBe('open');
	});
});
