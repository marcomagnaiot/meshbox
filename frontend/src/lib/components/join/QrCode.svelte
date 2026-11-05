<!-- Código QR en SVG, dibujado como un solo trazo (sin HTML inyectado). -->
<script lang="ts">
	import qrcode from 'qrcode-generator';

	interface Props {
		value: string;
		label: string;
		size?: number;
	}

	let { value, label, size = 200 }: Props = $props();
	const MARGIN = 4;

	const qr = $derived.by(() => {
		const q = qrcode(0, 'M');
		q.addData(value);
		q.make();
		const n = q.getModuleCount();
		let d = '';
		for (let r = 0; r < n; r++)
			for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `M${c + MARGIN} ${r + MARGIN}h1v1h-1z`;
		return { d, view: n + MARGIN * 2 };
	});
</script>

<svg
	class="qr"
	width={size}
	height={size}
	viewBox="0 0 {qr.view} {qr.view}"
	role="img"
	aria-label={label}
	shape-rendering="crispEdges"
>
	<rect width={qr.view} height={qr.view} fill="#fff" />
	<path d={qr.d} fill="#000" />
</svg>

<style>
	.qr {
		display: block;
		max-width: 100%;
		height: auto;
		border-radius: var(--r-sm);
	}
</style>
