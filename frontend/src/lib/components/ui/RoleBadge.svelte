<script lang="ts">
	import RadioTower from '@lucide/svelte/icons/radio-tower';
	import { roleLabel } from '$lib/i18n/labels';

	interface Props {
		role: string;
		infra?: boolean;
	}

	let { role, infra = false }: Props = $props();
</script>

<span class="role" class:infra title={role}>
	{#if infra}<RadioTower size={14} aria-hidden="true" />{/if}
	{roleLabel(role)}
</span>

<style>
	.role {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		min-height: 22px;
		padding: 1px 8px;
		border-radius: 6px;
		background: var(--fill-1);
		color: var(--text-2);
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.01em;
	}

	.role.infra {
		color: var(--text-1);
		background: color-mix(in oklch, var(--st-infra) 18%, transparent);
	}
</style>
