<script lang="ts">
	import type { NodeStatus } from '$lib/api/types';
	import { statusLabel } from '$lib/i18n/labels';
	import StatusGlyph from './StatusGlyph.svelte';

	interface Props {
		status: NodeStatus;
		infra?: boolean;
		fixed?: boolean;
		/** Texto adicional ("escuchado hace 12 min"). */
		detail?: string;
	}

	let { status, infra = false, fixed = false, detail }: Props = $props();
</script>

<span class="badge" data-status={status}>
	<StatusGlyph {status} {infra} {fixed} size={16} />
	<span class="label">{statusLabel(status)}</span>
	{#if detail}<span class="detail">· {detail}</span>{/if}
</span>

<style>
	.badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 26px;
		padding: 2px 10px 2px 6px;
		border-radius: 999px;
		background: color-mix(in oklch, var(--st-active) 14%, transparent);
		font-size: 0.8125rem;
		color: var(--text-1);
	}

	.badge[data-status='recent'] {
		background: color-mix(in oklch, var(--st-recent) 16%, transparent);
	}

	.badge[data-status='late'] {
		background: color-mix(in oklch, var(--st-late) 16%, transparent);
	}

	.badge[data-status='inactive'] {
		background: var(--fill-1);
	}

	.label {
		font-weight: 600;
	}

	.detail {
		color: var(--text-2);
	}
</style>
