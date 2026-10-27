<script lang="ts">
	import type { LucideIcon } from '@lucide/svelte';
	import LoaderCircle from '@lucide/svelte/icons/loader-circle';
	import type { Snippet } from 'svelte';
	import type { HTMLAnchorAttributes, HTMLButtonAttributes } from 'svelte/elements';

	type Common = {
		variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
		size?: 'md' | 'sm';
		icon?: LucideIcon;
		loading?: boolean;
		full?: boolean;
		children?: Snippet;
	};
	type Props = Common &
		(
			| (Omit<HTMLButtonAttributes, 'children'> & { href?: undefined })
			| (Omit<HTMLAnchorAttributes, 'children'> & { href: string })
		);

	let {
		variant = 'secondary',
		size = 'md',
		icon: Icon,
		loading = false,
		full = false,
		children,
		class: klass = '',
		...rest
	}: Props = $props();
</script>

{#if rest.href !== undefined}
	<a class="btn {variant} {size} {klass}" class:full {...rest as HTMLAnchorAttributes}>
		{#if Icon}<Icon size={18} aria-hidden="true" />{/if}
		{@render children?.()}
	</a>
{:else}
	<button
		type="button"
		class="btn {variant} {size} {klass}"
		class:full
		aria-busy={loading || undefined}
		{...rest as HTMLButtonAttributes}
		disabled={(rest as HTMLButtonAttributes).disabled || loading}
	>
		{#if loading}
			<LoaderCircle size={18} class="animate-spin" aria-hidden="true" />
		{:else if Icon}
			<Icon size={18} aria-hidden="true" />
		{/if}
		{@render children?.()}
	</button>
{/if}

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		min-height: 44px;
		padding: 0 16px;
		border-radius: var(--r-sm);
		border: 1px solid transparent;
		font: inherit;
		font-size: 0.875rem;
		font-weight: 600;
		line-height: 1.2;
		text-decoration: none;
		white-space: nowrap;
		color: var(--text-1);
		background: var(--fill-1);
		transition:
			background-color var(--dur-1) var(--ease),
			transform var(--dur-1) var(--ease);
	}

	.btn.sm {
		min-height: 36px;
		padding: 0 12px;
		font-size: 0.8125rem;
	}

	@media (pointer: coarse) {
		.btn.sm {
			min-height: 44px;
		}
	}

	.btn:hover {
		background: var(--fill-2);
	}

	.btn:active {
		transform: scale(0.98);
	}

	.btn.full {
		width: 100%;
	}

	.btn.primary {
		background: var(--accent);
		color: var(--on-accent);
	}

	.btn.primary:hover {
		background: color-mix(in oklch, var(--accent) 88%, white);
	}

	.btn.secondary {
		border-color: var(--line);
	}

	.btn.ghost {
		background: transparent;
	}

	.btn.ghost:hover {
		background: var(--fill-1);
	}

	.btn.danger {
		background: var(--danger-soft);
		color: var(--text-1);
		border-color: color-mix(in oklch, var(--danger) 50%, transparent);
	}

	.btn:disabled {
		opacity: 0.55;
		transform: none;
	}
</style>
