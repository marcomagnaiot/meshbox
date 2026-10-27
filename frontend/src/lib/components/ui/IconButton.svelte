<script lang="ts">
	import type { LucideIcon } from '@lucide/svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';

	interface Props extends Omit<HTMLButtonAttributes, 'type'> {
		/** Nombre accesible (también se muestra como ayuda emergente). */
		label: string;
		icon: LucideIcon;
		size?: 'md' | 'sm';
		variant?: 'ghost' | 'fill' | 'accent';
		pressed?: boolean;
		iconStyle?: string;
		type?: 'button' | 'submit';
		element?: HTMLButtonElement | null;
	}

	let {
		label,
		icon: Icon,
		size = 'md',
		variant = 'ghost',
		pressed,
		iconStyle,
		type = 'button',
		element = $bindable(null),
		class: klass = '',
		...rest
	}: Props = $props();
</script>

<button
	bind:this={element}
	{type}
	class="icon-btn {variant} {size} {klass}"
	aria-label={label}
	title={label}
	aria-pressed={pressed}
	{...rest}
>
	<Icon size={size === 'sm' ? 18 : 20} aria-hidden="true" style={iconStyle} />
</button>

<style>
	.icon-btn {
		display: inline-grid;
		place-items: center;
		flex: none;
		width: 44px;
		height: 44px;
		border-radius: var(--r-sm);
		color: var(--text-1);
		background: transparent;
		border: 0;
		transition:
			background-color var(--dur-1) var(--ease),
			transform var(--dur-1) var(--ease);
	}

	.icon-btn.sm {
		width: 36px;
		height: 36px;
	}

	/* Puntero preciso: el botón chico mantiene 44 px de zona táctil en pantallas táctiles. */
	@media (pointer: coarse) {
		.icon-btn.sm {
			width: 44px;
			height: 44px;
		}
	}

	.icon-btn:hover {
		background: var(--fill-2);
	}

	.icon-btn:active {
		transform: scale(0.96);
	}

	.icon-btn.fill {
		background: var(--fill-1);
	}

	.icon-btn.accent,
	.icon-btn[aria-pressed='true'] {
		background: var(--accent-soft);
		color: var(--accent-ink);
	}

	.icon-btn:disabled {
		opacity: 0.45;
		background: transparent;
	}
</style>
