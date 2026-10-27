<!--
  Detalle de un paquete (18.2): campos del MeshPacket, contenido decodificado en JSON, bytes en
  hexadecimal y recepciones por gateway con SNR y saltos.
-->
<script lang="ts">
	import * as adminApi from '$lib/admin/api';
	import { ApiError } from '$lib/api/client';
	import { problemText } from '$lib/admin/errors';
	import type { PacketDetail } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { portLabel } from '$lib/i18n/labels';
	import { m } from '$lib/paraglide/messages';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import CopyBlock from '../CopyBlock.svelte';
	import JsonView from '../JsonView.svelte';
	import KeyValue from '../KeyValue.svelte';

	interface Props {
		pk: number;
		nameOf: (id: string) => string | null;
	}

	let { pk, nameOf }: Props = $props();
	let data = $state<PacketDetail | null>(null);
	let error = $state<string | null>(null);

	// Un paquete recién llegado por el stream puede no estar escrito todavía (el escritor
	// guarda por lotes cada 2 s): ante un 404 se reintenta dos veces antes de mostrar el error.
	$effect(() => {
		const id = pk;
		let cancelled = false;
		data = null;
		error = null;
		const attempt = (n: number) => {
			adminApi.packets
				.get(id)
				.then((d) => {
					if (!cancelled) data = d;
				})
				.catch((err) => {
					if (cancelled) return;
					if (err instanceof ApiError && err.status === 404 && n < 2) {
						setTimeout(() => attempt(n + 1), 1500);
					} else error = problemText(err);
				});
		};
		attempt(0);
		return () => {
			cancelled = true;
		};
	});

	function who(id: string): string {
		const n = nameOf(id);
		return n ? `${n} (${id})` : id;
	}

	const receptions = $derived(
		(data?.receptions_detail ?? []).map((r) => ({
			gateway: String(r.gateway ?? '—'),
			source: String(r.source ?? ''),
			snr: typeof r.rx_snr === 'number' ? r.rx_snr : null,
			rssi: typeof r.rx_rssi === 'number' ? r.rx_rssi : null,
			hops:
				typeof r.hop_limit === 'number' && data?.hop_start
					? data.hop_start - (r.hop_limit as number)
					: null,
			ts: typeof r.rx_time === 'number' ? r.rx_time : null,
			mqtt: Boolean(r.via_mqtt)
		}))
	);
</script>

{#if error}
	<p class="adm-note danger" role="alert">{error}</p>
{:else if !data}
	<Skeleton lines={6} label={m.loading()} />
{:else}
	<div class="adm-stack">
		<KeyValue
			columns={3}
			items={[
				{ label: m.adm_pkt_type(), value: portLabel(data.portnum ?? 'ENCRYPTED') },
				{ label: m.adm_when(), value: fmt.dateTime(data.ts) },
				{ label: m.adm_pkt_id(), value: String(data.packet_id), mono: true },
				{ label: m.adm_from(), value: who(data.from) },
				{ label: m.adm_pkt_to(), value: data.to === '^all' ? m.adm_pkt_broadcast() : who(data.to) },
				{
					label: m.adm_channel(),
					value: data.channel ?? (data.channel_hash !== null ? `#${data.channel_hash}` : null)
				},
				{
					label: m.adm_pkt_hops(),
					value: data.hops === null ? null : `${data.hops} / ${data.hop_start ?? '—'}`
				},
				{ label: m.adm_snr(), value: fmt.db(data.snr) },
				{ label: m.adm_rssi(), value: fmt.dbm(data.rssi) },
				{ label: m.adm_gateway(), value: data.gateway, mono: true },
				{ label: m.adm_pkt_source(), value: data.source },
				{
					label: m.adm_pkt_size(),
					value: data.payload_len === null ? null : `${data.payload_len} B`
				}
			]}
		/>
		<div class="adm-row">
			{#if data.is_public}<span class="adm-badge ok">{m.adm_pkt_public()}</span>{/if}
			{#if data.encrypted}<span class="adm-badge">{m.adm_pkt_encrypted()}</span>{/if}
			{#if data.decoded_ok}<span class="adm-badge">{m.adm_pkt_decoded()}</span>{/if}
			{#if data.via_mqtt}<span class="adm-badge">MQTT</span>{/if}
			{#if data.want_ack}<span class="adm-badge">want_ack</span>{/if}
			{#if data.priority}<span class="adm-badge">{data.priority}</span>{/if}
		</div>
		{#if data.privacy_note}<p class="adm-note">{data.privacy_note}</p>{/if}
		{#if data.decoded}
			{#if data.decoded.error}<p class="adm-note danger">{data.decoded.error}</p>{/if}
			<JsonView
				summary={m.adm_pkt_content({ kind: data.decoded.kind })}
				value={data.decoded.content}
				open
			/>
		{/if}
		{#if data.fields}<JsonView summary={m.adm_pkt_fields()} value={data.fields} />{/if}
		{#if data.hex}
			<details>
				<summary class="sum">{m.adm_pkt_hex({ bytes: data.hex.length / 2 })}</summary>
				<CopyBlock
					text={data.hex.replace(/(.{2})/g, '$1 ').trim()}
					label={m.adm_pkt_hex({ bytes: data.hex.length / 2 })}
				/>
			</details>
		{/if}
		{#if receptions.length}
			<div class="recs">
				<h3>{m.adm_pkt_receptions({ count: receptions.length })}</h3>
				<table>
					<thead>
						<tr>
							<th scope="col">{m.adm_gateway()}</th>
							<th scope="col">{m.adm_pkt_source()}</th>
							<th scope="col" class="num">{m.adm_snr()}</th>
							<th scope="col" class="num">{m.adm_rssi()}</th>
							<th scope="col" class="num">{m.adm_pkt_hops()}</th>
							<th scope="col">{m.adm_when()}</th>
						</tr>
					</thead>
					<tbody>
						{#each receptions as r, i (i)}
							<tr>
								<td class="adm-mono">{r.gateway}{r.mqtt ? ' · MQTT' : ''}</td>
								<td>{r.source}</td>
								<td class="num">{fmt.db(r.snr)}</td>
								<td class="num">{fmt.dbm(r.rssi)}</td>
								<td class="num">{r.hops ?? '—'}</td>
								<td>{r.ts ? fmt.time(r.ts, true) : '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>
{/if}

<style>
	.sum {
		cursor: pointer;
		padding: 8px 0;
		font-size: 0.8125rem;
		font-weight: 650;
	}

	.recs {
		overflow-x: auto;
	}

	.recs h3 {
		margin: 0 0 8px;
		font-size: 0.875rem;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.8125rem;
		font-variant-numeric: tabular-nums;
	}

	th,
	td {
		padding: 6px 8px;
		text-align: left;
		border-bottom: 1px solid var(--line);
		white-space: nowrap;
	}

	th {
		color: var(--text-2);
		font-weight: 650;
	}

	.num {
		text-align: right;
	}
</style>
