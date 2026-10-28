<!-- Datos de un nodo según la base de la placa (pestaña Nodos y ficha desde Mensajes). -->
<script lang="ts">
	import type { BoardNode } from '$lib/admin/radio';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import KeyValue from '$lib/components/admin/KeyValue.svelte';

	interface Props {
		node: BoardNode;
		columns?: number;
	}

	let { node, columns = 3 }: Props = $props();

	const battery = $derived(node.metrics.batteryLevel);
</script>

<KeyValue
	{columns}
	items={[
		{ label: m.adm_cli_hw(), value: node.hw_model ?? '—' },
		{ label: m.adm_role(), value: node.role, mono: true },
		{ label: m.adm_last_heard(), value: fmt.relative(node.last_heard) },
		{ label: 'SNR', value: fmt.db(node.snr) },
		{
			label: m.adm_cli_hops_col(),
			value: node.hops === null ? '—' : node.hops === 0 ? m.adm_cli_direct_rx() : node.hops
		},
		{
			label: m.adm_battery(),
			value: battery === undefined ? '—' : battery > 100 ? m.adm_powered() : `${battery} %`
		},
		{ label: m.adm_channel(), value: node.channel },
		{
			label: m.adm_cli_coords(),
			value: node.lat && node.lon ? `${node.lat.toFixed(4)}, ${node.lon.toFixed(4)}` : '—',
			mono: true
		},
		{ label: m.adm_cli_pki(), value: node.has_pki ? m.adm_yes() : m.adm_no() },
		{ label: 'MQTT', value: node.via_mqtt ? m.adm_yes() : m.adm_no() }
	]}
/>
