<script lang="ts">
	import type { LucideIcon } from '@lucide/svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		icon?: LucideIcon;
		title: string;
		description?: string;
		children?: Snippet;
		compact?: boolean;
	}

	let { icon: Icon, title, description, children, compact = false }: Props = $props();
</script>

<div class="empty" class:compact>
	{#if Icon}
		<span class="icon" aria-hidden="true"><Icon size={compact ? 22 : 28} /></span>
	{/if}
	<p class="title">{title}</p>
	{#if description}<p class="desc">{description}</p>{/if}
	{#if children}<div class="actions">{@render children()}</div>{/if}
</div>

<style>
	.empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		gap: 6px;
		padding: 32px 16px;
		color: var(--text-2);
	}

	.empty.compact {
		padding: 16px 12px;
	}

	.icon {
		display: grid;
		place-items: center;
		width: 52px;
		height: 52px;
		border-radius: 50%;
		background: var(--fill-1);
		color: var(--text-2);
		margin-bottom: 4px;
	}

	.compact .icon {
		width: 40px;
		height: 40px;
	}

	.title {
		margin: 0;
		font-weight: 600;
		color: var(--text-1);
	}

	.desc {
		margin: 0;
		font-size: 0.875rem;
		max-width: 36ch;
	}

	.actions {
		margin-top: 8px;
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		justify-content: center;
	}
</style>
