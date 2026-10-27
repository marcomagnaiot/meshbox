<!-- Fragmentos en línea del aviso: texto, negrita, cursiva, código y enlaces http(s)/mailto. Nunca HTML. -->
<script lang="ts">
	import type { NoticeInline } from '$lib/api/types';

	interface Props {
		items: NoticeInline[];
	}

	let { items }: Props = $props();

	// Defensa adicional: el servidor ya filtra, pero solo se aceptan http(s) y mailto.
	const SAFE = /^(https?:\/\/|mailto:)[^\s<>"']+$/i;
</script>

{#each items as item, i (i)}
	{#if item.t === 'strong'}
		<strong>{item.v}</strong>
	{:else if item.t === 'em'}
		<em>{item.v}</em>
	{:else if item.t === 'code'}
		<code>{item.v}</code>
	{:else if item.t === 'link' && SAFE.test(item.href)}
		<a
			href={item.href}
			target={item.href.startsWith('mailto:') ? undefined : '_blank'}
			rel="noopener noreferrer">{item.v}</a
		>
	{:else}
		{item.v}
	{/if}
{/each}
