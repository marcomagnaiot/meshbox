<!-- Celular: buscador tipo píldora (abre la paleta) y fila de chips, en una sola superficie glass. -->
<script lang="ts">
	import Search from '@lucide/svelte/icons/search';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import FilterChips from './FilterChips.svelte';
</script>

<div class="mtop glass glass-text">
	<button type="button" class="pill" onclick={() => (ui.paletteOpen = true)}>
		<img src={site.data.logo_url ?? '/favicon.svg'} alt="" width="24" height="24" />
		<span class="placeholder">{m.search_placeholder()}</span>
		<Search size={18} aria-hidden="true" />
	</button>
	<FilterChips />
</div>

<style>
	.mtop {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 6px;
		border-radius: var(--r-lg);
	}

	.pill {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		height: 44px;
		padding: 0 14px 0 10px;
		border: 0;
		border-radius: 999px;
		background: var(--fill-1);
		color: var(--text-2);
		font: inherit;
		font-size: 0.875rem;
		text-align: left;
	}

	.pill img {
		border-radius: 6px;
		flex: none;
	}

	.placeholder {
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
