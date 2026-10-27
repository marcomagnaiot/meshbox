// Textos de los estados y tipos que devuelve la API del panel (conectores, cuentas MQTT,
// reglas). Lo desconocido se muestra tal cual.
import { m } from '$lib/paraglide/messages';

export function connectorStateLabel(state: string | null | undefined): string {
	switch (state) {
		case 'connected':
			return m.adm_cstate_connected();
		case 'connecting':
			return m.adm_cstate_connecting();
		case 'reconnecting':
			return m.adm_cstate_reconnecting();
		case 'degraded':
			return m.adm_cstate_degraded();
		case 'disconnected':
			return m.adm_cstate_disconnected();
		case 'stopped':
			return m.adm_cstate_stopped();
		case 'error':
			return m.adm_cstate_error();
		case 'finished':
			return m.adm_cstate_finished();
		default:
			return state ?? m.adm_unknown();
	}
}

/** Para StatusPill: conectado = activo, detenido = inactivo, el resto sin datos o error. */
export function connectorActive(state: string | null | undefined): boolean | null {
	if (state === 'connected') return true;
	if (state === 'stopped' || state === 'disconnected' || state === 'finished') return false;
	return null;
}

export function connectorKindLabel(kind: string): string {
	switch (kind) {
		case 'mqtt':
			return m.adm_ckind_mqtt();
		case 'serial':
			return m.adm_ckind_serial();
		case 'tcp':
			return m.adm_ckind_tcp();
		case 'replay':
			return m.adm_ckind_replay();
		default:
			return kind;
	}
}

export function purposeLabel(purpose: string): string {
	switch (purpose) {
		case 'gateway':
			return m.adm_purpose_gateway();
		case 'integration':
			return m.adm_purpose_integration();
		case 'debug':
			return m.adm_purpose_debug();
		case 'ingest':
			return m.adm_purpose_ingest();
		default:
			return purpose;
	}
}

export function ruleKindLabel(kind: string): string {
	switch (kind) {
		case 'keyword':
			return m.adm_rule_keyword();
		case 'telemetry_threshold':
			return m.adm_rule_telemetry_threshold();
		case 'node_offline':
			return m.adm_rule_node_offline();
		case 'node_online':
			return m.adm_rule_node_online();
		case 'new_node':
			return m.adm_rule_new_node();
		case 'gateway_down':
			return m.adm_rule_gateway_down();
		case 'system':
			return m.adm_rule_system();
		default:
			return kind;
	}
}

export function notifyChannelLabel(channel: string): string {
	switch (channel) {
		case 'webpush':
			return m.adm_notify_webpush();
		case 'telegram':
			return m.adm_notify_telegram();
		case 'webhook':
			return m.adm_notify_webhook();
		case 'mqtt':
			return m.adm_notify_mqtt();
		default:
			return channel;
	}
}

export function serviceLabel(name: string): string {
	switch (name) {
		case 'meshbox':
			return m.adm_svc_meshbox();
		case 'mosquitto':
			return m.adm_svc_mosquitto();
		case 'meshbox-cloudflared':
			return m.adm_svc_cloudflared();
		case 'meshbox-privd':
			return m.adm_svc_privd();
		default:
			return name;
	}
}

export function jobStateLabel(state: string): string {
	switch (state) {
		case 'running':
			return m.adm_job_running();
		case 'succeeded':
		case 'done':
			return m.adm_job_succeeded();
		case 'failed':
		case 'error':
			return m.adm_job_failed();
		default:
			return state;
	}
}

/** Pasos de los trabajos de privd (actualización y cambio de red). */
export function jobStepLabel(step: string): string {
	const labels: Record<string, () => string> = {
		queued: m.adm_step_queued,
		download: m.adm_step_download,
		verify_signature: m.adm_step_verify_signature,
		verify_checksum: m.adm_step_verify_checksum,
		extract: m.adm_step_extract,
		install: m.adm_step_install,
		backup: m.adm_step_backup,
		switch: m.adm_step_switch,
		health: m.adm_step_health,
		cleanup: m.adm_step_cleanup,
		rollback: m.adm_step_rollback,
		profile: m.adm_step_profile,
		connecting: m.adm_step_connecting,
		fallback: m.adm_step_fallback
	};
	return labels[step]?.() ?? step;
}
