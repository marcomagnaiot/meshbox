import { describe, expect, it } from 'vitest';
import type { Traceroute } from '$lib/api/types';
import { tracerouteLegs, UNKNOWN_HOP } from './traceroute';

const base: Traceroute = {
	ts: 1,
	from: '!aaaaaaaa',
	to: '!bbbbbbbb',
	route: [],
	snr_towards: [],
	route_back: [],
	snr_back: []
};

describe('tracerouteLegs', () => {
	it('arma la ida y la vuelta con el SNR de cada tramo', () => {
		const legs = tracerouteLegs({
			...base,
			route: ['!cccccccc', UNKNOWN_HOP],
			snr_towards: [10, null, 5.5],
			route_back: ['!cccccccc'],
			snr_back: [7.5, 3]
		});
		expect(legs.towards).toEqual([
			{ id: '!aaaaaaaa', unknown: false, snr: null },
			{ id: '!cccccccc', unknown: false, snr: 10 },
			{ id: UNKNOWN_HOP, unknown: true, snr: null },
			{ id: '!bbbbbbbb', unknown: false, snr: 5.5 }
		]);
		expect(legs.back?.map((h) => [h.id, h.snr])).toEqual([
			['!bbbbbbbb', null],
			['!cccccccc', 7.5],
			['!aaaaaaaa', 3]
		]);
	});

	it('directo y sin datos de la vuelta', () => {
		const legs = tracerouteLegs({ ...base, snr_towards: [8] });
		expect(legs.towards.map((h) => h.snr)).toEqual([null, 8]);
		expect(legs.back).toBeNull();
	});
});
