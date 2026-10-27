// Etiquetas traducidas de valores que vienen de la radio (roles, tipos de paquete, estados).
import type { Alert, NodeStatus } from '$lib/api/types';
import { m } from '$lib/paraglide/messages';

const ROLES: Record<string, () => string> = {
	CLIENT: m.role_CLIENT,
	CLIENT_MUTE: m.role_CLIENT_MUTE,
	CLIENT_HIDDEN: m.role_CLIENT_HIDDEN,
	CLIENT_BASE: m.role_CLIENT_BASE,
	TRACKER: m.role_TRACKER,
	TAK: m.role_TAK,
	TAK_TRACKER: m.role_TAK_TRACKER,
	SENSOR: m.role_SENSOR,
	LOST_AND_FOUND: m.role_LOST_AND_FOUND,
	ROUTER: m.role_ROUTER,
	ROUTER_LATE: m.role_ROUTER_LATE,
	ROUTER_CLIENT: m.role_ROUTER_CLIENT,
	REPEATER: m.role_REPEATER
};

export function roleLabel(role: string | null | undefined): string {
	if (!role) return m.unknown();
	return ROLES[role]?.() ?? role;
}

export const KNOWN_ROLES = Object.keys(ROLES);

const PORTS: Record<string, () => string> = {
	TEXT_MESSAGE_APP: m.port_TEXT_MESSAGE_APP,
	POSITION_APP: m.port_POSITION_APP,
	NODEINFO_APP: m.port_NODEINFO_APP,
	TELEMETRY_APP: m.port_TELEMETRY_APP,
	NEIGHBORINFO_APP: m.port_NEIGHBORINFO_APP,
	TRACEROUTE_APP: m.port_TRACEROUTE_APP,
	MAP_REPORT_APP: m.port_MAP_REPORT_APP,
	ROUTING_APP: m.port_ROUTING_APP,
	WAYPOINT_APP: m.port_WAYPOINT_APP,
	ALERT_APP: m.port_ALERT_APP,
	RANGE_TEST_APP: m.port_RANGE_TEST_APP,
	STORE_FORWARD_APP: m.port_STORE_FORWARD_APP,
	DETECTION_SENSOR_APP: m.port_DETECTION_SENSOR_APP,
	PAXCOUNTER_APP: m.port_PAXCOUNTER_APP,
	ENCRYPTED: m.port_ENCRYPTED
};

export const KNOWN_PORTS = Object.keys(PORTS);

export function portLabel(portnum: string | null | undefined): string {
	if (!portnum) return m.port_other();
	return PORTS[portnum]?.() ?? portnum.replace(/_APP$/, '').replaceAll('_', ' ').toLowerCase();
}

const STATUS: Record<NodeStatus, () => string> = {
	active: m.status_active,
	recent: m.status_recent,
	late: m.status_late,
	inactive: m.status_inactive
};

export function statusLabel(status: NodeStatus): string {
	return STATUS[status]();
}

export function severityLabel(severity: Alert['severity']): string {
	return severity === 'critical'
		? m.alerts_severity_critical()
		: severity === 'warning'
			? m.alerts_severity_warning()
			: m.alerts_severity_info();
}

export function sourceLabel(source: string): string {
	return source === 'neighborinfo'
		? m.node_source_neighborinfo()
		: source === 'traceroute'
			? m.node_source_traceroute()
			: m.node_source_direct();
}
