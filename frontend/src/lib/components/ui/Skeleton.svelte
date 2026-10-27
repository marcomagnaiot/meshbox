<!-- Esqueleto de carga: bloques con brillo suave (sin animación con movimiento reducido). -->
<script lang="ts">
	interface Props {
		lines?: number;
		height?: string;
		label?: string;
		avatar?: boolean;
	}

	let { lines = 3, height = '14px', label, avatar = false }: Props = $props();
</script>

<div class="sk" role="status" aria-live="polite" aria-busy="true">
	{#if label}<span class="sr-only">{label}</span>{/if}
	{#each Array.from({ length: lines }, (_, i) => i) as i (i)}
		<div class="row" aria-hidden="true">
			{#if avatar}<span class="skeleton avatar"></span>{/if}
			<span
				class="skeleton bar"
				style="height: {height}; width: {i === lines - 1 ? 62 : 100 - (i % 3) * 9}%"
			></span>
		</div>
	{/each}
</div>

<style>
	.sk {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 4px 0;
	}

	.row {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.avatar {
		width: 28px;
		height: 28px;
		border-radius: 50%;
		flex: none;
	}

	.bar {
		display: block;
	}
</style>
