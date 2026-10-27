<!--
  Armazón del sitio público (16.3): el mapa ocupa toda la pantalla y la capa flotante cambia
  según el ancho. Celular: buscador y chips arriba, controles a la derecha, panel inferior con
  tres anclajes y barra de pestañas. Tableta: panel izquierdo de 360 px plegable. PC: barra
  superior, panel izquierdo de 380 px con pestañas y ficha a la derecha de 420 px. Celular
  apaisado: panel lateral. Como máximo cuatro superficies glass visibles.
-->
<script lang="ts">
	import Command from '@lucide/svelte/icons/command';
	import Info from '@lucide/svelte/icons/info';
	import MapIcon from '@lucide/svelte/icons/map';
	import PanelLeft from '@lucide/svelte/icons/panel-left';
	import PanelLeftClose from '@lucide/svelte/icons/panel-left-close';
	import { onMount, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { m } from '$lib/paraglide/messages';
	import { alerts } from '$lib/stores/alerts.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { mapData } from '$lib/stores/mapdata.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { filters, selection, ui } from '$lib/stores/ui.svelte';
	import { sheetAnchorFor, viewFor } from '$lib/stores/view';
	import SosBanner from '$lib/components/alerts/SosBanner.svelte';
	import NodesList from '$lib/components/node/NodesList.svelte';
	import BottomSheet from '$lib/components/ui/BottomSheet.svelte';
	import IconButton from '$lib/components/ui/IconButton.svelte';
	import AppearanceMenu from '$lib/components/shell/AppearanceMenu.svelte';
	import CommandPalette from '$lib/components/shell/CommandPalette.svelte';
	import MapControls from '$lib/components/shell/MapControls.svelte';
	import MobileTop from '$lib/components/shell/MobileTop.svelte';
	import OfflineBanner from '$lib/components/shell/OfflineBanner.svelte';
	import PanelTabs from '$lib/components/shell/PanelTabs.svelte';
	import SummaryStrip from '$lib/components/shell/SummaryStrip.svelte';
	import TabBar from '$lib/components/shell/TabBar.svelte';
	import TopBar from '$lib/components/shell/TopBar.svelte';

	let { children } = $props();

	// MapLibre fuera del paquete inicial: se pide ya, en paralelo con los datos.
	const mapModule = import('$lib/map/MapView.svelte');

	let searchInput: HTMLInputElement | null = $state(null);
	let viewportH = $state(800);
	let portrait = $state(false);

	const view = $derived(viewFor(page.route.id));
	const nodeId = $derived(view === 'node' ? (page.params.id ?? null) : null);
	const layout = $derived(ui.layout);
	const tabbarH = 64;

	$effect(() => {
		selection.select(nodeId);
	});

	// Al cambiar de vista, el panel inferior toma el anclaje de esa vista.
	$effect(() => {
		const v = view;
		untrack(() => (ui.sheet = sheetAnchorFor(v)));
	});

	onMount(() => {
		live.start();
		void alerts.load();
		void site.load().then((s) => {
			filters.applySiteDefault(s.features.show_inactive);
			if (s.features.links) void mapData.loadLinks();
			if (s.features.waypoints) void mapData.loadWaypoints();
		});
		const onResize = () => {
			viewportH = window.innerHeight;
			portrait = window.innerHeight > window.innerWidth;
		};
		onResize();
		window.addEventListener('resize', onResize);
		return () => {
			window.removeEventListener('resize', onResize);
			live.stop();
		};
	});

	function onKey(e: KeyboardEvent) {
		if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
			e.preventDefault();
			ui.paletteOpen = !ui.paletteOpen;
			return;
		}
		const target = e.target as HTMLElement | null;
		if (target?.closest('input, textarea, select, [contenteditable="true"]')) return;
		if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
		if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
			e.preventDefault();
			if (searchInput) searchInput.focus();
			else ui.paletteOpen = true;
		} else if (e.key === 'Escape' && view === 'node') {
			void goto('/');
		}
	}

	// Relleno del mapa: lo que tapan los paneles (centrar un nodo lo deja a la vista).
	const padding = $derived.by(() => {
		switch (layout) {
			case 'desktop':
				return { top: 84, left: 412, right: view === 'node' ? 452 : 72, bottom: 16 };
			case 'tablet':
				return {
					top: 84,
					left: ui.sideCollapsed ? 16 : 392,
					right: view === 'node' && !portrait ? 392 : 72,
					bottom: view === 'node' && portrait ? Math.round(viewportH * 0.45) : 16
				};
			case 'landscape':
				return { top: 16, left: ui.sideCollapsed ? 16 : 376, right: 64, bottom: 16 };
			default:
				return { top: 120, left: 8, right: 60, bottom: ui.sheetHeight + tabbarH };
		}
	});

	// Atribución del mapa: siempre a la vista, entre los paneles (nunca debajo de la ficha).
	const attrBottom = $derived(
		layout === 'mobile'
			? ui.sheetHeight + tabbarH + 4
			: layout === 'tablet' && view === 'node' && portrait
				? Math.round(viewportH * 0.45) + 24
				: 8
	);
	const attrRight = $derived(
		layout === 'desktop' && view === 'node'
			? 452
			: layout === 'tablet' && view === 'node' && !portrait
				? 392
				: layout === 'landscape'
					? 64
					: 16
	);
	const attrLeft = $derived(
		layout === 'desktop'
			? 412
			: layout === 'tablet' || layout === 'landscape'
				? ui.sideCollapsed
					? 8
					: 392
				: 4
	);
	const bannerTop = $derived(layout === 'mobile' ? 112 : layout === 'landscape' ? 8 : 80);
</script>

<svelte:window onkeydown={onKey} />

<div
	class="shell"
	data-layout={layout}
	style="--attr-bottom: {attrBottom}px; --attr-left: {attrLeft}px; --attr-right: {attrRight}px; --banner-top: {bannerTop}px"
>
	{#await mapModule then mod}
		<mod.default {padding} />
	{:catch}
		<p class="map-failed" role="alert">{m.map_error()}</p>
	{/await}

	<SosBanner />

	{#if layout === 'desktop'}
		<div class="area-top"><TopBar bind:searchInput /></div>
		<aside class="panel left glass glass-text" aria-label={m.nav_sections()}>
			<div class="panel-head">
				<SummaryStrip />
				<PanelTabs {view} />
			</div>
			{#if view === 'node'}
				<div class="panel-body"><NodesList /></div>
			{:else}
				<main id="contenido" class="panel-body" tabindex="-1">{@render children()}</main>
			{/if}
		</aside>
		{#if view === 'node'}
			<main id="contenido" class="panel right glass glass-text" tabindex="-1">
				<div class="page-scroll">{@render children()}</div>
			</main>
		{/if}
		<div class="area-controls" class:shifted={view === 'node'}><MapControls /></div>
	{:else if layout === 'tablet' || layout === 'landscape'}
		{#if layout === 'tablet'}
			<div class="area-top" class:collapsed={ui.sideCollapsed}>
				<TopBar bind:searchInput compact />
			</div>
		{/if}
		{#if ui.sideCollapsed}
			<div class="area-reopen glass-sm">
				<IconButton
					icon={PanelLeft}
					label={m.panel_show()}
					onclick={() => (ui.sideCollapsed = false)}
				/>
			</div>
		{:else}
			<aside class="panel side glass glass-text" aria-label={m.nav_sections()}>
				<div class="panel-head">
					<div class="side-head">
						<SummaryStrip compact={layout === 'landscape'} />
						<IconButton
							icon={PanelLeftClose}
							label={m.panel_hide()}
							size="sm"
							onclick={() => (ui.sideCollapsed = true)}
						/>
					</div>
					{#if layout === 'landscape'}
						<!-- Apaisado: herramientas y pestañas (solo íconos) en una sola fila. -->
						<div class="side-row">
							<div class="side-tools">
								<a class="btn-icon" href="/" aria-label={m.nav_map()} title={m.nav_map()}
									><MapIcon size={20} aria-hidden="true" /></a
								>
								<IconButton
									icon={Command}
									label={m.palette_open()}
									size="sm"
									onclick={() => (ui.paletteOpen = true)}
								/>
								<a class="btn-icon" href="/acerca" aria-label={m.nav_about()} title={m.nav_about()}
									><Info size={20} aria-hidden="true" /></a
								>
								<AppearanceMenu />
							</div>
							<PanelTabs {view} compact />
						</div>
					{:else}
						<PanelTabs {view} />
					{/if}
				</div>
				{#if view === 'node' && layout === 'tablet'}
					<div class="panel-body"><NodesList /></div>
				{:else}
					<main id="contenido" class="panel-body" tabindex="-1">
						{#if view === 'node'}<div class="page-scroll">
								{@render children()}
							</div>{:else}{@render children()}{/if}
					</main>
				{/if}
			</aside>
		{/if}
		{#if view === 'node' && (layout === 'tablet' || ui.sideCollapsed)}
			<main
				id="contenido"
				class="panel node-panel glass glass-text"
				class:bottom={portrait}
				class:wide={ui.sideCollapsed}
				tabindex="-1"
			>
				<div class="page-scroll">{@render children()}</div>
			</main>
		{/if}
		<div class="area-controls" class:shifted={view === 'node' && layout === 'tablet' && !portrait}>
			<MapControls showZoom={layout === 'tablet'} />
		</div>
	{:else}
		<!-- Con el panel al 92 % la barra superior se oculta: no queda glass sobre glass. -->
		<div class="area-mtop" class:hidden={ui.sheet === 'full'} inert={ui.sheet === 'full'}>
			<MobileTop />
		</div>
		<div class="area-controls"><MapControls showZoom={false} layerSide="left" /></div>
		<BottomSheet
			bind:anchor={ui.sheet}
			bind:visibleHeight={ui.sheetHeight}
			bottomOffset={tabbarH}
			label={m.nav_sections()}
		>
			{#snippet header()}<SummaryStrip compact />{/snippet}
			<main id="contenido" class="sheet-main" tabindex="-1">{@render children()}</main>
		</BottomSheet>
		<div class="area-tabbar"><TabBar {view} /></div>
	{/if}

	<div class="area-offline"><OfflineBanner /></div>
	<CommandPalette />
</div>

<style>
	.shell {
		position: fixed;
		inset: 0;
		overflow: hidden;
		background: var(--bg);
	}

	.map-failed {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		margin: 0;
		color: var(--text-2);
	}

	.area-top {
		position: absolute;
		z-index: var(--z-panels);
		top: calc(16px + var(--safe-top));
		left: calc(16px + var(--safe-left));
		right: calc(16px + var(--safe-right));
	}

	[data-layout='tablet'] .area-top {
		left: calc(392px + var(--safe-left));
	}

	[data-layout='tablet'] .area-top.collapsed {
		left: calc(76px + var(--safe-left));
	}

	.panel {
		position: absolute;
		z-index: var(--z-panels);
		display: flex;
		flex-direction: column;
		border-radius: var(--r-lg);
		overflow: hidden;
	}

	.panel.left {
		top: calc(92px + var(--safe-top));
		bottom: calc(16px + var(--safe-bottom));
		left: calc(16px + var(--safe-left));
		width: 380px;
	}

	.panel.right {
		top: calc(92px + var(--safe-top));
		bottom: calc(16px + var(--safe-bottom));
		right: calc(16px + var(--safe-right));
		width: 420px;
	}

	.panel.side {
		top: calc(16px + var(--safe-top));
		bottom: calc(16px + var(--safe-bottom));
		left: calc(16px + var(--safe-left));
		width: 360px;
	}

	[data-layout='landscape'] .panel.side {
		top: calc(8px + var(--safe-top));
		bottom: calc(8px + var(--safe-bottom));
		left: calc(8px + var(--safe-left));
		width: min(360px, 46vw);
	}

	.panel.node-panel {
		top: calc(92px + var(--safe-top));
		bottom: calc(16px + var(--safe-bottom));
		right: calc(16px + var(--safe-right));
		width: 360px;
	}

	.panel.node-panel.bottom {
		top: auto;
		left: calc(392px + var(--safe-left));
		right: calc(16px + var(--safe-right));
		width: auto;
		height: 45%;
	}

	.panel.node-panel.bottom.wide {
		left: calc(16px + var(--safe-left));
	}

	[data-layout='landscape'] .panel.node-panel {
		top: calc(8px + var(--safe-top));
		bottom: calc(8px + var(--safe-bottom));
		right: auto;
		left: calc(8px + var(--safe-left));
		width: min(360px, 46vw);
	}

	.panel-head {
		flex: none;
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 14px 14px 10px;
		border-bottom: 1px solid var(--line);
	}

	.side-head {
		display: flex;
		align-items: flex-start;
		gap: 8px;
	}

	.side-head > :global(:first-child) {
		flex: 1;
		min-width: 0;
	}

	.side-tools {
		display: flex;
		gap: 2px;
	}

	.side-row {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.side-row > :global(:last-child) {
		flex: 1;
	}

	[data-layout='landscape'] .panel-head {
		gap: 6px;
		padding: 8px 10px 6px;
	}

	.panel-body {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
	}

	.panel-body:focus,
	.panel:focus,
	.sheet-main:focus {
		outline: none;
	}

	.area-reopen {
		position: absolute;
		z-index: var(--z-panels);
		top: calc(16px + var(--safe-top));
		left: calc(16px + var(--safe-left));
		padding: 4px;
		border-radius: var(--r-md);
	}

	.area-controls {
		position: absolute;
		z-index: var(--z-controls);
		right: calc(16px + var(--safe-right));
		top: calc(92px + var(--safe-top));
		transition: transform var(--dur-2) var(--ease);
	}

	[data-layout='desktop'] .area-controls.shifted {
		transform: translateX(-436px);
	}

	[data-layout='tablet'] .area-controls.shifted {
		transform: translateX(-376px);
	}

	[data-layout='landscape'] .area-controls {
		top: calc(8px + var(--safe-top));
		right: calc(8px + var(--safe-right));
	}

	[data-layout='mobile'] .area-controls {
		top: calc(132px + var(--safe-top));
		right: calc(8px + var(--safe-right));
	}

	.area-mtop {
		position: absolute;
		z-index: var(--z-panels);
		top: calc(8px + var(--safe-top));
		left: calc(8px + var(--safe-left));
		right: calc(8px + var(--safe-right));
		transition:
			opacity var(--dur-2) var(--ease),
			transform var(--dur-2) var(--ease);
	}

	.area-mtop.hidden {
		opacity: 0;
		transform: translateY(-12px);
		pointer-events: none;
	}

	.sheet-main {
		display: flex;
		flex-direction: column;
		height: 100%;
		min-height: 0;
	}

	.area-tabbar {
		position: absolute;
		z-index: calc(var(--z-sheet) + 1);
		left: 0;
		right: 0;
		bottom: 0;
	}

	.area-offline {
		position: absolute;
		z-index: var(--z-toasts);
		left: 50%;
		transform: translateX(-50%);
		bottom: calc(24px + var(--safe-bottom));
		pointer-events: none;
	}

	[data-layout='mobile'] .area-offline {
		top: calc(120px + var(--safe-top));
		bottom: auto;
	}
</style>
