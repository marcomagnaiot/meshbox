<!-- Texto para copiar (comandos del Heltec, contraseñas de una sola vez, ACL). -->
<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import Copy from '@lucide/svelte/icons/copy';
	import { m } from '$lib/paraglide/messages';
	import { toasts } from '$lib/stores/ui.svelte';

	interface Props {
		text: string;
		label: string;
		/** Una sola línea (contraseña): sin saltos y con el botón al costado. */
		inline?: boolean;
	}

	let { text, label, inline = false }: Props = $props();
	let copied = $state(false);
	let pre: HTMLElement | null = $state(null);

	async function copy(): Promise<void> {
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			// Sin permiso del portapapeles (HTTP en la LAN): se selecciona para copiar a mano.
			if (pre) {
				const range = document.createRange();
				range.selectNodeContents(pre);
				const sel = window.getSelection();
				sel?.removeAllRanges();
				sel?.addRange(range);
			}
			toasts.show(m.adm_copy_failed(), { kind: 'warning' });
		}
	}
</script>

<div class="copy" class:inline>
	<pre class="adm-code" bind:this={pre} aria-label={label} tabindex="-1">{text}</pre>
	<button type="button" class="btn" onclick={copy} aria-label="{m.adm_copy()}: {label}">
		{#if copied}<Check size={16} aria-hidden="true" />{:else}<Copy
				size={16}
				aria-hidden="true"
			/>{/if}
		<span>{copied ? m.adm_copied() : m.adm_copy()}</span>
	</button>
	<span class="sr-only" aria-live="polite">{copied ? m.adm_copied() : ''}</span>
</div>

<style>
	.copy {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}

	.copy.inline {
		flex-direction: row;
		align-items: stretch;
	}

	.copy.inline pre {
		flex: 1;
		white-space: nowrap;
		overflow-x: auto;
	}

	.btn {
		align-self: flex-end;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 36px;
		padding: 0 12px;
		border: 1px solid var(--line);
		border-radius: var(--r-sm);
		background: var(--fill-1);
		color: var(--text-1);
		font: inherit;
		font-size: 0.8125rem;
		font-weight: 600;
	}

	.inline .btn {
		align-self: stretch;
	}

	.btn:hover {
		background: var(--fill-2);
	}

	@media (pointer: coarse) {
		.btn {
			min-height: 44px;
		}
	}
</style>
