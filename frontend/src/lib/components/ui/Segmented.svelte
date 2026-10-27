<!-- Control segmentado (rangos de tiempo, tema, idioma): grupo de radio accesible. -->
<script lang="ts" generics="V extends string">
	interface Option {
		value: V;
		label: string;
		disabled?: boolean;
	}

	interface Props {
		options: Option[];
		value: V;
		label: string;
		onchange?: (value: V) => void;
		size?: 'md' | 'sm';
	}

	let { options, value = $bindable(), label, onchange, size = 'md' }: Props = $props();

	const uid = $props.id();
	const name = `seg-${uid}`;
</script>

<div class="seg {size}" role="radiogroup" aria-label={label}>
	{#each options as opt (opt.value)}
		<label class:checked={opt.value === value} class:disabled={opt.disabled}>
			<input
				type="radio"
				{name}
				value={opt.value}
				checked={opt.value === value}
				disabled={opt.disabled}
				onchange={() => {
					value = opt.value;
					onchange?.(opt.value);
				}}
			/>
			<span>{opt.label}</span>
		</label>
	{/each}
</div>

<style>
	.seg {
		display: inline-flex;
		padding: 3px;
		gap: 2px;
		border-radius: var(--r-sm);
		background: var(--fill-1);
		max-width: 100%;
		overflow-x: auto;
		scrollbar-width: none;
	}

	label {
		/* Sin achicarse: si no entran, el grupo se desplaza de costado. */
		flex: none;
		position: relative;
		display: inline-grid;
		place-items: center;
		min-height: 38px;
		min-width: 44px;
		padding: 0 12px;
		border-radius: 8px;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-2);
		white-space: nowrap;
		cursor: pointer;
		transition: background-color var(--dur-1) var(--ease);
	}

	.sm label {
		min-height: 32px;
		padding: 0 10px;
	}

	@media (pointer: coarse) {
		.sm label {
			min-height: 40px;
		}
	}

	label:hover {
		color: var(--text-1);
	}

	label.checked {
		background: var(--surface-3);
		color: var(--text-1);
		box-shadow: 0 1px 2px oklch(0% 0 0 / 0.2);
	}

	label.disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	input {
		position: absolute;
		opacity: 0;
		inset: 0;
		margin: 0;
		cursor: inherit;
	}

	label:has(input:focus-visible) {
		outline: 2px solid var(--focus);
		outline-offset: 1px;
	}
</style>
