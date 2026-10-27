// Geometría: distancias, círculos de incertidumbre y límites.

const R = 6371008.8; // radio medio terrestre en metros

export function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
	const toRad = Math.PI / 180;
	const dLat = (lat2 - lat1) * toRad;
	const dLon = (lon2 - lon1) * toRad;
	const a =
		Math.sin(dLat / 2) ** 2 +
		Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
	return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Polígono (anillo cerrado [lon, lat]) que aproxima un círculo de `meters` de radio. */
export function circleRing(
	lat: number,
	lon: number,
	meters: number,
	steps = 48
): [number, number][] {
	const ring: [number, number][] = [];
	const dLat = (meters / R) * (180 / Math.PI);
	const dLon = dLat / Math.max(0.01, Math.cos((lat * Math.PI) / 180));
	for (let i = 0; i <= steps; i++) {
		const t = (i / steps) * 2 * Math.PI;
		ring.push([lon + dLon * Math.cos(t), lat + dLat * Math.sin(t)]);
	}
	return ring;
}

export type LngLatBounds = [[number, number], [number, number]];

/** Límites [[oeste, sur], [este, norte]] de una lista de puntos [lon, lat]. */
export function boundsOf(points: [number, number][]): LngLatBounds | null {
	if (points.length === 0) return null;
	let w = Infinity,
		s = Infinity,
		e = -Infinity,
		n = -Infinity;
	for (const [lon, lat] of points) {
		if (lon < w) w = lon;
		if (lon > e) e = lon;
		if (lat < s) s = lat;
		if (lat > n) n = lat;
	}
	return [
		[w, s],
		[e, n]
	];
}

/** Punto intermedio entre dos posiciones (para el trazo animado de actividad). */
export function lerp(a: [number, number], b: [number, number], t: number): [number, number] {
	return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

export function isValidLatLon(lat: unknown, lon: unknown): lat is number {
	return (
		typeof lat === 'number' &&
		typeof lon === 'number' &&
		Number.isFinite(lat) &&
		Number.isFinite(lon) &&
		Math.abs(lat) <= 90 &&
		Math.abs(lon) <= 180 &&
		!(lat === 0 && lon === 0)
	);
}
