<!-- Paleta de comandos (Ctrl+K): páginas, nodos y acciones de apariencia e idioma. -->
<script lang="ts">
	import { Command, Dialog } from 'bits-ui';
	import Bell from '@lucide/svelte/icons/bell';
	import ChartColumn from '@lucide/svelte/icons/chart-column';
	import Contrast from '@lucide/svelte/icons/contrast';
	import Info from '@lucide/svelte/icons/info';
	import Languages from '@lucide/svelte/icons/languages';
	import List from '@lucide/svelte/icons/list';
	import MapIcon from '@lucide/svelte/icons/map';
	import MessageCircle from '@lucide/svelte/icons/message-circle';
	import Moon from '@lucide/svelte/icons/moon';
	import Sun from '@lucide/svelte/icons/sun';
	import { goto } from '$app/navigation';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { i18n } from '$lib/i18n/locale.svelte';
	import { m } from '$lib/paraglide/messages';
	import { clock } from '$lib/stores/clock.svelte';
	import { live } from '$lib/stores/live.svelte';
	import { prefs } from '$lib/stores/prefs.svelte';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import { nodeHref } from '$lib/utils/ids';
	import { displayName, shortName } from '$lib/utils/nodes';
	import { classify } from '$lib/utils/status';
	import { fold } from '$lib/utils/text';
	import StatusGlyph from '$lib/components/ui/StatusGlyph.svelte';

	let search = $state('');

	const pages = $derived([
		{ href: '/', label: m.nav_map(), icon: MapIcon },
		{ href: '/nodos', label: m.nav_nodes(), icon: List },
		{ href: '/chat', label: m.nav_chat(), icon: MessageCircle },
		{ href: '/alertas', label: m.nav_alerts(), icon: Bell },
		{ href: '/estadisticas', label: m.nav_stats(), icon: ChartColumn },
		{ href: '/acerca', label: m.nav_about(), icon: Info }
	]);

	const nodes = $derived(
		live
			.nodeList()
			.sort((a, b) => b.last_heard - a.last_heard)
			.slice(0, 300)
	);

	function go(href: string) {
		ui.paletteOpen = false;
		search = '';
		void goto(href);
	}

	function act(fn: () => void) {
		fn();
		ui.paletteOpen = false;
		search = '';
	}

	// Búsqueda sin acentos y por palabras.
	function filter(value: string, query: string, keywords?: string[]): number {
		const hay = fold(`${value} ${(keywords ?? []).join(' ')}`);
		const terms = fold(query).trim().split(/\s+/).filter(Boolean);
		if (!terms.length) return 1;
		return terms.every((t) => hay.includes(t)) ? 1 : 0;
	}
</script>

<Dialog.Root bind:open={ui.paletteOpen}>
	<Dialog.Portal>
		<Dialog.Overlay class="modal-overlay" />
		<Dialog.Content class="palette surface-raised">
			<Dialog.Title class="sr-only">{m.palette_title()}</Dialog.Title>
			<Command.Root label={m.palette_title()} {filter} loop>
				<Command.Input
					class="palette-input"
					placeholder={m.palette_placeholder()}
					bind:value={search}
				/>
				<Command.List class="palette-list">
					<Command.Viewport>
						<Command.Empty class="palette-empty">{m.palette_empty()}</Command.Empty>
						<Command.Group>
							<Command.GroupHeading class="menu-heading">{m.palette_pages()}</Command.GroupHeading>
							<Command.GroupItems>
								{#each pages as p (p.href)}
									<Command.Item class="menu-item" value={p.label} onSelect={() => go(p.href)}>
										<p.icon size={18} aria-hidden="true" />
										{p.label}
									</Command.Item>
								{/each}
							</Command.GroupItems>
						</Command.Group>
						<Command.Group>
							<Command.GroupHeading class="menu-heading">{m.palette_nodes()}</Command.GroupHeading>
							<Command.GroupItems>
								{#each nodes as n (n.id)}
									<Command.Item
										class="menu-item"
										value={`${displayName(n)} ${n.id}`}
										keywords={[shortName(n), n.hw_model ?? '']}
										onSelect={() => go(nodeHref(n.id))}
									>
										<StatusGlyph
											status={classify(n.last_heard, clock.now, site.data.thresholds)}
											infra={n.is_infra}
											fixed={n.is_fixed}
										/>
										<span class="grow">{displayName(n)}</span>
										<span class="muted">{shortName(n)} · {fmt.relative(n.last_heard)}</span>
									</Command.Item>
								{/each}
							</Command.GroupItems>
						</Command.Group>
						<Command.Group>
							<Command.GroupHeading class="menu-heading">{m.palette_actions()}</Command.GroupHeading
							>
							<Command.GroupItems>
								<Command.Item
									class="menu-item"
									value={`${m.appearance_theme()} ${m.theme_dark()}`}
									onSelect={() => act(() => prefs.setTheme('dark'))}
								>
									<Moon size={18} aria-hidden="true" />{m.appearance_theme()}: {m.theme_dark()}
								</Command.Item>
								<Command.Item
									class="menu-item"
									value={`${m.appearance_theme()} ${m.theme_light()}`}
									onSelect={() => act(() => prefs.setTheme('light'))}
								>
									<Sun size={18} aria-hidden="true" />{m.appearance_theme()}: {m.theme_light()}
								</Command.Item>
								<Command.Item
									class="menu-item"
									value={m.appearance_solid()}
									onSelect={() => act(() => prefs.setSolid(!prefs.solid))}
								>
									<Contrast size={18} aria-hidden="true" />{m.appearance_solid()}: {prefs.solid
										? '✓'
										: '—'}
								</Command.Item>
								<Command.Item
									class="menu-item"
									value={`${m.appearance_language()} ${i18n.locale === 'es' ? 'English' : 'Español'}`}
									onSelect={() => act(() => i18n.set(i18n.locale === 'es' ? 'en' : 'es'))}
								>
									<Languages size={18} aria-hidden="true" />{m.appearance_language()}: {i18n.locale ===
									'es'
										? 'English'
										: 'Español'}
								</Command.Item>
							</Command.GroupItems>
						</Command.Group>
					</Command.Viewport>
				</Command.List>
			</Command.Root>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<style>
	:global(.palette) {
		position: fixed;
		z-index: var(--z-modals);
		left: 50%;
		top: max(12vh, calc(var(--safe-top) + 12px));
		transform: translateX(-50%);
		width: min(620px, calc(100vw - 24px));
		border-radius: var(--r-lg);
		background: var(--surface-1);
		overflow: hidden;
		animation: fade-in var(--dur-1) var(--ease);
	}

	:global(.palette-input) {
		width: 100%;
		height: 56px;
		padding: 0 20px;
		border: 0;
		border-bottom: 1px solid var(--line);
		background: transparent;
		color: var(--text-1);
		font: inherit;
		font-size: 1rem;
	}

	:global(.palette-input:focus-visible) {
		outline: none;
		box-shadow: inset 0 -2px 0 var(--focus);
	}

	:global(.palette-list) {
		max-height: min(60dvh, 480px);
		overflow: auto;
		padding: 6px 8px 10px;
	}

	:global(.palette-empty) {
		padding: 16px;
		color: var(--text-2);
		text-align: center;
	}

	.grow {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.muted {
		font-size: 0.75rem;
		color: var(--text-2);
		white-space: nowrap;
	}
</style>
