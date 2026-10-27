// Tipos de la API. Los recursos salen del OpenAPI (schema.d.ts, `pnpm gen:api`); los eventos
// SSE, el aviso en bloques y las rutas sin modelo de respuesta se escriben a mano.
import type { components } from './schema';

type S = components['schemas'];

export type Node = S['Node'];
export type NodeDetail = S['NodeDetail'];
export type NodeList = S['NodeList'];
export type EnvValues = S['EnvValues'];
export type Message = S['Message'];
export type MessagePage = S['MessagePage'];
export type Alert = S['Alert'];
export type AlertPage = S['AlertPage'];
export type Link = S['Link'];
export type Traceroute = S['Traceroute'];
export type Waypoint = S['Waypoint'];
export type Position = S['Position'];
export type TelemetrySeries = S['TelemetrySeries'];
export type StatsSummary = S['StatsSummary'];
export type TimeSeries = S['TimeSeries'];
export type Thresholds = S['Thresholds'];
export type MapLayers = S['MapLayers'];

export type TelemetryKind = TelemetrySeries['kind'];
export type StatsRange = '24h' | '7d' | '30d';
export type StatsMetric =
	'packets' | 'active_nodes' | 'new_nodes' | 'avg_channel_util' | 'by_portnum' | 'by_hops';

export type BaseLayer = 'dark' | 'light' | 'satellite';

/** Aviso de privacidad en bloques (sin HTML): lo arma el servidor desde Markdown (13.5). */
export type NoticeInline =
	{ t: 'text' | 'strong' | 'em' | 'code'; v: string } | { t: 'link'; v: string; href: string };
export type NoticeBlock =
	{ t: 'p' | 'h2' | 'h3' | 'h4'; c: NoticeInline[] } | { t: 'ul'; c: NoticeInline[][] };

export interface Attribution {
	name: string;
	url?: string;
	text?: string;
}

/** `GET /api/v1/site` con los campos de forma libre tipados. */
export interface Site extends Omit<
	S['Site'],
	'notice' | 'attributions' | 'features' | 'center' | 'bounds' | 'layers'
> {
	center: [number, number];
	bounds?: [number, number, number, number] | null;
	layers: MapLayers & { default: BaseLayer };
	features: SiteFeatures;
	notice: NoticeBlock[];
	attributions: Attribution[];
}

export interface SiteFeatures {
	push: boolean;
	activity: boolean;
	links: boolean;
	waypoints: boolean;
	show_inactive: boolean;
	tx: boolean;
	[key: string]: boolean;
}

/** `GET /api/v1/stats/breakdown` (sin modelo en el OpenAPI). */
export interface StatsBreakdown {
	range: StatsRange;
	by_portnum: Record<string, number>;
	by_hops: Record<string, number>;
	relays: RelayInfo[];
}

export interface RelayInfo {
	relay: string;
	count: number;
	candidates: { id: string; name: string | null; is_infra: boolean }[];
}

export type NodeStatus = 'active' | 'recent' | 'late' | 'inactive';

// ------------------------------------------------------------------ eventos SSE (12.3)

export interface SeqEvent {
	seq: number;
}

export type NodeEvent = Node & SeqEvent;
export interface NodeRemoveEvent extends SeqEvent {
	id: string;
}
export interface PositionEvent extends SeqEvent {
	id: string;
	lat: number;
	lon: number;
	alt: number | null;
	precision_m: number | null;
	ts: number;
}
export interface TelemetryEvent extends SeqEvent {
	id: string;
	kind: TelemetryKind;
	values: Record<string, number | null>;
	ts: number;
}
export type MessageEvent = Message & SeqEvent;
export interface MessageModerationEvent extends SeqEvent {
	pk: number;
}
export type AlertEvent = Alert & SeqEvent;
export type LinkEvent = Link & SeqEvent;
export type StatsEvent = StatsSummary & SeqEvent;
export type WaypointEvent = Waypoint & SeqEvent & { deleted?: boolean };
/** Actividad en vivo: sin `seq` (no es estado). */
export interface ActivityEvent {
	portnum: string | null;
	from: string;
	to: string;
	hops: number | null;
	snr: number | null;
	gateway: string | null;
	ts: number;
}

export interface LiveEventMap {
	node: NodeEvent;
	node_remove: NodeRemoveEvent;
	position: PositionEvent;
	telemetry: TelemetryEvent;
	message: MessageEvent;
	message_remove: MessageModerationEvent;
	message_restore: MessageModerationEvent;
	alert: AlertEvent;
	link: LinkEvent;
	stats: StatsEvent;
	waypoint: WaypointEvent;
	activity: ActivityEvent;
}

export type LiveEventName = keyof LiveEventMap;

export type LiveEvent = {
	[K in LiveEventName]: { name: K; data: LiveEventMap[K] };
}[LiveEventName];

// ------------------------------------------------------------------ administración

export type AdminRole = 'admin' | 'operator';

export interface AdminSession {
	user_id: number;
	username: string;
	role: AdminRole;
	csrf_token: string;
	expires_at: number;
	must_change_password: boolean;
	idle_timeout_s?: number;
	mode?: 'appliance' | 'shared';
	server?: 'public' | 'lan' | 'remote';
	insecure_transport?: boolean;
	tx_enabled?: boolean;
}
