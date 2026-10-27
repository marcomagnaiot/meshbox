<!--
  Servicios del equipo (18.2): estado en systemd (`active` booleano y `state` en texto) y, para
  quien administra, reinicio con confirmación. privd no se reinicia desde el panel.
-->
<script lang="ts">
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import * as adminApi from '$lib/admin/api';
	import { serviceLabel } from '$lib/admin/labels';
	import type { ServiceStatus } from '$lib/admin/types';
	import { fmt } from '$lib/i18n/fmt.svelte';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';
	import ConfirmAction from '../ConfirmAction.svelte';
	import StatusPill from '../StatusPill.svelte';

	type Restartable = 'meshbox' | 'mosquitto' | 'meshbox-cloudflared';

	interface Props {
		services: ServiceStatus[];
		canRestart?: boolean;
		onrestarted?: (name: Restartable) => void;
	}

	let { services, canRestart = false, onrestarted }: Props = $props();

	const RESTARTABLE = new Set<string>(['meshbox', 'mosquitto', 'meshbox-cloudflared']);
	let target = $state<Restartable | null>(null);
	let open = $state(false);

	function detail(svc: ServiceStatus): string {
		const parts: string[] = [];
		if (svc.version) parts.push(`v${svc.version}`);
		if (svc.uptime_s !== undefined) parts.push(`${m.adm_uptime()} ${fmt.duration(svc.uptime_s)}`);
		else if (svc.since) parts.push(m.adm_since({ time: fmt.dateTime(svc.since) }));
		if (svc.restarts) parts.push(m.adm_restarts({ count: svc.restarts }));
		if (svc.error) parts.push(svc.error);
		return parts.join(' · ');
	}

	function ask(name: string): void {
		if (!RESTARTABLE.has(name)) return;
		target = name as Restartable;
		open = true;
	}
</script>

<ul class="services">
	{#each services as svc (svc.name)}
		<li>
			<div class="svc-main">
				<span class="svc-name">{serviceLabel(svc.name)}</span>
				<StatusPill active={svc.active} state={svc.state} />
			</div>
			<p class="adm-muted">{detail(svc)}</p>
			{#if canRestart && RESTARTABLE.has(svc.name)}
				<Button
					size="sm"
					variant="ghost"
					icon={RotateCcw}
					onclick={() => ask(svc.name)}
					aria-label="{m.adm_restart()} {serviceLabel(svc.name)}">{m.adm_restart()}</Button
				>
			{/if}
		</li>
	{/each}
</ul>

<ConfirmAction
	bind:open
	title={m.adm_restart_service_title({ name: target ? serviceLabel(target) : '' })}
	description={target === 'meshbox' ? m.adm_restart_meshbox_desc() : m.adm_restart_service_desc()}
	confirmLabel={m.adm_restart()}
	danger={target === 'meshbox'}
	action={() => adminApi.system.restartService(target!)}
	onsuccess={() => {
		if (target) onrestarted?.(target);
	}}
/>

<style>
	.services {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.services li {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: 2px 12px;
		padding-bottom: 12px;
		border-bottom: 1px solid var(--line);
	}

	.services li:last-child {
		border-bottom: 0;
		padding-bottom: 0;
	}

	.svc-main {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 12px;
	}

	.svc-name {
		font-weight: 650;
	}

	.services p {
		grid-column: 1;
		margin: 0;
	}

	.services :global(.btn) {
		grid-column: 2;
		grid-row: 1 / span 2;
	}
</style>
