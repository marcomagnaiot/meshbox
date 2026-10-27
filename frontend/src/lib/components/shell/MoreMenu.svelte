<!-- "Más" en la barra de pestañas: estadísticas, acerca, paleta y apariencia. -->
<script lang="ts">
	import { Popover } from 'bits-ui';
	import ChartColumn from '@lucide/svelte/icons/chart-column';
	import Command from '@lucide/svelte/icons/command';
	import Ellipsis from '@lucide/svelte/icons/ellipsis';
	import Info from '@lucide/svelte/icons/info';
	import { m } from '$lib/paraglide/messages';
	import { ui } from '$lib/stores/ui.svelte';
	import AppearanceControls from './AppearanceControls.svelte';

	interface Props {
		active?: boolean;
	}

	let { active = false }: Props = $props();
	let open = $state(false);
</script>

<Popover.Root bind:open>
	<Popover.Trigger class="tab more {active ? 'current' : ''}" aria-label={m.more_menu()}>
		<Ellipsis size={22} aria-hidden="true" />
		<span class="tab-label">{m.nav_more()}</span>
	</Popover.Trigger>
	<Popover.Portal>
		<Popover.Content
			class="menu-surface more-menu"
			side="top"
			align="end"
			sideOffset={12}
			collisionPadding={10}
		>
			<nav aria-label={m.nav_sections()}>
				<a class="menu-item" href="/estadisticas" onclick={() => (open = false)}>
					<ChartColumn size={18} aria-hidden="true" />{m.nav_stats()}
				</a>
				<a class="menu-item" href="/acerca" onclick={() => (open = false)}>
					<Info size={18} aria-hidden="true" />{m.nav_about()}
				</a>
				<button
					type="button"
					class="menu-item"
					onclick={() => {
						open = false;
						ui.paletteOpen = true;
					}}
				>
					<Command size={18} aria-hidden="true" />{m.palette_title()}
				</button>
			</nav>
			<p class="menu-heading">{m.appearance_title()}</p>
			<AppearanceControls />
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>

<style>
	:global(.more-menu) {
		width: min(320px, calc(100vw - 24px));
	}
</style>
