import { describe, expect, it } from 'vitest';
import { formatCoordinate, parseCoordinates, parseNumber } from './coords';

describe('parseCoordinates', () => {
	it('acepta lo que copia Google Maps', () => {
		expect(parseCoordinates('-35.66045, -63.75212')).toEqual({ lat: -35.66045, lon: -63.75212 });
		expect(parseCoordinates('  -35.66045,-63.75212 ')).toEqual({ lat: -35.66045, lon: -63.75212 });
		expect(parseCoordinates('(-35.66045, -63.75212)')).toEqual({ lat: -35.66045, lon: -63.75212 });
	});

	it('acepta coma decimal', () => {
		expect(parseCoordinates('-35,66045 -63,75212')).toEqual({ lat: -35.66045, lon: -63.75212 });
		expect(parseCoordinates('-35,66045; -63,75212')).toEqual({ lat: -35.66045, lon: -63.75212 });
		expect(parseCoordinates('-35,66045, -63,75212')).toEqual({ lat: -35.66045, lon: -63.75212 });
	});

	it('saca el punto de un enlace', () => {
		expect(parseCoordinates('https://www.google.com/maps/@-35.6604501,-63.7521234,15z')).toEqual({
			lat: -35.6604501,
			lon: -63.7521234
		});
		expect(parseCoordinates('https://maps.google.com/?q=-35.66,-63.75')).toEqual({
			lat: -35.66,
			lon: -63.75
		});
	});

	it('acepta grados, minutos y segundos', () => {
		const p = parseCoordinates(`35°39'37.6"S 63°45'07.6"W`);
		expect(p?.lat).toBeCloseTo(-35.66044, 4);
		expect(p?.lon).toBeCloseTo(-63.75211, 4);
		expect(parseCoordinates(`35°39'37.6"S 63°45'07.6"O`)?.lon).toBeCloseTo(-63.75211, 4);
	});

	it('rechaza lo que no es un par válido', () => {
		expect(parseCoordinates('')).toBeNull();
		expect(parseCoordinates('-35.66045')).toBeNull();
		expect(parseCoordinates('General Pico')).toBeNull();
		expect(parseCoordinates('95, 10')).toBeNull();
		expect(parseCoordinates('10, 200')).toBeNull();
	});
});

describe('parseNumber y formatCoordinate', () => {
	it('lee punto o coma decimal', () => {
		expect(parseNumber('-35.66045')).toBe(-35.66045);
		expect(parseNumber(' -35,66045 ')).toBe(-35.66045);
		expect(parseNumber('-35,')).toBeNull();
		expect(parseNumber('abc')).toBeNull();
	});

	it('muestra hasta 6 decimales con punto', () => {
		expect(formatCoordinate(-35.660450123)).toBe('-35.66045');
		expect(formatCoordinate(null)).toBe('');
	});
});
