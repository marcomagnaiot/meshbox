// Coordenadas escritas o pegadas a mano: «lat, lon» copiado de Google Maps, con coma decimal, un
// enlace con @lat,lon o ?q=lat,lon, o grados, minutos y segundos (35°39'37.6"S 63°45'07.6"W).

export interface LatLon {
	lat: number;
	lon: number;
}

const inRange = (lat: number, lon: number) => Math.abs(lat) <= 90 && Math.abs(lon) <= 180;

/** Un número suelto con punto o coma decimal («-35,66045»); null si no lo es. */
export function parseNumber(text: string): number | null {
	const t = text.trim().replace(',', '.');
	if (!/^[-+]?\d+(\.\d+)?$/.test(t)) return null;
	const v = Number(t);
	return Number.isFinite(v) ? v : null;
}

function pair(a: string, b: string): LatLon | null {
	const lat = Number(a.replace(',', '.'));
	const lon = Number(b.replace(',', '.'));
	return Number.isFinite(lat) && Number.isFinite(lon) && inRange(lat, lon) ? { lat, lon } : null;
}

const DMS =
	/(\d+(?:[.,]\d+)?)\s*°\s*(?:(\d+(?:[.,]\d+)?)\s*['′]\s*)?(?:(\d+(?:[.,]\d+)?)\s*(?:["″]|'')\s*)?([NSEWO])/gi;

function fromDms(text: string): LatLon | null {
	const found = [...text.matchAll(DMS)];
	if (found.length !== 2) return null;
	let lat: number | null = null;
	let lon: number | null = null;
	for (const [, deg, min = '0', sec = '0', hemi] of found) {
		const n = (s: string) => Number(s.replace(',', '.'));
		const value = n(deg) + n(min) / 60 + n(sec) / 3600;
		const h = hemi.toUpperCase();
		if (h === 'N' || h === 'S') lat = h === 'S' ? -value : value;
		else lon = h === 'W' || h === 'O' ? -value : value;
	}
	return lat !== null && lon !== null && inRange(lat, lon) ? { lat, lon } : null;
}

/** Latitud y longitud de un texto pegado; null si no se reconoce un par válido. */
export function parseCoordinates(text: string): LatLon | null {
	const t = text.trim();
	if (!t) return null;
	const link = t.match(/[@=](-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/);
	if (link) return pair(link[1], link[2]);
	if (t.includes('°')) return fromDms(t);
	const dot = t.match(/^\(?\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*\)?$/);
	if (dot) return pair(dot[1], dot[2]);
	const comma =
		t.match(/^(-?\d+,\d+)\s*[;\s]\s*(-?\d+,\d+)$/) ?? t.match(/^(-?\d+,\d+),\s+(-?\d+,\d+)$/);
	if (comma) return pair(comma[1], comma[2]);
	return null;
}

/** Para mostrar en un campo: hasta 6 decimales (unos 10 cm), con punto. */
export function formatCoordinate(v: number | null | undefined): string {
	return v === null || v === undefined || !Number.isFinite(v)
		? ''
		: String(Math.round(v * 1e6) / 1e6);
}
