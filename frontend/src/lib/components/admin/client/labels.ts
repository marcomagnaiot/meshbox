// Nombres de las secciones de configuración de la placa (los de la app de Meshtastic).
import { fieldLabel } from '$lib/admin/radio';
import { m } from '$lib/paraglide/messages';

const SECTIONS: Record<string, () => string> = {
	device: m.adm_cli_sec_device,
	position: m.adm_cli_sec_position,
	power: m.adm_cli_sec_power,
	network: m.adm_cli_sec_network,
	display: m.adm_cli_sec_display,
	lora: m.adm_cli_sec_lora,
	bluetooth: m.adm_cli_sec_bluetooth,
	security: m.adm_cli_sec_security,
	mqtt: m.adm_cli_sec_mqtt,
	serial: m.adm_cli_sec_serial,
	external_notification: m.adm_cli_sec_external_notification,
	store_forward: m.adm_cli_sec_store_forward,
	range_test: m.adm_cli_sec_range_test,
	telemetry: m.adm_cli_sec_telemetry,
	canned_message: m.adm_cli_sec_canned_message,
	audio: m.adm_cli_sec_audio,
	remote_hardware: m.adm_cli_sec_remote_hardware,
	neighbor_info: m.adm_cli_sec_neighbor_info,
	ambient_lighting: m.adm_cli_sec_ambient_lighting,
	detection_sensor: m.adm_cli_sec_detection_sensor,
	paxcounter: m.adm_cli_sec_paxcounter,
	statusmessage: m.adm_cli_sec_statusmessage,
	traffic_management: m.adm_cli_sec_traffic_management,
	tak: m.adm_cli_sec_tak
};

export function sectionLabel(name: string): string {
	return SECTIONS[name]?.() ?? fieldLabel(name);
}
