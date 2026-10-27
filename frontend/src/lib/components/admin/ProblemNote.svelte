<!--
  Error de una carga o acción: `detail` del servidor y su `code` (RFC 9457), con reintentar.
  En un equipo compartido (409 shared_mode) explica por qué la acción no existe.
-->
<script lang="ts">
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { problemCode, problemText, isSharedModeError } from '$lib/admin/errors';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';

	interface Props {
		error: unknown;
		title?: string;
		onretry?: () => void;
	}

	let { error, title, onretry }: Props = $props();
	const code = $derived(problemCode(error));
	const shared = $derived(isSharedModeError(error));
</script>

<div class="note" class:shared role="alert">
	<TriangleAlert size={18} aria-hidden="true" />
	<div class="text">
		<p class="title">{title ?? m.adm_load_error()}</p>
		<p>{problemText(error)}</p>
		{#if code && !shared}<p class="code">code: <code>{code}</code></p>{/if}
	</div>
	{#if onretry}<Button size="sm" onclick={onretry}>{m.retry()}</Button>{/if}
</div>

<style>
	.note {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		padding: 12px;
		border-radius: var(--r-sm);
		background: var(--danger-soft);
		color: var(--text-1);
		font-size: 0.875rem;
	}

	.note.shared {
		background: var(--warning-soft);
	}

	.text {
		flex: 1;
		min-width: 0;
	}

	p {
		margin: 0;
		line-height: 1.45;
		overflow-wrap: anywhere;
	}

	.title {
		font-weight: 650;
	}

	.code {
		margin-top: 4px;
		font-size: 0.75rem;
		color: var(--text-2);
	}
</style>
