// Cliente Meshtastic del panel (ADR 0015): tipos y llamadas de /api/v1/admin/radio. Las
// respuestas salen de la placa tal como las da la librería, sin modelo en el OpenAPI.
import { api, request } from '$lib/api/client';
import { ApiError } from '$lib/api/client';

const R = '/api/v1/admin/radio';
const enc = encodeURIComponent;

/** Valor que el servidor muestra en lugar de una clave guardada (no cambia si se reenvía). */
export const MASK = '********';

export interface Board {
	id: string;
	kind: 'serial' | 'tcp';
	via: 'USB' | 'TCP';
	state: string;
	gateway_id: string | null;
	long_name: string | null;
	short_name: string | null;
	hw_model: string | null;
}

export interface BoardChannel {
	index: number;
	role: 'DISABLED' | 'PRIMARY' | 'SECONDARY';
	name: string;
	custom_name: boolean;
	/** none = sin cifrar, default = clave pública conocida, simple = clave corta, secret = propia. */
	psk: 'none' | 'default' | 'simple' | 'secret';
	uplink: boolean;
	downlink: boolean;
	position_precision: number;
	muted: boolean;
}

export interface BoardStatus {
	id: string;
	via: 'USB' | 'TCP';
	gateway_id: string | null;
	node: {
		id: string | null;
		long_name: string | null;
		short_name: string | null;
		hw_model: string | null;
		role: string;
		firmware: string | null;
		region: string;
		preset: string;
		preset_name: string | null;
		tx_power: number;
		hop_limit: number;
		tx_enabled: boolean;
		wifi_enabled: boolean;
		bluetooth_enabled: boolean;
		power_saving: boolean;
		fixed_position: boolean;
		mqtt_enabled: boolean;
		map_reporting: boolean;
		has_wifi: boolean | null;
		has_bluetooth: boolean | null;
		/** Clave pública de la placa: la que se carga en los nodos a administrar (ADR 0017). */
		public_key: string | null;
	};
	metrics: {
		batteryLevel?: number;
		voltage?: number;
		channelUtilization?: number;
		airUtilTx?: number;
		uptimeSeconds?: number;
	};
	position: { latitude?: number; longitude?: number; altitude?: number; time?: number };
	nodes_in_db: number;
	channels: BoardChannel[];
	position_refreshed_at: number | null;
	local_stats: Record<string, number> | null;
	tx_enabled: boolean;
	remote: boolean;
}

export interface BoardNode {
	num: number;
	id: string | null;
	long_name: string | null;
	short_name: string | null;
	hw_model: string | null;
	role: string;
	has_pki: boolean;
	last_heard: number | null;
	snr: number | null;
	hops: number | null;
	via_mqtt: boolean;
	favorite: boolean;
	channel: number;
	lat: number | null;
	lon: number | null;
	precision_bits: number | null;
	metrics: { batteryLevel?: number; voltage?: number };
	is_self: boolean;
}

/** Mensaje del historial de una placa (ADR 0016): queda en la base de la Pi. */
export interface BoardMessage {
	/** Número en el historial: crece siempre, sirve para pedir lo nuevo y marcar lo leído. */
	seq: number;
	id: number | null;
	ts: number;
	direction: 'in' | 'out';
	from: string | null;
	to: string;
	dm: boolean;
	/** Conversación: `ch:<índice>` o `dm:<nodo>`. */
	conv: string;
	channel_index: number;
	channel: string | null;
	text: string;
	snr: number | null;
	rssi: number | null;
	hops: number | null;
	reply_id: number | null;
	emoji: boolean;
	/** enviado → retransmitido (otro nodo lo repitió) → entregado (confirmó el destino), o error. */
	status: string | null;
}

/** Un día de batería (placas con panel solar): ver store/battery.py. */
export interface BatteryDay {
	date: string;
	samples: number;
	complete: boolean;
	/** Mínimo antes de empezar a cargar (al amanecer). */
	dawn_v: number | null;
	dawn_at: number | null;
	dawn_pct: number | null;
	max_v: number | null;
	/** Horas con el cargador activo (la placa informa 101). */
	charge_h: number;
	/** Llegó a la meseta de carga completa al menos una hora. */
	full: boolean;
	charge_start: number | null;
	charge_end: number | null;
	/** Voltaje al cerrar el día (21 a 24, sin sol). */
	evening_v: number | null;
	night_drain_mv_h: number | null;
	/** Cuenta para la tendencia (es posterior al último corte largo). */
	in_trend: boolean;
}

export interface BatteryTrend {
	node: string;
	days: number;
	samples: number;
	from: number | null;
	to: number | null;
	per_day: BatteryDay[];
	trend: {
		dawn_slope_v_day: number | null;
		evening_delta_v: number | null;
		full_days: number;
		complete_days: number;
		verdict: 'recupera' | 'estable' | 'deficit' | 'sin_datos';
		days_to_cutoff: number | null;
		cutoff_v: number;
		/** Primera muestra después de un corte de más de 6 horas: la tendencia cuenta desde ahí. */
		since: number | null;
	};
}

export interface MessagePage {
	messages: BoardMessage[];
	/** Quedan mensajes anteriores sin traer. */
	more: boolean;
	/** Lo leído por este usuario en cada conversación (número de historial). */
	reads: Record<string, number>;
	channels: Record<string, string>;
	board: string | null;
	retention_days: number;
}

/** Recibidos sin leer de una conversación. */
export function unreadCount(
	msgs: readonly BoardMessage[],
	reads: Record<string, number>,
	conv: string
): number {
	const from = reads[conv] ?? 0;
	return msgs.filter((x) => x.direction === 'in' && x.conv === conv && x.seq > from).length;
}

export type FieldType = 'bool' | 'enum' | 'string' | 'float' | 'int' | 'list' | 'bytes' | 'object';

export interface ConfigField {
	name: string;
	type: FieldType;
	danger: boolean;
	secret: boolean;
	readonly: boolean;
	value?: unknown;
	options?: string[];
	min?: number;
	max?: number;
	max_length?: number;
	fields?: ConfigField[];
}

export interface ConfigSection {
	name: string;
	kind: 'config' | 'module';
	writable: boolean;
	danger: boolean;
	fields: ConfigField[];
}

export interface BoardBackup {
	name: string;
	size: number;
	created: number;
}

export interface WriteResult {
	changed: string[];
	danger?: string[];
	backup: string | null;
}

/** Lo que la placa sabe de un nodo a administrar a distancia (no transmite). */
export interface RemoteInfo {
	node: string;
	known: boolean;
	long_name: string | null;
	short_name: string | null;
	hw_model: string | null;
	role: string;
	has_pki: boolean;
	last_heard: number | null;
	hops: number | null;
	snr: number | null;
	via_mqtt: boolean;
	board: string | null;
	board_public_key: string | null;
	/** La placa tiene un canal "admin" (administración heredada, sin PKI). */
	admin_channel: boolean;
	sections: Omit<ConfigSection, 'fields'>[];
	remote: boolean;
}

export interface RemoteProbe {
	firmware: string;
	role: string | number;
	hw_model: string | number;
	has_wifi: boolean;
	has_bluetooth: boolean;
	/** Lo que tardó la respuesta por la malla. */
	seconds: number;
}

export interface RemoteSection extends ConfigSection {
	read_at: number;
}

export interface RemoteWriteResult extends WriteResult {
	/** Se volvió a leer y coincide; `null` si el nodo no contestó (se está reiniciando). */
	verified: boolean | null;
	mismatch: string[];
	/** La sección releída para verificar (sin otro pedido por la malla). */
	section: RemoteSection | null;
}

export interface ChannelBody {
	name?: string;
	/** keep, default, none, random o la clave en base64. */
	psk?: string;
	uplink?: boolean;
	downlink?: boolean;
	position_precision?: number;
	muted?: boolean;
}

const B = (cid: string) => `${R}/${enc(cid)}`;

export const radioApi = {
	boards: () => api.get<{ boards: Board[]; remote: boolean }>(R),
	status: (cid: string, signal?: AbortSignal) => api.get<BoardStatus>(B(cid), undefined, signal),
	nodes: (cid: string, signal?: AbortSignal) =>
		api.get<{ nodes: BoardNode[] }>(`${B(cid)}/nodes`, undefined, signal),
	/** Sin `after`: los últimos `limit` (o los anteriores a `before`); con `after`, lo nuevo. */
	messages: (
		cid: string,
		q: { after?: number; before?: number; limit?: number },
		signal?: AbortSignal
	) => api.get<MessagePage>(`${B(cid)}/messages`, q, signal),
	markRead: (cid: string, conv: string, seq: number) =>
		api.put<{ conv: string; seq: number }>(`${B(cid)}/reads`, { conv, seq }),
	clearMessages: (cid: string) =>
		request<{ deleted: number }>(`${B(cid)}/messages`, {
			method: 'DELETE',
			body: { confirm: true }
		}),
	send: (cid: string, text: string, channel_index: number, to: string | null) =>
		api.post<{ ok: boolean; packet_id: number }>(`${B(cid)}/messages`, {
			text,
			channel_index,
			to: to ?? undefined,
			confirm: true
		}),
	requestPosition: (cid: string, node: string, channel_index = 0) =>
		api.post<{ answered: boolean; detail?: string }>(`${B(cid)}/request-position`, {
			node,
			channel_index
		}),
	traceroute: (cid: string, node: string, hop_limit: number, channel_index = 0) =>
		api.post<{ ok: boolean; note: string }>(`${B(cid)}/traceroute`, {
			node,
			hop_limit,
			channel_index
		}),
	config: (cid: string) =>
		api.get<{ sections: ConfigSection[]; remote: boolean }>(`${B(cid)}/config`),
	writeSection: (
		cid: string,
		section: string,
		values: Record<string, unknown>,
		confirm_danger = false
	) => api.put<WriteResult>(`${B(cid)}/config/${enc(section)}`, { values, confirm_danger }),
	writeChannel: (cid: string, index: number, body: ChannelBody, confirm_danger = false) =>
		api.put<WriteResult>(`${B(cid)}/channels/${index}`, { ...body, confirm_danger }),
	addChannel: (cid: string, body: ChannelBody) =>
		api.post<{ index: number; backup: string }>(`${B(cid)}/channels`, body),
	deleteChannel: (cid: string, index: number) =>
		request<{ deleted: number; backup: string }>(`${B(cid)}/channels/${index}`, {
			method: 'DELETE',
			body: { confirm_danger: true }
		}),
	owner: (cid: string, long_name: string, short_name: string) =>
		api.put<{ long_name: string; short_name: string; backup: string }>(`${B(cid)}/owner`, {
			long_name,
			short_name
		}),
	refreshPosition: (cid: string) =>
		api.post<{ lat: number; lon: number }>(`${B(cid)}/position/refresh`),
	/** Tendencia de carga de la batería de un nodo (cualquiera, no solo las placas). */
	battery: (nodeId: string, days: number, signal?: AbortSignal) =>
		api.get<BatteryTrend>(`/api/v1/admin/nodes/${enc(nodeId)}/battery`, { days }, signal),
	/** Posición fija de la placa (la usa en lugar del GPS). */
	setPosition: (cid: string, lat: number, lon: number, alt: number) =>
		api.put<{ fixed: boolean }>(`${B(cid)}/position`, { lat, lon, alt }),
	removePosition: (cid: string) => api.del<Record<string, never>>(`${B(cid)}/position`),
	reboot: (cid: string) =>
		api.post<{ ok: boolean; message: string }>(`${B(cid)}/reboot`, { confirm: true }),
	shutdown: (cid: string) =>
		api.post<{ ok: boolean; message: string }>(`${B(cid)}/shutdown`, { confirm_danger: true }),
	backups: (cid: string) => api.get<{ backups: BoardBackup[] }>(`${B(cid)}/backups`),
	createBackup: (cid: string) => api.post<{ name: string }>(`${B(cid)}/backups`),
	backupUrl: (cid: string, name: string) => `${B(cid)}/backups/${enc(name)}`,
	// Administración remota de nodos propios por la malla (ADR 0017): cada pedido transmite.
	remoteInfo: (cid: string, node: string, signal?: AbortSignal) =>
		api.get<RemoteInfo>(`${B(cid)}/remote/${enc(node)}`, undefined, signal),
	remoteProbe: (cid: string, node: string) =>
		api.post<RemoteProbe>(`${B(cid)}/remote/${enc(node)}/probe`),
	remoteRead: (cid: string, node: string, section: string) =>
		api.get<RemoteSection>(`${B(cid)}/remote/${enc(node)}/config/${enc(section)}`),
	remoteWrite: (
		cid: string,
		node: string,
		section: string,
		values: Record<string, unknown>,
		confirm_danger = false
	) =>
		api.put<RemoteWriteResult>(`${B(cid)}/remote/${enc(node)}/config/${enc(section)}`, {
			values,
			confirm_danger
		}),
	remoteOwner: (cid: string, node: string, long_name: string, short_name: string) =>
		api.put<{ long_name: string; short_name: string }>(`${B(cid)}/remote/${enc(node)}/owner`, {
			long_name,
			short_name
		}),
	remotePosition: (cid: string, node: string, lat: number, lon: number, alt: number) =>
		api.put<{ fixed: boolean }>(`${B(cid)}/remote/${enc(node)}/position`, { lat, lon, alt }),
	remoteReboot: (cid: string, node: string) =>
		api.post<{ ok: boolean; seconds: number }>(`${B(cid)}/remote/${enc(node)}/reboot`, {
			confirm: true
		}),
	restore: (cid: string, name: string) =>
		api.post<{ sections: string[]; channels: number[]; owner: boolean; backup_before: string }>(
			`${B(cid)}/backups/${enc(name)}/restore`,
			{ confirm_danger: true }
		)
};

/** Campos peligrosos que el servidor pide confirmar (409 danger_confirmation_required). */
export function dangerFields(err: unknown): string[] | null {
	if (
		err instanceof ApiError &&
		err.status === 409 &&
		err.problem.code === 'danger_confirmation_required'
	) {
		const fields = err.problem.fields;
		return Array.isArray(fields) ? fields.map(String) : [];
	}
	return null;
}

/** Nombre legible de un campo de la configuración (`screen_on_secs` → `Screen on secs`). */
export function fieldLabel(name: string): string {
	const s = name.replace(/_/g, ' ');
	return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Valores actuales de una sección, por ruta (`map_report_settings.publish_interval_secs`). */
export function sectionValues(fields: ConfigField[], prefix = ''): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	for (const f of fields) {
		if (f.type === 'object')
			Object.assign(out, sectionValues(f.fields ?? [], `${prefix}${f.name}.`));
		else out[`${prefix}${f.name}`] = f.value;
	}
	return out;
}

/** Valores a enviar: solo lo que cambió, con los objetos anidados como el servidor los espera. */
export function changedValues(
	fields: ConfigField[],
	original: Record<string, unknown>,
	draft: Record<string, unknown>,
	prefix = ''
): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	for (const f of fields) {
		if (f.readonly || f.type === 'list' || f.type === 'bytes') continue;
		const path = `${prefix}${f.name}`;
		if (f.type === 'object') {
			const nested = changedValues(f.fields ?? [], original, draft, `${path}.`);
			if (Object.keys(nested).length) out[f.name] = nested;
			continue;
		}
		const a = original[path];
		const b = draft[path];
		if (f.secret && (b === MASK || b === '')) continue;
		if (b === null || b === undefined || b === a) continue;
		out[f.name] = b;
	}
	return out;
}

/**
 * Radio de la posición que comparte un canal según su precisión en bits (tabla de la app:
 * 13 → 2,9 km, 16 → 364 m, 19 → 45 m). 0 = no la comparte (null), 32 = exacta (0).
 */
export function precisionMeters(bits: number): number | null {
	if (bits <= 0) return null;
	if (bits >= 32) return 0;
	return bits < 10 ? 23_300 * 2 ** (10 - bits) : Math.round(23_300 / 2 ** (bits - 10));
}

/** Tipo de clave del canal en palabras. */
export function pskKind(c: Pick<BoardChannel, 'psk'>): 'public' | 'private' | 'open' {
	return c.psk === 'secret' ? 'private' : c.psk === 'none' ? 'open' : 'public';
}
