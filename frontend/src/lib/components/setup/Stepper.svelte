<!--
  Pasos del asistente: lista con el actual marcado (aria-current="step"), los hechos con tilde
  y los alcanzables como botón. En pantallas angostas, solo "Paso N de M" y una barra.
-->
<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import type { SetupStep } from '$lib/admin/types';
	import { m } from '$lib/paraglide/messages';
	import type { Wizard } from '$lib/setup/wizard.svelte';
	import { stepLabel } from '$lib/setup/labels';

	interface Props {
		wizard: Wizard;
	}

	let { wizard }: Props = $props();
	const total = $derived(wizard.steps.length);
	const position = $derived(Math.max(0, wizard.index) + 1);

	function state(step: SetupStep): 'current' | 'done' | 'pending' {
		if (step === wizard.current) return 'current';
		return wizard.isDone(step) ? 'done' : 'pending';
	}
</script>

<nav class="stepper" aria-label={m.setup_steps()}>
	<p class="compact" aria-hidden="true">
		{m.setup_step_of({ n: position, total })} · <strong>{stepLabel(wizard.current)}</strong>
	</p>
	<div class="bar" aria-hidden="true">
		<span style="width: {(position / Math.max(1, total)) * 100}%"></span>
	</div>
	<ol>
		{#each wizard.steps as step, i (step)}
			{@const st = state(step)}
			<li class={st}>
				{#if st !== 'current' && wizard.reachable(step)}
					<button type="button" onclick={() => wizard.go(step)}>
						<span class="dot" aria-hidden="true">
							{#if st === 'done'}<Check size={14} />{:else}{i + 1}{/if}
						</span>
						<span class="name">{stepLabel(step)}</span>
						{#if st === 'done'}<span class="sr-only">({m.setup_step_done()})</span>{/if}
					</button>
				{:else}
					<span class="item" aria-current={st === 'current' ? 'step' : undefined}>
						<span class="dot" aria-hidden="true">
							{#if st === 'done'}<Check size={14} />{:else}{i + 1}{/if}
						</span>
						<span class="name">{stepLabel(step)}</span>
						{#if st === 'done'}<span class="sr-only">({m.setup_step_done()})</span>{/if}
					</span>
				{/if}
			</li>
		{/each}
	</ol>
</nav>

<style>
	ol {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	button,
	.item {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		min-height: 40px;
		padding: 0 10px;
		border: 0;
		border-radius: 8px;
		background: none;
		color: var(--text-2);
		font: inherit;
		font-size: 0.875rem;
		text-align: left;
	}

	button {
		cursor: pointer;
	}

	button:hover {
		background: var(--fill-1);
		color: var(--text-1);
	}

	.current .item {
		background: var(--accent-soft);
		color: var(--text-1);
		font-weight: 650;
	}

	.dot {
		flex: none;
		display: grid;
		place-items: center;
		width: 24px;
		height: 24px;
		border-radius: 50%;
		border: 1.5px solid var(--line-strong, var(--line));
		font-size: 0.75rem;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.done .dot {
		border-color: transparent;
		background: var(--success);
		color: var(--on-accent, #fff);
	}

	.current .dot {
		border-color: var(--accent);
		background: var(--accent);
		color: var(--on-accent, #fff);
	}

	.compact,
	.bar {
		display: none;
	}

	@media (max-width: 820px) {
		ol {
			display: none;
		}

		.compact {
			display: block;
			margin: 0 0 8px;
			font-size: 0.875rem;
			color: var(--text-2);
		}

		.compact strong {
			color: var(--text-1);
		}

		.bar {
			display: block;
			height: 6px;
			border-radius: 999px;
			background: var(--fill-2);
			overflow: hidden;
		}

		.bar span {
			display: block;
			height: 100%;
			border-radius: inherit;
			background: var(--accent);
			transition: width var(--dur-2) var(--ease);
		}
	}
</style>
