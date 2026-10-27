// Rutas públicas (sección 12.2).
import { api } from './client';
import type {
	AlertPage,
	Link,
	MessagePage,
	NodeDetail,
	NodeList,
	Position,
	Site,
	StatsBreakdown,
	StatsMetric,
	StatsRange,
	StatsSummary,
	TelemetryKind,
	TelemetrySeries,
	TimeSeries,
	Traceroute,
	Waypoint
} from './types';

const V1 = '/api/v1';
const enc = encodeURIComponent;

export const publicApi = {
	site: (signal?: AbortSignal) => api.get<Site>(`${V1}/site`, undefined, signal),
	nodes: (signal?: AbortSignal) => api.get<NodeList>(`${V1}/nodes`, undefined, signal),
	node: (id: string, signal?: AbortSignal) =>
		api.get<NodeDetail>(`${V1}/nodes/${enc(id)}`, undefined, signal),
	positions: (id: string, from: number, to: number, maxPoints = 500, signal?: AbortSignal) =>
		api.get<Position[]>(
			`${V1}/nodes/${enc(id)}/positions`,
			{ from: Math.floor(from), to: Math.ceil(to), max_points: maxPoints },
			signal
		),
	telemetry: (id: string, kind: TelemetryKind, from: number, to: number, signal?: AbortSignal) =>
		api.get<TelemetrySeries>(
			`${V1}/nodes/${enc(id)}/telemetry`,
			{ kind, from: Math.floor(from), to: Math.ceil(to) },
			signal
		),
	nodeLinks: (id: string, signal?: AbortSignal) =>
		api.get<Link[]>(`${V1}/nodes/${enc(id)}/links`, undefined, signal),
	messages: (before?: string | null, limit = 50, signal?: AbortSignal) =>
		api.get<MessagePage>(`${V1}/messages`, { before, limit }, signal),
	alerts: (before?: string | null, limit = 20, signal?: AbortSignal) =>
		api.get<AlertPage>(`${V1}/alerts`, { before, limit }, signal),
	links: (maxAge = 86400, signal?: AbortSignal) =>
		api.get<Link[]>(`${V1}/links`, { max_age: maxAge }, signal),
	traceroutes: (node?: string, limit = 10, signal?: AbortSignal) =>
		api.get<Traceroute[]>(`${V1}/traceroutes`, { node, limit }, signal),
	waypoints: (signal?: AbortSignal) => api.get<Waypoint[]>(`${V1}/waypoints`, undefined, signal),
	summary: (signal?: AbortSignal) =>
		api.get<StatsSummary>(`${V1}/stats/summary`, undefined, signal),
	timeseries: (metric: StatsMetric, range: StatsRange, signal?: AbortSignal) =>
		api.get<TimeSeries>(`${V1}/stats/timeseries`, { metric, range }, signal),
	breakdown: (range: StatsRange, signal?: AbortSignal) =>
		api.get<StatsBreakdown>(`${V1}/stats/breakdown`, { range }, signal),

	// Notificaciones push públicas (solo alertas públicas).
	vapidKey: () => api.get<{ key: string }>(`${V1}/push/vapid-public-key`),
	subscribe: (sub: PushSubscriptionBody) => api.post<unknown>(`${V1}/push/subscriptions`, sub),
	unsubscribe: (sub: PushSubscriptionBody) => api.del<unknown>(`${V1}/push/subscriptions`, sub)
};

export interface PushSubscriptionBody {
	endpoint: string;
	keys: { p256dh: string; auth: string };
}
