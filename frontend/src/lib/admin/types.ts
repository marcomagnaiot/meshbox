// Respuestas de la API de administración (12.4). El backend responde JSON sin modelo de
// respuesta en OpenAPI, así que los tipos salen del código de backend/src/meshbox/api/admin/
// y de respuestas reales del backend de desarrollo. Los cuerpos de petición vienen de
// schema.d.ts (`components['schemas']`).
import type { components } from '$lib/api/schema';
import type { Alert, NodeDetail } from '$lib/api/types';

export type Schemas = components['schemas'];

/** Ventana de tiempo Unix en segundos (como en toda la API). */
export type Ts = number;

// ------------------------------------------------------------------ sistema

export interface ServiceStatus {
	name: string;
	unit?: string;
	load?: string;
	/** `null` si privd no pudo consultar el servicio. */
	active: boolean | null;
	sub?: string;
	enabled?: boolean;
	pid?: number | null;
	restarts?: number;
	result?: string;
	since?: Ts | null;
	state: string | null;
	unit_file_state?: string;
	version?: string;
	uptime_s?: number;
	error?: string;
}

export interface ConnectorStatus {
	id: string;
	kind: string;
	state: string;
	since: Ts | null;
	last_packet_at: Ts | null;
	packets: number;
	invalid: number;
	errors: number;
	last_error: string | null;
	detail: Record<string, unknown>;
	enabled?: boolean;
}

export interface SystemSnapshot {
	ts: Ts;
	rss_mb: number;
	rss_peak_mb: number;
	cpu_process: number;
	cpu_system: number;
	threads: number;
	mem_total: number;
	mem_available: number;
	mem_percent: number;
	swap_used: number;
	swap_percent: number;
	temperature: number | null;
	disk: { total: number; used: number; free: number; percent: number };
	load: number[];
	uptime_s: number;
	boot_time: Ts;
	db: { db: number; db_wal: number; db_shm: number };
	writer: {
		queue: number;
		written_ops: number;
		dropped_ops: number;
		failed_ops: number;
		batches: number;
		last_batch_ms: number;
		last_batch_size: number;
	};
	bus: { seq: number; dropped: number };
	ingest_queue: number;
	ingest_dropped: number;
	sse_clients: { public: number; admin: number };
	connectors: ConnectorStatus[];
	ntp_synced: boolean | null;
}

/** El backend responde `{}` hasta la primera muestra (unos segundos después de arrancar). */
export function snapshotOf(s: SystemSnapshot | null | undefined): SystemSnapshot | null {
	return s && typeof s.ts === 'number' ? s : null;
}

export interface GatewayInfo {
	id: string;
	last_seen: Ts;
	connectors: string[];
	firmware_version: string | null;
	region: string | null;
	modem_preset: string | null;
	num_online_local_nodes: number | null;
	has_default_channel: boolean | null;
	local_stats: Record<string, unknown> | null;
	local_stats_ts: Ts | null;
	packets: number;
}

export interface Counters {
	packets_total: number;
	duplicates_total: number;
	invalid_total: number;
	hidden_dropped: number;
	flood_dropped: number;
	undecryptable: number;
	decode_errors: number;
	routing_errors: Record<string, number>;
	by_connector: Record<string, number>;
	portnums_last_hour: Record<string, number>;
}

export interface MinuteCount {
	t: Ts;
	n: number;
}

export interface AdminAlertEvent extends Alert {
	rule_id?: number | null;
	is_public?: boolean;
	ack_by?: number | string | null;
	ack_at?: Ts | null;
}

export interface SystemStatus {
	version: string;
	mode: 'shared' | 'appliance';
	services: Record<string, ServiceStatus>;
	system: SystemSnapshot | null;
	connectors: ConnectorStatus[];
	gateways: GatewayInfo[];
	summary: {
		nodes: Record<string, number>;
		packets_last_hour: number;
		channel_utilization_avg: number | null;
		new_nodes_24h: number;
		last_packet_at: Ts | null;
		ts: Ts;
	};
	counters: Counters;
	packets_per_minute: MinuteCount[];
	sse_clients: { public: number; admin: number };
	last_packet_at: Ts | null;
	recent_alerts: AdminAlertEvent[];
	update: UpdatesStatus | null;
	ntp_synced: boolean | null;
	privd: string;
}

export interface SystemMetrics {
	system: SystemSnapshot | null;
	packets_per_minute: MinuteCount[];
	counters: Counters;
	writer: SystemSnapshot['writer'];
	bus: SystemSnapshot['bus'] & {
		published?: number;
		subscribers?: { name: string; queued: number; dropped: number }[];
	};
	dedup_entries: number;
	ingest: { queue: number; dropped: number };
	memory_guard: { soft_mb: number; hard_mb: number; soft_hits: number };
}

export type LogUnit = 'meshbox' | 'mosquitto' | 'meshbox-cloudflared' | 'meshbox-privd';

export interface LogEntry {
	ts: Ts | null;
	level: string;
	msg: string;
	logger: string | null;
	unit: string;
	seq?: number;
}

// ------------------------------------------------------------------ red

export interface WifiStatus {
	device: string;
	state: string;
	connection: string | null;
	ssid: string | null;
	signal: number | null;
	ip4: string[];
	hotspot: boolean;
	saved: { ssid: string; name: string; uuid: string }[];
	job: PrivJob | null;
}

export interface NetworkStatus {
	wifi: WifiStatus;
	time: {
		timezone: string;
		ntp: boolean;
		ntp_synchronized: boolean;
		can_ntp: boolean;
		local_rtc: boolean;
		time: string;
	};
	system: {
		hostname: string;
		mode: string;
		kernel: string;
		arch: string;
		model: string;
		uptime_s: number;
		os: string | null;
		python: string;
		privd_version: string;
	};
	lan_ip: string;
	/** `true` solo en un equipo dedicado (modo appliance). */
	managed: boolean;
}

export interface WifiNetwork {
	ssid: string;
	bssid: string;
	signal: number;
	security: string;
	channel: number;
	freq_mhz: number;
	in_use: boolean;
}

export interface WifiScan {
	networks: WifiNetwork[];
	cached: boolean;
	scanned_at: Ts;
}

/** Trabajo largo de privd (actualización, cambio de red). */
export interface PrivJob {
	job: string;
	kind: string;
	state: 'running' | 'succeeded' | 'failed' | string;
	step: string;
	/** 0 a 1, o null si no se conoce. */
	progress: number | null;
	message: string | null;
	error_code: string | null;
	started_at: Ts;
	finished_at: Ts | null;
	meta: Record<string, unknown>;
	result: Record<string, unknown> | null;
}

// ------------------------------------------------------------------ radio

export type ConnectorKind = 'mqtt' | 'serial' | 'tcp' | 'replay';

export interface ConnectorConfig {
	id: string;
	kind: ConnectorKind;
	enabled: boolean;
	host?: string;
	port?: number | string;
	username?: string | null;
	/** `********` si hay una guardada (solo escritura). */
	password?: string;
	topics?: string[];
	tls?: boolean;
	file?: string;
	speed?: number;
	loop?: boolean;
	rebase_time?: boolean;
	status: Partial<ConnectorStatus> & { state: string };
}

export interface SerialPortInfo {
	device: string;
	description?: string | null;
	hwid?: string | null;
	[key: string]: unknown;
}

export interface Recording {
	name: string;
	size: number;
	mtime: Ts;
}

export type ConnectorTest =
	| { ok: true; connected_ms: number; messages: number; valid_envelopes: number; seconds: number }
	| { ok: true; node: Record<string, unknown> }
	| { ok: boolean; file: string }
	| { ok: false; error: string };

// ------------------------------------------------------------------ MQTT

export interface MqttAccount {
	username: string;
	purpose: 'gateway' | 'integration' | 'debug' | 'ingest' | string;
	created_at: Ts;
	note: string | null;
}

export interface HeltecCommands {
	commands: string[];
	optional_gateway_only: string;
	notes: string[];
}

export interface MqttSecret {
	username: string;
	password: string;
	purpose?: string;
	warning?: string;
	heltec?: HeltecCommands;
}

export interface MqttStatus {
	broker: Partial<ServiceStatus> & {
		accounts?: string[];
		acl_present?: boolean;
		error?: string;
	};
	mqtt_out: {
		enabled: boolean;
		connected: boolean;
		published: number;
		dropped: number;
		last_error: string | null;
		prefix: string;
	} | null;
	lan_ip: string;
	port: number;
}

// ------------------------------------------------------------------ canales

export interface RadioChannel {
	id: number;
	name: string;
	hash: number | null;
	is_public: boolean;
	has_key: boolean;
}

// ------------------------------------------------------------------ paquetes, nodos y mensajes

export interface PacketRow {
	pk: number;
	from: string;
	to: string;
	packet_id: number;
	channel: string | null;
	channel_index: number | null;
	channel_hash: number | null;
	portnum: string | null;
	ts: Ts;
	hop_start: number | null;
	hops: number | null;
	want_ack: boolean;
	priority: string | null;
	encrypted: boolean;
	decoded_ok: boolean;
	is_public: boolean;
	payload_len: number | null;
	has_raw: boolean;
	gateway: string | null;
	source: string | null;
	snr: number | null;
	rssi: number | null;
	relay_node: number | null;
	via_mqtt: boolean;
	receptions: number;
}

export interface PacketDetail extends PacketRow {
	receptions_detail: Record<string, unknown>[];
	fields?: Record<string, unknown>;
	hex?: string;
	decoded?: {
		portnum: string;
		kind: string;
		content: unknown;
		error: string | null;
		channel?: string;
		request_id?: number | null;
		reply_id?: number | null;
	};
	privacy_note?: string;
}

/** Paquete en vivo por el stream del panel (`event: packet`). */
export interface LivePacket {
	seq: number;
	pk: number;
	portnum: string | null;
	from: string;
	to: string;
	packet_id: number;
	channel: string | null;
	hops: number | null;
	snr: number | null;
	rssi: number | null;
	gateway: string | null;
	source: string | null;
	connector: string | null;
	is_public: boolean;
	encrypted: boolean;
	decoded_ok: boolean;
	duplicate: boolean;
	via_mqtt: boolean;
	ts: Ts;
}

export interface PacketPage {
	packets: PacketRow[];
	next: string | null;
}

export interface AdminNode extends NodeDetail {
	num: number;
	hidden: boolean;
	note: string | null;
	is_licensed: boolean;
	has_public_key: boolean;
	last_gateway: string | null;
	heard_via_mqtt_only: boolean;
	precision_bits: number | null;
	status: 'active' | 'recent' | 'late' | 'inactive';
}

export interface AdminMessage {
	pk: number;
	ts: Ts;
	from: string;
	from_name: string | null;
	channel: string | null;
	text: string;
	reply_id: number | null;
	emoji: boolean;
	is_alert: boolean;
	hidden: boolean;
}

// ------------------------------------------------------------------ alertas

export type RuleKind = Schemas['RuleIn']['kind'];
export type NotifyChannel = 'webpush' | 'telegram' | 'webhook' | 'mqtt';

export interface AlertRule {
	id: number;
	name: string;
	kind: RuleKind;
	params: Record<string, unknown>;
	enabled: boolean;
	cooldown_s: number;
	channels: NotifyChannel[];
	severity: 'info' | 'warning' | 'critical';
	is_public: boolean;
	created_at: Ts | null;
	updated_at: Ts;
}

export interface AlertChannels {
	webpush: {
		enabled: boolean;
		available: boolean;
		public_key: string | null;
		subscriptions: Record<string, number>;
		subject: string;
	};
	telegram: { enabled: boolean; chat_id: string; bot_token: string };
	webhooks: { id: string; url: string; enabled: boolean; secret: string }[];
	mqtt: { enabled: boolean };
	stats: {
		fired: number;
		resolved: number;
		notifications_ok: number;
		notifications_failed: number;
		by_channel: Record<string, Record<string, number> | number>;
	};
}

// ------------------------------------------------------------------ sitio y privacidad

export type SiteSettings = Required<
	Pick<
		Schemas['SiteSettings'],
		| 'name'
		| 'description'
		| 'accent'
		| 'zoom'
		| 'default_layer'
		| 'satellite_enabled'
		| 'default_language'
		| 'notice_md'
		| 'show_inactive'
		| 'activity_layer'
		| 'links_layer'
		| 'waypoints_layer'
	>
> & {
	logo: string | null;
	center: number[];
	bounds: number[] | null;
	status_thresholds: { active_s: number; recent_s: number; late_s: number };
};

export interface AdminSite {
	site: SiteSettings;
	timezone: string;
	slug: string;
}

export interface TileJobStatus {
	state: 'idle' | 'running' | 'done' | 'error';
	progress: string[];
	started_at: Ts | null;
	finished_at: Ts | null;
	error: string | null;
	bytes: number;
}

export interface TilesStatus {
	store: {
		available: boolean;
		path: string;
		size: number;
		min_zoom: number | null;
		max_zoom: number | null;
		bounds: number[] | null;
		served: number;
	} | null;
	job: TileJobStatus;
}

export type PrivacyCfg = Required<Schemas['PrivacyCfg']>;
export type RetentionCfg = Required<Schemas['RetentionCfg']>;

export interface AdminPrivacy {
	privacy: PrivacyCfg;
	retention: RetentionCfg;
	notice_md: string;
}

// ------------------------------------------------------------------ Cloudflare

export interface CloudflareZone {
	id: string;
	name: string;
	account_id: string;
	account_name: string | null;
}

export interface CloudflareStatus {
	mode: 'none' | 'token' | 'api';
	public_hostname: string;
	admin_hostname: string;
	service: Partial<ServiceStatus> & { token_configured?: boolean; error?: string };
	tunnel: {
		id?: string;
		name?: string;
		status?: string;
		connections?: number;
		error?: string;
	} | null;
	site_check: { ok: boolean | null; status?: number; error?: string; checked_at?: Ts } | null;
	has_api_token: boolean;
	access: { team_domain: string; configured: boolean };
	public_target: string;
	admin_target: string;
}

export interface ProvisionStep {
	step: string;
	[key: string]: unknown;
}

// ------------------------------------------------------------------ plugins

export interface JsonSchema {
	type?: string | string[];
	title?: string;
	description?: string;
	default?: unknown;
	enum?: unknown[];
	const?: unknown;
	properties?: Record<string, JsonSchema>;
	required?: string[];
	items?: JsonSchema;
	minimum?: number;
	maximum?: number;
	exclusiveMinimum?: number;
	exclusiveMaximum?: number;
	minLength?: number;
	maxLength?: number;
	minItems?: number;
	maxItems?: number;
	pattern?: string;
	format?: string;
	writeOnly?: boolean;
	anyOf?: JsonSchema[];
	oneOf?: JsonSchema[];
	allOf?: JsonSchema[];
	$ref?: string;
	$defs?: Record<string, JsonSchema>;
	additionalProperties?: boolean | JsonSchema;
}

export interface PluginInfo {
	id: string;
	name: string;
	version: string;
	description: string | null;
	builtin: boolean;
	permissions: string[];
	enabled: boolean;
	running: boolean;
	error: string | null;
	settings: Record<string, unknown>;
	settings_schema: JsonSchema | null;
	layers: { id: string; name: string; geometry?: string; style?: string; refresh_s?: number }[];
}

export interface PluginList {
	plugins: PluginInfo[];
	warning: string;
	user_dir: string;
}

// ------------------------------------------------------------------ usuarios

export interface AdminUser {
	id: number;
	username: string;
	role: 'admin' | 'operator';
	disabled: boolean;
	created_at: Ts;
	last_login_at: Ts | null;
	must_change_password: boolean;
}

export interface AdminSessionRow {
	id: string;
	user_id: number;
	username: string;
	created_at: Ts;
	expires_at: Ts;
	last_seen_at: Ts;
	ip: string | null;
	user_agent: string | null;
	current: boolean;
}

export interface AuditEntry {
	id: number;
	ts: Ts;
	user_id: number | null;
	username: string | null;
	action: string;
	target: string | null;
	details: string | Record<string, unknown> | null;
	ip: string | null;
}

// ------------------------------------------------------------------ respaldos y actualizaciones

export interface BackupFile {
	name: string;
	size: number;
	mtime: Ts;
	daily: boolean;
}

export interface ReleaseInfo {
	version: string;
	tag: string;
	name: string;
	notes: string;
	published_at: string | null;
	prerelease: boolean;
	has_package: boolean;
	signed: boolean;
}

export interface UpdatesStatus {
	current: string;
	local: {
		current?: string;
		installed?: string[];
		previous?: string | null;
		/** Lo que privd guarda de la última actualización o vuelta atrás. */
		last_update?: { updated_at?: Ts; current?: string; rolled_back_from?: string } | null;
		job?: PrivJob | null;
		updates_base_url?: string | null;
		error?: string;
	};
	latest: string | null;
	update_available: boolean;
	releases: ReleaseInfo[];
	auto_check: boolean;
	source: string;
	error: string | null;
}

// ------------------------------------------------------------------ asistente

export type SetupStep =
	| 'wifi'
	| 'code'
	| 'locale'
	| 'admin'
	| 'site'
	| 'radio'
	| 'channel'
	| 'privacy'
	| 'tiles'
	| 'cloudflare'
	| 'finish';

export interface SetupState {
	needs_setup: boolean;
	users_exist: boolean;
	code_required: boolean;
	window_open: boolean;
	window_closes_at: Ts | null;
	hotspot: boolean;
	mode: 'shared' | 'appliance';
	lan_ip: string;
	lan_bind: string;
	steps: SetupStep[];
	completed: SetupStep[];
	done: boolean;
}

/** Resumen del último paso: llega al menos un paquete y el sitio responde. */
export interface SetupVerify {
	packets_total: number;
	last_packet_at: Ts | null;
	packet_received: boolean;
	connectors: ConnectorStatus[];
	nodes: number;
	public_channels: string[];
	site_ok: boolean;
	tiles: boolean;
}
