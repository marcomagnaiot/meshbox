<!--
  Marco de un paso del asistente: título (recibe el foco al cambiar de paso), descripción,
  contenido y botones (atrás a la izquierda; omitir y continuar a la derecha). Todo el paso es
  un formulario: Enter envía.
-->
<script lang="ts">
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import type { Snippet } from 'svelte';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';

	interface Props {
		title: string;
		description?: string;
		children: Snippet;
		onsubmit: () => void | Promise<void>;
		submitLabel?: string;
		busy?: boolean;
		disabled?: boolean;
		error?: string | null;
		onback?: () => void;
		onskip?: () => void | Promise<void>;
		skipLabel?: string;
		/** Contenido extra al pie (estado, enlaces). */
		footer?: Snippet;
	}

	let {
		title,
		description,
		children,
		onsubmit,
		submitLabel,
		busy = false,
		disabled = false,
		error = null,
		onback,
		onskip,
		skipLabel,
		footer
	}: Props = $props();
</script>

<form
	class="step"
	aria-labelledby="step-title"
	novalidate
	onsubmit={(e) => {
		e.preventDefault();
		if (!busy && !disabled) void onsubmit();
	}}
>
	<header>
		<h2 id="step-title" tabindex="-1">{title}</h2>
		{#if description}<p class="desc">{description}</p>{/if}
	</header>
	<div class="body adm-stack">
		{@render children()}
	</div>
	{#if error}<p class="adm-note danger" role="alert">{error}</p>{/if}
	{#if footer}{@render footer()}{/if}
	<div class="actions">
		{#if onback}
			<Button variant="ghost" icon={ArrowLeft} onclick={onback}>{m.setup_back()}</Button>
		{/if}
		<span class="spacer"></span>
		{#if onskip}
			<Button variant="ghost" onclick={() => onskip?.()}>{skipLabel ?? m.setup_skip()}</Button>
		{/if}
		<Button type="submit" variant="primary" loading={busy} {disabled}
			>{submitLabel ?? m.setup_next()}</Button
		>
	</div>
</form>

<style>
	.step {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}

	h2 {
		margin: 0;
		font-size: 1.375rem;
		font-weight: 650;
		line-height: 1.25;
	}

	h2:focus {
		outline: none;
	}

	.desc {
		margin: 6px 0 0;
		color: var(--text-2);
		line-height: 1.5;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		padding-top: 14px;
		border-top: 1px solid var(--line);
	}

	.spacer {
		flex: 1;
	}
</style>
