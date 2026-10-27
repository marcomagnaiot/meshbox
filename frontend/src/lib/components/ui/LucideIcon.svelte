<!--
  Base liviana para los íconos de Lucide (reemplaza `@lucide/svelte/dist/Icon.svelte` en el
  build, ver vite.config.ts). El original arma los atributos con varios $derived y dibuja cada
  trazo con un <svelte:element>; acá el contenido del SVG se arma una sola vez por ícono y se
  inserta con {@html}. Admite lo que usa la app: size, color, strokeWidth, class y el resto de
  atributos (aria-*, style). Sin etiqueta accesible queda aria-hidden, como en Lucide.
-->
<script module lang="ts">
	type IconNode = [string, Record<string, string | number>][];

	const markup = new Map<string, string>();

	function escape(v: string | number): string {
		return String(v).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
	}

	function inner(name: string, node: IconNode): string {
		let html = markup.get(name);
		if (html === undefined) {
			html = node
				.map(
					([tag, attrs]) =>
						`<${tag} ${Object.entries(attrs)
							.filter(([k]) => k !== 'key')
							.map(([k, v]) => `${k}="${escape(v)}"`)
							.join(' ')}/>`
				)
				.join('');
			markup.set(name, html);
		}
		return html;
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		icon: { name: string; size?: number; node: IconNode };
		size?: number | string;
		color?: string;
		strokeWidth?: number | string;
		absoluteStrokeWidth?: boolean;
		class?: string;
		children?: Snippet;
		[attr: string]: unknown;
	}

	let {
		icon,
		size = 24,
		color = 'currentColor',
		strokeWidth = 2,
		absoluteStrokeWidth = false,
		class: klass = '',
		children,
		...rest
	}: Props = $props();

	const stroke = $derived(
		absoluteStrokeWidth ? (Number(strokeWidth) * 24) / Number(size) : strokeWidth
	);
	const labelled = $derived(
		Boolean(children) ||
			Object.keys(rest).some((k) => k === 'aria-label' || k === 'aria-labelledby' || k === 'title')
	);
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke={color}
	stroke-width={stroke}
	stroke-linecap="round"
	stroke-linejoin="round"
	class="lucide-icon lucide lucide-{icon.name} {klass}"
	aria-hidden={labelled ? undefined : 'true'}
	{...rest}
>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- trazos fijos de Lucide, con los valores escapados en inner() -->
	{@html inner(icon.name, icon.node)}
	{@render children?.()}
</svg>
