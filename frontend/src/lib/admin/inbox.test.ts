import { describe, expect, it } from 'vitest';
import { convLabel, countLabel, inboxHref, senderLabel } from './inbox.svelte';

const msg = { seq: 1, ts: 100, text: 'hola', emoji: false };

describe('mensajes nuevos (ADR 0022)', () => {
	it('cuenta hasta 99 y después «99+»', () => {
		expect(countLabel(1)).toBe('1');
		expect(countLabel(99)).toBe('99');
		expect(countLabel(100)).toBe('99+');
	});

	it('lleva a la conversación en el Cliente', () => {
		expect(inboxHref({ cid: 'tcp-mrco', conv: 'dm:!c6c3daac' })).toBe(
			'/admin/cliente?placa=tcp-mrco&conv=dm%3A!c6c3daac'
		);
	});

	it('nombra canales y directos', () => {
		expect(convLabel({ dm: false, name: 'MediumFast', channel_index: 0 })).toBe('# MediumFast');
		expect(convLabel({ dm: false, name: null, channel_index: 2 })).toMatch(/^# .*2/);
		expect(convLabel({ dm: true, name: 'LU2VMC', peer: '!c6c3daac' })).toBe('LU2VMC');
		expect(convLabel({ dm: true, name: null, peer: '!c6c3daac' })).toBe('!c6c3daac');
	});

	it('nombra a quien escribió con lo que se sepa', () => {
		const who = { from: '!7f0f359f', from_name: 'Meshtastic 359f', from_short: '359f' };
		expect(senderLabel({ ...msg, ...who })).toBe('359f');
		expect(senderLabel({ ...msg, ...who, from_short: null })).toBe('Meshtastic 359f');
		expect(senderLabel({ ...msg, from: '!7f0f359f', from_name: null, from_short: null })).toBe(
			'!7f0f359f'
		);
	});
});
