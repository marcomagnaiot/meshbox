<!-- Interruptor accesible (bits-ui Switch) con etiqueta y ayuda. -->
<script lang="ts">
	import { Switch } from 'bits-ui';

	interface Props {
		checked: boolean;
		label: string;
		hint?: string;
		disabled?: boolean;
		onchange?: (checked: boolean) => void;
	}

	let { checked = $bindable(false), label, hint, disabled = false, onchange }: Props = $props();
	const uid = $props.id();
	const id = `sw-${uid}`;
</script>

<div class="toggle">
	<span class="text">
		<label for={id}>{label}</label>
		{#if hint}<span class="hint" id="{id}-hint">{hint}</span>{/if}
	</span>
	<Switch.Root
		{id}
		bind:checked
		{disabled}
		class="switch"
		aria-describedby={hint ? `${id}-hint` : undefined}
		onCheckedChange={(v) => onchange?.(v)}
	>
		<Switch.Thumb class="switch-thumb" />
	</Switch.Root>
</div>

<style>
	.toggle {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		min-height: 44px;
	}

	.text {
		display: flex;
		flex-direction: column;
	}

	label {
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
	}

	.hint {
		font-size: 0.75rem;
		color: var(--text-2);
	}

	:global(.switch) {
		position: relative;
		flex: none;
		width: 44px;
		height: 26px;
		border-radius: 999px;
		border: 1px solid var(--line-strong);
		background: var(--fill-2);
		padding: 0;
		transition: background-color var(--dur-1) var(--ease);
	}

	:global(.switch[data-state='checked']) {
		background: var(--accent);
		border-color: transparent;
	}

	:global(.switch-thumb) {
		display: block;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		background: var(--text-1);
		transform: translateX(2px);
		transition: transform var(--dur-1) var(--ease);
	}

	:global(.switch[data-state='checked'] .switch-thumb) {
		transform: translateX(20px);
		background: var(--on-accent);
	}
</style>
