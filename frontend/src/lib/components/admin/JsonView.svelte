<!-- JSON de solo lectura (configuración del nodo, contenido decodificado), desplegable. -->
<script lang="ts">
	interface Props {
		value: unknown;
		summary: string;
		open?: boolean;
	}

	let { value, summary, open = false }: Props = $props();
	const text = $derived(JSON.stringify(value, null, 2) ?? '');
</script>

<details class="json" {open}>
	<summary>{summary}</summary>
	<pre class="adm-code">{text}</pre>
</details>

<style>
	.json summary {
		cursor: pointer;
		padding: 8px 0;
		font-size: 0.8125rem;
		font-weight: 650;
	}

	.json pre {
		margin-top: 6px;
	}
</style>
