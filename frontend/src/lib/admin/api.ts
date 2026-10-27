// Cliente de la API de administración (12.4), por área del panel. Toda petición que modifica
// lleva X-CSRF-Token (lo agrega el cliente) y queda en la auditoría del backend.
import { api, request, requestBlob, type QueryValue } from '$lib/api/client';
import type {
	AdminMessage,
	AdminNode,
	AdminPrivacy,
	AdminSessionRow,
	AdminSite,
	AdminUser,
	AlertChannels,
	AlertRule,
	AdminAlertEvent,
	AuditEntry,
	BackupFile,
	CloudflareStatus,
	CloudflareZone,
	ConnectorConfig,
	JsonSchema,
	RuleKind,
	ConnectorTest,
	LogEntry,
	LogUnit,
	MqttAccount,
	MqttSecret,
	MqttStatus,
	NetworkStatus,
	PacketDetail,
	PacketPage,
	PluginInfo,
	PluginList,
	PrivJob,
	ProvisionStep,
	RadioChannel,
	Recording,
	Schemas,
	SerialPortInfo,
	SetupState,
	SetupVerify,
	SiteSettings,
	SystemMetrics,
	SystemStatus,
	TileJobStatus,
	TilesStatus,
	UpdatesStatus,
	WifiScan
} from './types';

const A = '/api/v1/admin';
const enc = encodeURIComponent;

export interface PacketFilters {
	portnum?: string;
	from?: string;
	to?: string;
	channel?: string;
	gateway?: string;
	min_snr?: number | null;
	max_hops?: number | null;
	q?: string;
}

function packetQuery(f: PacketFilters): Record<string, QueryValue> {
	return {
		portnum: f.portnum,
		from: f.from,
		to: f.to,
		channel: f.channel,
		gateway: f.gateway,
		min_snr: f.min_snr ?? undefined,
		max_hops: f.max_hops ?? undefined,
		q: f.q
	};
}

export const system = {
	status: (signal?: AbortSignal) => api.get<SystemStatus>(`${A}/system/status`, undefined, signal),
	metrics: (minutes = 60) => api.get<SystemMetrics>(`${A}/system/metrics`, { minutes }),
	logs: (
		q: { unit: LogUnit; lines?: number; since?: string; level?: string; q?: string },
		signal?: AbortSignal
	) => api.get<{ unit: string; entries: LogEntry[] }>(`${A}/system/logs`, q, signal),
	hostname: (name: string) => api.put<{ hostname: string }>(`${A}/system/hostname`, { name }),
	timezone: (tz: string) =>
		api.put<{ timezone: string; system_changed: boolean }>(`${A}/system/timezone`, { tz }),
	reboot: () => api.post<Record<string, unknown>>(`${A}/system/reboot`, { confirm: true }),
	shutdown: () => api.post<Record<string, unknown>>(`${A}/system/shutdown`, { confirm: true }),
	restartService: (name: 'meshbox' | 'mosquitto' | 'meshbox-cloudflared') =>
		api.post<Record<string, unknown>>(`${A}/system/services/${name}/restart`)
};

export const network = {
	status: () => api.get<NetworkStatus>(`${A}/network/status`),
	scan: () => api.get<WifiScan>(`${A}/network/wifi/scan`),
	connect: (ssid: string, psk: string) =>
		api.post<{ job: string; state: string }>(`${A}/network/wifi/connect`, {
			ssid,
			psk,
			confirm: true
		}),
	forget: (ssid: string) =>
		api.del<{ ssid: string; deleted: number }>(`${A}/network/wifi/${enc(ssid)}`),
	hotspot: (enabled: boolean) =>
		api.post<Record<string, unknown>>(`${A}/network/hotspot`, { enabled })
};

export const connectors = {
	list: () => api.get<{ connectors: ConnectorConfig[] }>(`${A}/connectors`),
	create: (body: ConnectorBody) => api.post<ConnectorConfig>(`${A}/connectors`, body),
	update: (id: string, body: ConnectorBody) =>
		api.put<ConnectorConfig>(`${A}/connectors/${enc(id)}`, body),
	remove: (id: string) => api.del<void>(`${A}/connectors/${enc(id)}`),
	restart: (id: string) => api.post<{ ok: boolean }>(`${A}/connectors/${enc(id)}/restart`),
	release: (id: string) =>
		api.post<{ ok: boolean; state: string }>(`${A}/connectors/${enc(id)}/release`),
	test: (id: string) => api.post<ConnectorTest>(`${A}/connectors/${enc(id)}/test`),
	serialPorts: () => api.get<{ ports: SerialPortInfo[] }>(`${A}/connectors/serial-ports`),
	node: (id: string) => api.get<Record<string, unknown>>(`${A}/connectors/${enc(id)}/node`),
	rebootNode: (id: string) =>
		api.post<{ ok: boolean; message: string }>(`${A}/connectors/${enc(id)}/reboot-node`, {
			confirm: true
		}),
	record: (id: string, duration_s: number) =>
		api.post<{ ok: boolean; file: string; until: number }>(`${A}/connectors/${enc(id)}/record`, {
			duration_s
		}),
	recordings: () => api.get<{ files: Recording[] }>(`${A}/connectors/recordings`)
};

export type ConnectorBody =
	Schemas['MqttIn'] | Schemas['SerialIn'] | Schemas['TcpIn'] | Schemas['ReplayIn'];

export const mqtt = {
	accounts: () =>
		api.get<{ accounts: MqttAccount[]; root: string; events_prefix: string }>(`${A}/mqtt/accounts`),
	create: (body: Schemas['AccountIn']) => api.post<MqttSecret>(`${A}/mqtt/accounts`, body),
	rotate: (username: string, serial_port?: string) =>
		api.post<MqttSecret>(`${A}/mqtt/accounts/${enc(username)}/rotate`, { serial_port }),
	remove: (username: string) => api.del<void>(`${A}/mqtt/accounts/${enc(username)}`),
	acl: () => api.get<{ acl: string; payload: Record<string, unknown> }>(`${A}/mqtt/acl`),
	status: () => api.get<MqttStatus>(`${A}/mqtt/status`),
	out: (enabled: boolean, prefix: string) =>
		api.put<MqttStatus['mqtt_out']>(`${A}/mqtt/out`, { enabled, prefix })
};

export const channels = {
	list: () => api.get<{ channels: RadioChannel[] }>(`${A}/channels`),
	create: (body: Schemas['meshbox__api__admin__channels__ChannelIn']) =>
		api.post<RadioChannel>(`${A}/channels`, body),
	update: (id: number, body: Schemas['meshbox__api__admin__channels__ChannelIn']) =>
		api.put<RadioChannel>(`${A}/channels/${id}`, body),
	remove: (id: number) => api.del<void>(`${A}/channels/${id}`)
};

export const packets = {
	list: (f: PacketFilters, before?: string | null, limit = 200, signal?: AbortSignal) =>
		api.get<PacketPage>(`${A}/packets`, { ...packetQuery(f), before, limit }, signal),
	get: (pk: number) => api.get<PacketDetail>(`${A}/packets/${pk}`),
	exportUrl: (format: 'csv' | 'jsonl', f: PacketFilters) => {
		const params = new URLSearchParams({ format });
		for (const [k, v] of Object.entries(packetQuery(f))) {
			if (
				v !== undefined &&
				v !== null &&
				v !== '' &&
				k !== 'min_snr' &&
				k !== 'max_hops' &&
				k !== 'q'
			)
				params.set(k, String(v));
		}
		return `${A}/packets/export?${params}`;
	}
};

export const nodes = {
	list: () => api.get<{ nodes: AdminNode[]; seq: number }>(`${A}/nodes`),
	patch: (id: string, body: Schemas['NodePatch']) =>
		api.patch<AdminNode>(`${A}/nodes/${enc(id)}`, body),
	purge: (id: string) =>
		request<{ deleted: Record<string, number> }>(`${A}/nodes/${enc(id)}/history`, {
			method: 'DELETE',
			body: { confirm: true }
		})
};

export const messages = {
	list: (before?: string | null, limit = 200) =>
		api.get<{ messages: AdminMessage[]; next: string | null }>(`${A}/messages`, { before, limit }),
	moderate: (pk: number, hidden: boolean) =>
		api.patch<{ pk: number; hidden: boolean }>(`${A}/messages/${pk}`, { hidden })
};

export const alerts = {
	rules: () => api.get<{ rules: AlertRule[] }>(`${A}/alerts/rules`),
	/** JSON Schema de RuleIn y de los parámetros de cada tipo (los modelos del servidor, 18.3). */
	rulesSchema: () =>
		api.get<{ rule: JsonSchema; params: Record<RuleKind, JsonSchema> }>(`${A}/alerts/rules/schema`),
	createRule: (body: Schemas['RuleIn']) => api.post<AlertRule>(`${A}/alerts/rules`, body),
	updateRule: (id: number, body: Schemas['RuleIn']) =>
		api.put<AlertRule>(`${A}/alerts/rules/${id}`, body),
	deleteRule: (id: number) => api.del<void>(`${A}/alerts/rules/${id}`),
	testRule: (id: number) => api.post<Record<string, unknown>>(`${A}/alerts/rules/${id}/test`),
	events: (before?: string | null, limit = 50) =>
		api.get<{ events: AdminAlertEvent[]; next: string | null }>(`${A}/alerts/events`, {
			before,
			limit
		}),
	ack: (id: number) => api.post<{ id: number; ack_by: string }>(`${A}/alerts/events/${id}/ack`),
	channels: () => api.get<AlertChannels>(`${A}/alerts/channels`),
	saveChannels: (body: Schemas['ChannelsIn']) =>
		api.put<AlertChannels>(`${A}/alerts/channels`, body),
	testChannel: (channel: string) =>
		api.post<{ ok: boolean; error: string | null }>(`${A}/alerts/channels/${enc(channel)}/test`),
	webhookSecret: (id: string) =>
		api.get<{ id: string; secret: string }>(`${A}/alerts/webhooks/${enc(id)}/secret`),
	subscribe: (body: Schemas['AdminSubIn']) =>
		api.post<{ ok: boolean; scope: string }>(`${A}/alerts/push/subscriptions`, body)
};

export const site = {
	get: () => api.get<AdminSite>(`${A}/site`),
	put: (body: Omit<SiteSettings, 'logo'>) => api.put<{ site: SiteSettings }>(`${A}/site`, body),
	uploadLogo: (file: Blob) =>
		request<{ logo: string }>(`${A}/site/logo`, { method: 'POST', raw: file }),
	deleteLogo: () => api.del<void>(`${A}/site/logo`),
	tiles: () => api.get<TilesStatus>(`${A}/tiles/status`),
	downloadTiles: (bbox: number[], maxzoom: number, source?: string | null) =>
		api.post<{ job: TileJobStatus; source: string }>(`${A}/tiles/download`, {
			bbox,
			maxzoom,
			source: source || undefined
		}),
	deleteTiles: () => api.del<void>(`${A}/tiles`),
	privacy: () => api.get<AdminPrivacy>(`${A}/privacy`),
	putPrivacy: (body: Pick<AdminPrivacy, 'privacy' | 'retention'>) =>
		api.put<Pick<AdminPrivacy, 'privacy' | 'retention'>>(`${A}/privacy`, body),
	purge: () =>
		api.post<{ deleted: Record<string, number> }>(`${A}/privacy/purge`, { confirm: true })
};

export const cloudflare = {
	status: (probe = false) => api.get<CloudflareStatus>(`${A}/cloudflare/status`, { probe }),
	token: (token: string, public_hostname: string) =>
		api.post<{ ok: boolean; service: Record<string, unknown>; hint: string }>(
			`${A}/cloudflare/token`,
			{ token, public_hostname }
		),
	verify: (api_token: string, account_id?: string) =>
		api.post<{
			token: { status: string; kind?: string; expires_on?: string | null };
			zones: CloudflareZone[];
		}>(`${A}/cloudflare/api/verify`, { api_token, account_id: account_id || undefined }),
	zones: () => api.get<{ zones: CloudflareZone[] }>(`${A}/cloudflare/api/zones`),
	provision: (body: Schemas['ProvisionIn']) =>
		api.post<{
			ok: boolean;
			steps: ProvisionStep[];
			site_check: CloudflareStatus['site_check'];
			restart_needed_for_admin: boolean;
		}>(`${A}/cloudflare/api/provision`, body),
	access: (emails: string[]) =>
		api.post<{ ok: boolean; team_domain: string; aud: string; note: string }>(
			`${A}/cloudflare/access`,
			{ emails }
		),
	disconnect: (delete_dns: boolean, delete_tunnel: boolean) =>
		api.post<{ ok: boolean; done: string[] }>(`${A}/cloudflare/disconnect`, {
			confirm: true,
			delete_dns,
			delete_tunnel
		})
};

export const plugins = {
	list: () => api.get<PluginList>(`${A}/plugins`),
	update: (id: string, body: { enabled?: boolean; settings?: Record<string, unknown> }) =>
		api.put<PluginInfo>(`${A}/plugins/${enc(id)}`, body),
	logs: (id: string) =>
		api.get<{ logs: { ts: number; level: string; msg: string }[] }>(`${A}/plugins/${enc(id)}/logs`)
};

export interface TxPreview {
	preview: Record<string, unknown>;
	confirm_required: true;
}

export const tx = {
	text: (text: string, channel_index: number, confirm: boolean) =>
		api.post<TxPreview | { ok: boolean; packet_id?: number }>(`${A}/tx/text`, {
			text,
			channel_index,
			confirm
		}),
	traceroute: (node: string, hop_limit: number, channel_index: number, confirm: boolean) =>
		api.post<TxPreview | { ok: boolean; note?: string; error?: string }>(`${A}/tx/traceroute`, {
			node,
			hop_limit,
			channel_index,
			confirm
		})
};

export const users = {
	list: () => api.get<{ users: AdminUser[] }>(`${A}/users`),
	create: (body: Schemas['UserIn']) =>
		api.post<{ id: number; username: string; role: string }>(`${A}/users`, body),
	update: (id: number, body: Schemas['UserPatch']) => api.put<AdminUser>(`${A}/users/${id}`, body),
	remove: (id: number) => api.del<void>(`${A}/users/${id}`),
	sessions: () => api.get<{ sessions: AdminSessionRow[] }>(`${A}/sessions`),
	closeSession: (id: string) => api.del<void>(`${A}/sessions/${enc(id)}`),
	audit: (before?: number | null, action?: string, limit = 200) =>
		api.get<{ entries: AuditEntry[]; next: number | null; now: number }>(`${A}/audit`, {
			before,
			action,
			limit
		})
};

export const backups = {
	list: () =>
		api.get<{ backups: BackupFile[]; db: { db: number; db_wal: number; db_shm: number } }>(
			`${A}/backups`
		),
	create: () => api.post<BackupFile>(`${A}/backups`),
	downloadUrl: (name: string) => `${A}/backups/${enc(name)}`,
	restore: (name: string) =>
		api.post<{ ok: boolean; restored: string; safety_backup?: string }>(`${A}/backups/restore`, {
			name,
			confirm: true
		}),
	uploadAndRestore: (file: Blob) =>
		request<{ ok: boolean; restored: string }>(`${A}/backups/upload`, {
			method: 'POST',
			raw: file,
			contentType: 'application/gzip',
			query: { confirm: 1 }
		}),
	exportConfig: (include_secrets: boolean, password?: string) =>
		requestBlob(`${A}/config/export`, {
			method: 'POST',
			body: { include_secrets, password: password || undefined },
			filename: 'meshbox-config.json'
		}),
	importConfig: (data: Record<string, unknown>, password?: string) =>
		api.post<{ ok: boolean; restart_recommended: boolean }>(`${A}/config/import`, {
			data,
			password: password || undefined,
			confirm: true
		})
};

export const updates = {
	status: (force = false) => api.get<UpdatesStatus>(`${A}/updates`, { force }),
	install: (version: string) =>
		api.post<{ job: string; state: string }>(`${A}/updates/install`, { version, confirm: true }),
	job: (job: string) => api.get<PrivJob>(`${A}/updates/jobs/${enc(job)}`),
	rollback: () =>
		api.post<{ job: string; state: string }>(`${A}/updates/rollback`, { confirm: true }),
	settings: (auto_check: boolean, source?: string | null) =>
		api.put<{ auto_check: boolean; source: string }>(`${A}/updates/settings`, {
			auto_check,
			source: source || undefined
		})
};

const S = '/api/v1/setup';

/** Asistente de primer uso (18.1). El código va en X-Setup-Code hasta crear el administrador. */
export const setup = {
	state: () => api.get<SetupState>(`${S}/state`),
	post: <T = Record<string, unknown>>(path: string, body?: unknown, code?: string | null) =>
		request<T>(`${S}/${path}`, {
			method: 'POST',
			body: body ?? {},
			headers: code ? { 'X-Setup-Code': code } : undefined
		}),
	verify: () => api.get<SetupVerify>(`${S}/verify`)
};
