// Secciones del panel (18.2). El rol operador ve diagnóstico, paquetes, nodos, mensajes,
// alertas y registros (13.2); Transmisión solo aparece si está habilitada (22).
import type { LucideIcon } from '@lucide/svelte';
import Archive from '@lucide/svelte/icons/archive';
import Bell from '@lucide/svelte/icons/bell';
import Cable from '@lucide/svelte/icons/cable';
import Cloud from '@lucide/svelte/icons/cloud';
import Database from '@lucide/svelte/icons/database';
import Download from '@lucide/svelte/icons/download';
import KeyRound from '@lucide/svelte/icons/key-round';
import LayoutDashboard from '@lucide/svelte/icons/layout-dashboard';
import MapIcon from '@lucide/svelte/icons/map';
import MessageSquare from '@lucide/svelte/icons/message-square';
import Network from '@lucide/svelte/icons/network';
import Puzzle from '@lucide/svelte/icons/puzzle';
import Radio from '@lucide/svelte/icons/radio';
import ScrollText from '@lucide/svelte/icons/scroll-text';
import Send from '@lucide/svelte/icons/send';
import Shield from '@lucide/svelte/icons/shield';
import Smartphone from '@lucide/svelte/icons/smartphone';
import Users from '@lucide/svelte/icons/users';
import Waypoints from '@lucide/svelte/icons/waypoints';
import type { AdminRole } from '$lib/api/types';
import { m } from '$lib/paraglide/messages';

export interface AdminSection {
	slug: string;
	title: () => string;
	description: () => string;
	icon: LucideIcon;
	roles: AdminRole[];
	/** Solo si la transmisión está habilitada. */
	tx?: boolean;
}

const BOTH: AdminRole[] = ['admin', 'operator'];
const ADMIN: AdminRole[] = ['admin'];

export const SECTIONS: AdminSection[] = [
	{
		slug: '',
		title: m.admin_section_dashboard,
		description: m.admin_section_dashboard_desc,
		icon: LayoutDashboard,
		roles: BOTH
	},
	{
		slug: 'radio',
		title: m.admin_section_radio,
		description: m.admin_section_radio_desc,
		icon: Radio,
		roles: ADMIN
	},
	{
		slug: 'cliente',
		title: m.admin_section_client,
		description: m.admin_section_client_desc,
		icon: Smartphone,
		roles: BOTH
	},
	{
		slug: 'mqtt',
		title: m.admin_section_mqtt,
		description: m.admin_section_mqtt_desc,
		icon: Cable,
		roles: ADMIN
	},
	{
		slug: 'canales',
		title: m.admin_section_channels,
		description: m.admin_section_channels_desc,
		icon: KeyRound,
		roles: ADMIN
	},
	{
		slug: 'paquetes',
		title: m.admin_section_packets,
		description: m.admin_section_packets_desc,
		icon: Database,
		roles: BOTH
	},
	{
		slug: 'nodos',
		title: m.admin_section_nodes,
		description: m.admin_section_nodes_desc,
		icon: Waypoints,
		roles: BOTH
	},
	{
		slug: 'mensajes',
		title: m.admin_section_messages,
		description: m.admin_section_messages_desc,
		icon: MessageSquare,
		roles: BOTH
	},
	{
		slug: 'alertas',
		title: m.admin_section_alerts,
		description: m.admin_section_alerts_desc,
		icon: Bell,
		roles: BOTH
	},
	{
		slug: 'sitio',
		title: m.admin_section_site,
		description: m.admin_section_site_desc,
		icon: MapIcon,
		roles: ADMIN
	},
	{
		slug: 'privacidad',
		title: m.admin_section_privacy,
		description: m.admin_section_privacy_desc,
		icon: Shield,
		roles: ADMIN
	},
	{
		slug: 'cloudflare',
		title: m.admin_section_cloudflare,
		description: m.admin_section_cloudflare_desc,
		icon: Cloud,
		roles: ADMIN
	},
	{
		slug: 'red',
		title: m.admin_section_network,
		description: m.admin_section_network_desc,
		icon: Network,
		roles: ADMIN
	},
	{
		slug: 'plugins',
		title: m.admin_section_plugins,
		description: m.admin_section_plugins_desc,
		icon: Puzzle,
		roles: ADMIN
	},
	{
		slug: 'usuarios',
		title: m.admin_section_users,
		description: m.admin_section_users_desc,
		icon: Users,
		roles: ADMIN
	},
	{
		slug: 'respaldo',
		title: m.admin_section_backups,
		description: m.admin_section_backups_desc,
		icon: Archive,
		roles: ADMIN
	},
	{
		slug: 'actualizaciones',
		title: m.admin_section_updates,
		description: m.admin_section_updates_desc,
		icon: Download,
		roles: ADMIN
	},
	{
		slug: 'registros',
		title: m.admin_section_logs,
		description: m.admin_section_logs_desc,
		icon: ScrollText,
		roles: BOTH
	},
	{
		slug: 'transmision',
		title: m.admin_section_tx,
		description: m.admin_section_tx_desc,
		icon: Send,
		roles: ADMIN,
		tx: true
	}
];

export function sectionBySlug(slug: string): AdminSection | undefined {
	return SECTIONS.find((s) => s.slug === slug);
}

export function visibleSections(role: AdminRole | undefined, txEnabled: boolean): AdminSection[] {
	return SECTIONS.filter((s) => (!s.tx || txEnabled) && (!role || s.roles.includes(role)));
}
