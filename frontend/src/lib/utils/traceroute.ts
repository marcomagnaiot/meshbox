// Traceroute como lo muestra la app: la ida y la vuelta salto por salto, con el SNR con que
// cada nodo recibió el paquete del anterior.
import type { Traceroute } from '$lib/api/types';
import { m } from '$lib/paraglide/messages';

/** Un salto que no se anotó en la ruta (firmware viejo o sin la clave del canal). */
export const UNKNOWN_HOP = '!ffffffff';

export interface Hop {
	id: string;
	unknown: boolean;
	/** SNR al recibir del salto anterior; `null` en el primero o si no se conoce. */
	snr: number | null;
}

export interface TracerouteLegs {
	towards: Hop[];
	/** `null` si el destino no informó la vuelta. */
	back: Hop[] | null;
}

function leg(ids: string[], snrs: (number | null)[]): Hop[] {
	return ids.map((id, i) => ({
		id,
		unknown: id === UNKNOWN_HOP,
		snr: i === 0 ? null : (snrs[i - 1] ?? null)
	}));
}

export function tracerouteLegs(tr: Traceroute): TracerouteLegs {
	return {
		towards: leg([tr.from, ...tr.route, tr.to], tr.snr_towards),
		back:
			tr.snr_back.length || tr.route_back.length
				? leg([tr.to, ...tr.route_back, tr.from], tr.snr_back)
				: null
	};
}

/** «directo», «1 salto intermedio» o «N saltos intermedios». */
export function hopsLabel(n: number): string {
	return n <= 0 ? m.trace_direct() : n === 1 ? m.trace_hop_one() : m.trace_hops({ n });
}
