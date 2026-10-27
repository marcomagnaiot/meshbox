<!--
  Progreso de un trabajo largo (actualización, descarga del extracto, cambio de red): barra con
  role="progressbar", paso, mensaje y error; el texto se anuncia con aria-live.
-->
<script lang="ts">
	import { jobStepLabel } from '$lib/admin/labels';
	import { m } from '$lib/paraglide/messages';

	interface Props {
		state: string;
		/** 0 a 1, o null si no se conoce. */
		progress?: number | null;
		step?: string | null;
		message?: string | null;
		error?: string | null;
		label: string;
	}

	let {
		state,
		progress = null,
		step = null,
		message = null,
		error = null,
		label
	}: Props = $props();
	const running = $derived(state === 'running');
	const ok = $derived(state === 'succeeded' || state === 'done');
	const failed = $derived(state === 'failed' || state === 'error');
	const pct = $derived(
		progress === null ? null : Math.round(Math.min(1, Math.max(0, progress)) * 100)
	);
	const text = $derived(
		running ? m.adm_job_running() : ok ? m.adm_job_succeeded() : failed ? m.adm_job_failed() : state
	);
</script>

<div class="job" class:failed class:ok>
	<div
		class="bar"
		role="progressbar"
		aria-label={label}
		aria-valuemin={0}
		aria-valuemax={100}
		aria-valuenow={pct ?? undefined}
		aria-valuetext={pct === null ? text : `${pct} %`}
	>
		<span
			class="fill"
			class:indeterminate={running && pct === null}
			style="width: {pct ?? (ok ? 100 : 30)}%"
		></span>
	</div>
	<p class="status" aria-live="polite">
		<strong>{text}</strong>{#if pct !== null && running}
			· {pct} %{/if}{#if step}
			· {m.adm_job_step({ step: jobStepLabel(step) })}{/if}
	</p>
	{#if message && !failed}<p class="msg">{message}</p>{/if}
	{#if error}<p class="msg err" role="alert">{error}</p>{/if}
</div>

<style>
	.job {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.bar {
		height: 8px;
		border-radius: 999px;
		background: var(--fill-2);
		overflow: hidden;
	}

	.fill {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: var(--accent);
		transition: width var(--dur-2) var(--ease);
	}

	.ok .fill {
		background: var(--success);
	}

	.failed .fill {
		background: var(--danger);
	}

	.fill.indeterminate {
		animation: slide 1.4s var(--ease) infinite;
	}

	@keyframes slide {
		0% {
			transform: translateX(-100%);
		}
		100% {
			transform: translateX(340%);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.fill.indeterminate {
			animation: none;
		}
	}

	.status,
	.msg {
		margin: 0;
		font-size: 0.8125rem;
	}

	.msg {
		color: var(--text-2);
		overflow-wrap: anywhere;
	}

	.msg.err {
		color: var(--text-1);
		padding-left: 8px;
		border-left: 3px solid var(--danger);
	}
</style>
