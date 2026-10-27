<!--
  Catálogo de componentes con todos sus estados (16.4). Solo en desarrollo (/dev/componentes).
  Los textos de esta página son internos y no se traducen.
-->
<script lang="ts">
	import Bell from '@lucide/svelte/icons/bell';
	import Download from '@lucide/svelte/icons/download';
	import MapIcon from '@lucide/svelte/icons/map';
	import Plus from '@lucide/svelte/icons/plus';
	import RadioTower from '@lucide/svelte/icons/radio-tower';
	import SearchX from '@lucide/svelte/icons/search-x';
	import Trash from '@lucide/svelte/icons/trash-2';
	import type { Alert, Message, Node, NoticeBlock } from '$lib/api/types';
	import { alerts } from '$lib/stores/alerts.svelte';
	import { clock } from '$lib/stores/clock.svelte';
	import { prefs } from '$lib/stores/prefs.svelte';
	import { toasts } from '$lib/stores/ui.svelte';
	import { STATUSES } from '$lib/utils/status';
	import AlertItem from '$lib/components/alerts/AlertItem.svelte';
	import MessageBubble from '$lib/components/chat/MessageBubble.svelte';
	import NodeCard from '$lib/components/node/NodeCard.svelte';
	import NoticeBlocks from '$lib/components/notice/NoticeBlocks.svelte';
	import AppearanceControls from '$lib/components/shell/AppearanceControls.svelte';
	import FilterChips from '$lib/components/shell/FilterChips.svelte';
	import MapLegend from '$lib/components/shell/MapLegend.svelte';
	import SosBanner from '$lib/components/alerts/SosBanner.svelte';
	import BarList from '$lib/components/stats/BarList.svelte';
	import StatTile from '$lib/components/stats/StatTile.svelte';
	import BatteryRing from '$lib/components/ui/BatteryRing.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Chip from '$lib/components/ui/Chip.svelte';
	import ConfirmDialog from '$lib/components/ui/ConfirmDialog.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';
	import LiveIndicator from '$lib/components/ui/LiveIndicator.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import RoleBadge from '$lib/components/ui/RoleBadge.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import SignalBars from '$lib/components/ui/SignalBars.svelte';
	import Skeleton from '$lib/components/ui/Skeleton.svelte';
	import Sparkline from '$lib/components/ui/Sparkline.svelte';
	import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';
	import TimeSeriesChart from '$lib/components/ui/TimeSeriesChart.svelte';
	import Toggle from '$lib/components/ui/Toggle.svelte';

	const now = clock.exact();
	const TOKENS = [
		'--bg', '--surface-1', '--surface-2', '--surface-3', '--glass-bg', '--glass-bg-strong', '--glass-bg-solid',
		'--fill-1', '--fill-2', '--scrim', '--text-1', '--text-2', '--text-3', '--accent', '--accent-ink',
		'--st-active', '--st-recent', '--st-late', '--st-inactive', '--st-infra', '--st-alert',
		'--danger', '--warning', '--success', '--chart-line', '--cat-1', '--cat-2', '--cat-3', '--cat-other', '--route'
	]; // prettier-ignore
	const SIZES = [12, 13, 14, 16, 20, 24, 32];

	const series = Array.from({ length: 48 }, (_, i) => now - (47 - i) * 1800);
	const battery = series.map((_, i) => Math.round(80 + 15 * Math.sin(i / 6) - i * 0.2));
	const temp = series.map((_, i) => (i % 11 === 5 ? null : 14 + 6 * Math.sin(i / 7)));

	const sampleNode: Node = {
		id: '!0b03cbf0', short_name: 'TECH', long_name: 'Techo Magna (nombre largo de prueba para cortar)', role: 'ROUTER',
		hw_model: 'HELTEC_V4', lat: -40.81, lon: -62.99, alt: 14, precision_m: 23, battery: 101, powered: true,
		voltage: 4.2, channel_utilization: 7.1, air_util_tx: 0.9, uptime_s: 100000, last_heard: now - 600,
		first_seen: now - 86400 * 3, hops: 0, snr: 10.25, rssi: -53, is_infra: true, is_gateway: false, is_fixed: true, env: null
	}; // prettier-ignore
	const lateNode: Node = { ...sampleNode, id: '!3b28fef0', short_name: '🚀CR', long_name: 'Casa Ruta 251', role: 'CLIENT',
		battery: 12, powered: false, last_heard: now - 4 * 3600, is_infra: false, is_fixed: false, snr: -8, rssi: -118 }; // prettier-ignore

	const base: Message = {
		pk: 1, ts: now - 3600, from: '!0b03cbf0', from_name: 'Techo Magna', channel: 'MediumFast',
		text: 'Hola a todos, ¿alguien escucha desde la costa?', reply_id: null, emoji: false, packet_id: 111
	}; // prettier-ignore
	const reply: Message = { ...base, pk: 2, ts: now - 3500, from: '!3b28fef0', from_name: 'Casa Ruta 251',
		text: 'Fuerte y claro <img src=x onerror=alert(1)> (esto se ve como texto)', reply_id: 111, packet_id: 222 }; // prettier-ignore
	const orphanReply: Message = {
		...reply,
		pk: 3,
		reply_id: 999,
		text: 'Respuesta a un mensaje que no está cargado'
	};

	const alertFiring: Alert = { id: 9001, state: 'firing', severity: 'critical', kind: 'keyword', node: '!0b03cbf0',
		title: 'SOS desde Techo Magna', body: 'SOS necesito ayuda en la ruta 3', ts: now - 120 }; // prettier-ignore
	const alertWarn: Alert = { ...alertFiring, id: 9002, severity: 'warning', kind: 'telemetry_threshold',
		title: 'Batería baja en Casa Ruta 251', body: 'Batería 12 % durante 30 min', ts: now - 5000 }; // prettier-ignore
	const alertResolved: Alert = {
		...alertWarn,
		id: 9003,
		state: 'resolved',
		title: 'Nodo caído: Repetidor Costa'
	};

	const notice: NoticeBlock[] = [
		{ t: 'h3', c: [{ t: 'text', v: 'Privacidad' }] },
		{ t: 'p', c: [{ t: 'text', v: 'Texto con ' }, { t: 'strong', v: 'negrita' }, { t: 'text', v: ', ' }, { t: 'em', v: 'cursiva' }, { t: 'text', v: ' y ' }, { t: 'code', v: 'código' }, { t: 'text', v: '.' }] },
		{ t: 'ul', c: [[{ t: 'text', v: 'Un enlace: ' }, { t: 'link', v: 'OpenStreetMap', href: 'https://www.openstreetmap.org' }], [{ t: 'link', v: 'enlace peligroso (no se dibuja como enlace)', href: 'javascript:alert(1)' }], [{ t: 'text', v: '<b onmouseover=alert(1)>etiqueta</b> queda como texto' }]] }
	]; // prettier-ignore

	let segValue = $state('24h');
	let toggled = $state(true);
	let modalOpen = $state(false);
	let confirmOpen = $state(false);
	let chipA = $state(true);
	let chipB = $state(false);

	function simulateSos() {
		const map = new Map(alerts.byId);
		map.set(alertFiring.id, { ...alertFiring, ts: clock.exact() });
		alerts.byId = map;
	}
</script>

<svelte:head><title>Catálogo de componentes · meshbox</title></svelte:head>

<main id="contenido" class="catalog">
	<header class="intro">
		<h1>Catálogo de componentes</h1>
		<p>Sistema de diseño de meshbox (sección 16). Solo en desarrollo. Tema y modo sólido:</p>
		<div class="appearance surface"><AppearanceControls /></div>
	</header>

	<section>
		<h2>Tokens de color ({prefs.resolvedTheme}{prefs.solid ? ', sólido' : ''})</h2>
		<div class="swatches">
			{#each TOKENS as t (t)}
				<div class="swatch">
					<span class="chip-color" style="background: var({t})"></span>
					<code>{t}</code>
				</div>
			{/each}
		</div>
	</section>

	<section>
		<h2>Tipografía (Inter Variable)</h2>
		{#each SIZES as s (s)}
			<p style="font-size: {s}px; margin: 4px 0">{s} px · Red Meshtastic 0123456789</p>
		{/each}
		<p class="tabular">Cifras tabulares: 11:11 · 88:88 · 101 %</p>
	</section>

	<section>
		<h2>Superficies glass sobre un fondo exigente</h2>
		<div class="backdrop">
			<div class="glass glass-text demo">
				glass (16 px) + scrim · texto principal <span class="t2">secundario</span>
				<span class="t3">terciario</span>
			</div>
			<div class="glass-sm glass-text demo">glass-sm (20 px) + scrim</div>
			<div class="glass demo">glass sin scrim (solo íconos)</div>
			<div class="surface demo">superficie sólida (menús, diálogos, panel)</div>
		</div>
	</section>

	<section>
		<h2>Botones</h2>
		<div class="row">
			<Button variant="primary" icon={Plus}>Primario</Button>
			<Button>Secundario</Button>
			<Button variant="ghost">Fantasma</Button>
			<Button variant="danger" icon={Trash}>Peligro</Button>
			<Button loading>Cargando</Button>
			<Button disabled>Deshabilitado</Button>
			<Button size="sm" icon={Download}>Chico</Button>
		</div>
		<div class="row">
			<IconButton icon={MapIcon} label="Fantasma" />
			<IconButton icon={MapIcon} label="Relleno" variant="fill" />
			<IconButton icon={MapIcon} label="Acento" variant="accent" />
			<IconButton icon={MapIcon} label="Presionado" pressed />
			<IconButton icon={MapIcon} label="Chico" size="sm" />
			<IconButton icon={MapIcon} label="Deshabilitado" disabled />
		</div>
	</section>

	<section>
		<h2>Chips de filtro</h2>
		<div class="row">
			<Chip pressed={chipA} onclick={() => (chipA = !chipA)}>Activos</Chip>
			<Chip pressed={chipB} icon={RadioTower} onclick={() => (chipB = !chipB)}>Infraestructura</Chip
			>
		</div>
		<FilterChips />
	</section>

	<section>
		<h2>Estado de nodo (forma + color + texto)</h2>
		<div class="row">
			{#each STATUSES as s (s)}
				<StatusGlyph status={s} size={28} label={s} />
				<StatusGlyph status={s} infra size={28} />
				<StatusGlyph status={s} fixed size={28} />
				<StatusGlyph status={s} infra fixed size={28} />
			{/each}
		</div>
		<div class="row">
			{#each STATUSES as s (s)}<StatusBadge status={s} detail="hace 12 min" />{/each}
		</div>
		<div class="row">
			<RoleBadge role="ROUTER" infra /><RoleBadge role="CLIENT" /><RoleBadge
				role="TRACKER"
			/><RoleBadge role="NUEVO_ROL" />
		</div>
		<div class="legend surface"><MapLegend /></div>
	</section>

	<section>
		<h2>Batería y señal</h2>
		<div class="row">
			<BatteryRing battery={null} /><BatteryRing battery={5} /><BatteryRing
				battery={25}
			/><BatteryRing battery={55} />
			<BatteryRing battery={92} /><BatteryRing battery={101} powered /><BatteryRing
				battery={40}
				size={32}
				compact
			/>
		</div>
		<div class="row">
			<SignalBars snr={null} rssi={null} /><SignalBars snr={-12} /><SignalBars
				snr={-3}
			/><SignalBars snr={4} /><SignalBars snr={11} />
			<SignalBars snr={null} rssi={-80} />
		</div>
	</section>

	<section>
		<h2>Indicador de conexión</h2>
		<div class="row">
			<LiveIndicator status="live" /><LiveIndicator status="connecting" /><LiveIndicator
				status="reconnecting"
			/>
			<LiveIndicator status="offline" onretry={() => toasts.show('Reintentar')} />
		</div>
	</section>

	<section>
		<h2>Gráficos</h2>
		<div class="row">
			<Sparkline ts={series} values={battery} min={0} max={100} label="Batería" />
			<Sparkline ts={series} values={temp} label="Temperatura con huecos" />
			<Sparkline ts={[]} values={[]} label="Sin datos" />
		</div>
		<div class="chart card">
			<TimeSeriesChart
				ts={series}
				values={battery}
				label="Batería"
				format={(v) => `${Math.round(v)} %`}
				yRange={[0, 100]}
			/>
		</div>
		<div class="chart card">
			<TimeSeriesChart ts={[]} values={[]} label="Sin datos" />
		</div>
		<div class="row">
			<StatTile label="Nodos" value="27" />
			<StatTile label="Paquetes última hora" value="1.284" hint="+12 % que ayer" />
		</div>
		<div class="card pad">
			<BarList
				rows={[
					{ key: 'p', label: 'Posición', value: 2370 },
					{ key: 't', label: 'Telemetría', value: 1567 },
					{ key: 'n', label: 'Información de nodo', value: 200 },
					{ key: 'm', label: 'Mensajes de texto', value: 92 },
					{ key: 'x', label: 'Otros', value: 30 }
				]}
				caption="Paquetes por tipo"
				labelHeader="Tipo"
				valueHeader="Paquetes"
				shareHeader="Proporción"
			/>
		</div>
	</section>

	<section>
		<h2>Controles</h2>
		<Segmented
			label="Rango"
			options={[
				{ value: '24h', label: '24 h' },
				{ value: '7d', label: '7 d' },
				{ value: '30d', label: '30 d', disabled: true }
			]}
			bind:value={segValue}
		/>
		<div class="narrow">
			<Toggle label="Modo de prueba" hint="Con ayuda debajo" bind:checked={toggled} />
		</div>
	</section>

	<section>
		<h2>Lista de nodos</h2>
		<div class="cards">
			<div class="card-row"><NodeCard node={sampleNode} /></div>
			<div class="card-row"><NodeCard node={lateNode} selected /></div>
		</div>
	</section>

	<section>
		<h2>Mensajes</h2>
		<div class="chat card pad">
			<MessageBubble
				message={base}
				reactions={[
					{ emoji: '👍', from: [reply, orphanReply] },
					{ emoji: '❤️', from: [reply] }
				]}
			/>
			<MessageBubble message={reply} replyTo={base} />
			<MessageBubble
				message={{ ...reply, pk: 4, reply_id: null, text: 'Mensaje agrupado del mismo nodo' }}
				grouped
			/>
			<MessageBubble message={orphanReply} replyTo={null} />
		</div>
	</section>

	<section>
		<h2>Alertas</h2>
		<div class="col">
			<AlertItem alert={alertFiring} />
			<AlertItem alert={alertWarn} />
			<AlertItem alert={alertResolved} />
		</div>
		<Button icon={Bell} onclick={simulateSos}>Simular aviso SOS</Button>
		<SosBanner />
	</section>

	<section>
		<h2>Estados vacíos, carga y avisos</h2>
		<div class="row">
			<div class="card pad grow">
				<EmptyState
					icon={SearchX}
					title="Sin nodos que coincidan"
					description="Probar con otros filtros."
				/>
			</div>
			<div class="card pad grow"><Skeleton lines={4} avatar label="Cargando" /></div>
		</div>
		<div class="row">
			<Button onclick={() => toasts.show('Aviso informativo')}>Aviso</Button>
			<Button onclick={() => toasts.show('Guardado', { kind: 'success' })}>Éxito</Button>
			<Button onclick={() => toasts.show('No se pudo guardar', { kind: 'error' })}>Error</Button>
			<Button
				onclick={() =>
					toasts.show('Hay una nueva versión', {
						timeout: 0,
						action: { label: 'Actualizar', run: () => {} }
					})}>Con acción</Button
			>
			<Button onclick={() => (modalOpen = true)}>Diálogo</Button>
			<Button variant="danger" onclick={() => (confirmOpen = true)}>Confirmación</Button>
		</div>
	</section>

	<section>
		<h2>Aviso de privacidad en bloques (sin HTML)</h2>
		<div class="card pad"><NoticeBlocks blocks={notice} /></div>
	</section>
</main>

<Modal
	bind:open={modalOpen}
	title="Diálogo de ejemplo"
	description="Superficie sólida, foco atrapado, Escape cierra."
>
	<p>Contenido del diálogo.</p>
	{#snippet footer()}<Button variant="primary" onclick={() => (modalOpen = false)}>Aceptar</Button
		>{/snippet}
</Modal>
<ConfirmDialog
	bind:open={confirmOpen}
	title="¿Reiniciar el equipo?"
	description="También se cortan los demás servicios del equipo mientras reinicia."
	confirmLabel="Reiniciar"
	danger
	onconfirm={() => toasts.show('Confirmado')}
/>

<style>
	.catalog {
		max-width: 1100px;
		margin: 0 auto;
		padding: 24px 16px 80px;
	}

	h1 {
		margin: 0 0 4px;
	}

	h2 {
		margin: 36px 0 12px;
		font-size: 1.125rem;
	}

	.appearance {
		display: inline-block;
		padding: 8px;
		border-radius: var(--r-md);
	}

	.swatches {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
		gap: 8px;
	}

	.swatch {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.75rem;
	}

	.chip-color {
		width: 36px;
		height: 36px;
		border-radius: 8px;
		border: 1px solid var(--line-strong);
		flex: none;
	}

	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
		margin: 10px 0;
	}

	.col {
		display: flex;
		flex-direction: column;
		gap: 8px;
		margin-bottom: 10px;
	}

	.backdrop {
		position: relative;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: 16px;
		padding: 24px;
		border-radius: var(--r-lg);
		background:
			repeating-linear-gradient(45deg, #fff 0 18px, #c9a77a 18px 36px), linear-gradient(#fff, #000);
	}

	.demo {
		padding: 16px;
		border-radius: var(--r-md);
		color: var(--text-1);
		font-size: 0.875rem;
	}

	.t2 {
		color: var(--text-2);
	}

	.t3 {
		color: var(--text-3);
	}

	.legend {
		padding: 12px;
		border-radius: var(--r-md);
		max-width: 420px;
	}

	.chart {
		padding: 12px;
		margin: 10px 0;
	}

	.pad {
		padding: 12px;
	}

	.grow {
		flex: 1;
		min-width: 260px;
	}

	.narrow {
		max-width: 360px;
		margin-top: 8px;
	}

	.cards {
		max-width: 420px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.card-row {
		height: 64px;
	}

	.chat {
		display: flex;
		flex-direction: column;
		gap: 12px;
		max-width: 520px;
	}
</style>
