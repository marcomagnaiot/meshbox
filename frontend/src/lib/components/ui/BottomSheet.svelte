<!--
  Panel inferior con tres anclajes (16.3): resumen de 96 px, mitad y 92 %. Implementación
  propia (ver docs/diseño/componentes.md): arrastre con Pointer Events, ajuste al anclaje más
  cercano o al siguiente según la velocidad, resorte con transform (nunca se anima el
  desenfoque) y control por teclado desde el asa.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { m } from '$lib/paraglide/messages';
	import type { SheetAnchor } from '$lib/stores/ui.svelte';

	interface Props {
		anchor: SheetAnchor;
		label: string;
		/** Distancia al borde inferior (barra de pestañas + zona segura), en px. */
		bottomOffset?: number;
		header?: Snippet;
		children: Snippet;
		/** Alto visible actual (para que el mapa ajuste su relleno). */
		visibleHeight?: number;
	}

	let {
		anchor = $bindable('peek'),
		label,
		bottomOffset = 0,
		header,
		children,
		// Prop enlazada: el padre lee el alto visible (la regla no ve esa lectura).
		// eslint-disable-next-line no-useless-assignment
		visibleHeight = $bindable(0)
	}: Props = $props();

	const PEEK = 96;
	const ORDER: SheetAnchor[] = ['peek', 'half', 'full'];

	let viewportH = $state(typeof window === 'undefined' ? 800 : window.innerHeight);
	let safeTop = $state(0);
	let dragOffset = $state<number | null>(null);
	let dragZoneH = $state(72);

	const available = $derived(Math.max(240, viewportH - bottomOffset));
	const heights = $derived({
		peek: PEEK,
		half: Math.round(available * 0.5),
		full: Math.round(Math.min(available * 0.92, available - safeTop - 8))
	});
	const fullH = $derived(heights.full);
	const settled = $derived(heights[anchor]);
	const visible = $derived(dragOffset ?? settled);
	const translate = $derived(fullH - visible);

	$effect(() => {
		visibleHeight = settled;
	});

	$effect(() => {
		const onResize = () => {
			viewportH = window.innerHeight;
			const probe = getComputedStyle(document.documentElement).getPropertyValue('--safe-top');
			safeTop = parseFloat(probe) || 0;
		};
		onResize();
		window.addEventListener('resize', onResize);
		return () => window.removeEventListener('resize', onResize);
	});

	// ------------------------------------------------------------ arrastre

	let startY = 0;
	let startVisible = 0;
	let moved = false;
	let samples: { t: number; y: number }[] = [];

	function onPointerDown(e: PointerEvent) {
		if (e.button !== 0) return;
		const target = e.target as HTMLElement;
		// Los controles del encabezado siguen funcionando (salvo el asa, que también arrastra).
		if (target.closest('a, input, select, textarea, [data-no-drag]')) return;
		if (target.closest('button') && !target.closest('.handle')) return;
		startY = e.clientY;
		startVisible = settled;
		moved = false;
		samples = [{ t: performance.now(), y: e.clientY }];
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
	}

	function onPointerMove(e: PointerEvent) {
		if (!(e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) return;
		const dy = startY - e.clientY;
		if (!moved && Math.abs(dy) < 6) return;
		moved = true;
		let next = startVisible + dy;
		// Resistencia elástica fuera de los extremos.
		if (next > fullH) next = fullH + (next - fullH) * 0.25;
		if (next < PEEK) next = PEEK - (PEEK - next) * 0.25;
		dragOffset = next;
		const now = performance.now();
		samples.push({ t: now, y: e.clientY });
		samples = samples.filter((s) => now - s.t < 120);
	}

	function onPointerUp(e: PointerEvent) {
		const el = e.currentTarget as HTMLElement;
		if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
		if (!moved || dragOffset === null) {
			dragOffset = null;
			return;
		}
		const first = samples[0];
		const last = samples[samples.length - 1];
		const dt = Math.max(1, last.t - first.t);
		const velocity = (first.y - last.y) / dt; // px/ms, positivo hacia arriba
		const current = dragOffset;
		let target: SheetAnchor;
		if (Math.abs(velocity) > 0.55) {
			const idx = ORDER.indexOf(nearest(current));
			const dir = velocity > 0 ? 1 : -1;
			const candidate = ORDER[Math.max(0, Math.min(ORDER.length - 1, idx + dir))];
			target = heights[candidate] * dir > current * dir ? candidate : nearest(current);
		} else {
			target = nearest(current);
		}
		dragOffset = null;
		anchor = target;
	}

	function nearest(h: number): SheetAnchor {
		let best: SheetAnchor = 'peek';
		for (const a of ORDER) if (Math.abs(heights[a] - h) < Math.abs(heights[best] - h)) best = a;
		return best;
	}

	// ------------------------------------------------------------ teclado

	function cycle() {
		const idx = ORDER.indexOf(anchor);
		anchor = idx === ORDER.length - 1 ? 'peek' : ORDER[idx + 1];
	}

	function onHandleKey(e: KeyboardEvent) {
		const idx = ORDER.indexOf(anchor);
		if (e.key === 'ArrowUp') {
			anchor = ORDER[Math.min(ORDER.length - 1, idx + 1)];
			e.preventDefault();
		} else if (e.key === 'ArrowDown') {
			anchor = ORDER[Math.max(0, idx - 1)];
			e.preventDefault();
		} else if (e.key === 'Home') {
			anchor = 'full';
			e.preventDefault();
		} else if (e.key === 'End') {
			anchor = 'peek';
			e.preventDefault();
		}
	}

	const stateLabel = $derived(
		anchor === 'peek'
			? m.panel_state_peek()
			: anchor === 'half'
				? m.panel_state_half()
				: m.panel_state_full()
	);
</script>

<section
	class="sheet glass glass-text"
	class:dragging={dragOffset !== null}
	aria-label={label}
	style="height: {fullH}px; bottom: {bottomOffset}px; transform: translate3d(0, {translate}px, 0)"
	data-anchor={anchor}
>
	<div
		class="drag-zone"
		bind:clientHeight={dragZoneH}
		onpointerdown={onPointerDown}
		onpointermove={onPointerMove}
		onpointerup={onPointerUp}
		onpointercancel={onPointerUp}
		role="presentation"
	>
		<button
			type="button"
			class="handle"
			aria-label={m.panel_handle({ state: stateLabel })}
			aria-expanded={anchor !== 'peek'}
			onclick={() => {
				if (!moved) cycle();
			}}
			onkeydown={onHandleKey}
		>
			<span class="grabber" aria-hidden="true"></span>
		</button>
		{#if header}
			<div class="header">{@render header()}</div>
		{/if}
	</div>
	<div class="body" inert={anchor === 'peek'} style="height: {Math.max(0, settled - dragZoneH)}px">
		{@render children()}
	</div>
</section>

<style>
	.sheet {
		position: fixed;
		left: max(0px, var(--safe-left));
		right: max(0px, var(--safe-right));
		z-index: var(--z-sheet);
		display: flex;
		flex-direction: column;
		border-radius: var(--r-xl) var(--r-xl) 0 0;
		border-bottom: 0;
		transition:
			transform 340ms var(--ease-spring),
			opacity var(--dur-2) var(--ease);
		will-change: transform;
	}

	.sheet.dragging {
		transition: none;
	}

	@media (prefers-reduced-motion: reduce) {
		.sheet {
			transition: none;
		}
	}

	.drag-zone {
		flex: none;
		cursor: grab;
		touch-action: none;
		user-select: none;
	}

	.dragging .drag-zone {
		cursor: grabbing;
	}

	.handle {
		display: grid;
		place-items: center;
		width: 100%;
		height: 24px;
		border: 0;
		background: transparent;
		padding: 0;
		cursor: inherit;
	}

	.grabber {
		width: 40px;
		height: 5px;
		border-radius: 3px;
		background: var(--text-3);
		opacity: 0.8;
	}

	.header {
		padding: 0 16px 8px;
		min-height: 48px;
	}

	.body {
		flex: none;
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
		touch-action: pan-y;
		border-top: 1px solid var(--line);
	}
</style>
