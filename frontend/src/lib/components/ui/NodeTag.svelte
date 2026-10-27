<!--
  Nombre corto de un nodo sobre su color, el mismo que le da la app de Meshtastic. El color
  ayuda a reconocerlo de un vistazo, pero el nombre siempre está escrito (no depende del color).
-->
<script lang="ts">
	import { nodeColorStyle } from '$lib/utils/node-color';

	interface Props {
		id: string | null | undefined;
		label: string;
		size?: 'sm' | 'md';
	}

	let { id, label, size = 'sm' }: Props = $props();
	const style = $derived(nodeColorStyle(id));
</script>

<span class="tag {size}" class:colored={Boolean(style)} {style}>{label}</span>

<style>
	.tag {
		display: inline-flex;
		align-items: center;
		flex: none;
		min-height: 18px;
		padding: 0 6px;
		border-radius: 5px;
		font-size: 0.75rem;
		font-weight: 700;
		line-height: 1.2;
		white-space: nowrap;
		background: var(--fill-2);
		color: var(--text-2);
	}

	.tag.colored {
		background: var(--node);
		color: var(--node-ink);
		/* Borde sutil: un color casi igual al fondo de la página igual se distingue. */
		box-shadow: inset 0 0 0 1px oklch(50% 0 0 / 0.3);
	}

	.md {
		min-height: 22px;
		padding: 0 8px;
		font-size: 0.8125rem;
	}
</style>
