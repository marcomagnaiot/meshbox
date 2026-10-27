<script lang="ts">
	import type { LucideIcon } from '@lucide/svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		pressed?: boolean;
		icon?: LucideIcon;
		onclick?: (e: MouseEvent) => void;
		children: Snippet;
		/** Indicador visual a la izquierda (por ejemplo, el glifo de estado). */
		lead?: Snippet;
		class?: string;
	}

	let { pressed = false, icon: Icon, onclick, children, lead, class: klass = '' }: Props = $props();
</script>

<button type="button" class="chip {klass}" aria-pressed={pressed} {onclick}>
	{#if lead}{@render lead()}{:else if Icon}<Icon size={16} aria-hidden="true" />{/if}
	<span>{@render children()}</span>
</button>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		flex: none;
		height: 34px;
		padding: 0 12px;
		border-radius: 999px;
		border: 1px solid var(--line);
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 500;
		white-space: nowrap;
		position: relative;
		transition: background-color var(--dur-1) var(--ease);
	}

	/* Zona táctil de 44 px sin agrandar el chip visible. */
	.chip::after {
		content: '';
		position: absolute;
		inset: -5px -2px;
	}

	.chip:hover {
		background: var(--fill-2);
	}

	.chip[aria-pressed='true'] {
		background: var(--accent-soft);
		border-color: color-mix(in oklch, var(--accent) 60%, transparent);
		color: var(--text-1);
		font-weight: 600;
	}
</style>
