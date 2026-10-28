<!-- Nombre largo y corto de un nodo (la placa conectada o uno administrado a distancia). -->
<script lang="ts">
	import { untrack } from 'svelte';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import TextField from '$lib/components/admin/TextField.svelte';

	interface Props {
		open: boolean;
		title: string;
		initial: { long_name: string | null; short_name: string | null };
		note?: string;
		onsave: (longName: string, shortName: string) => Promise<boolean>;
	}

	let { open = $bindable(false), title, initial, note, onsave }: Props = $props();

	let longName = $state('');
	let shortName = $state('');
	let error = $state<string | null>(null);
	let saving = $state(false);
	let wasOpen = false;

	$effect.pre(() => {
		if (open && !wasOpen) {
			untrack(() => {
				longName = initial.long_name ?? '';
				shortName = initial.short_name ?? '';
				error = null;
			});
		}
		wasOpen = open;
	});

	async function save(e: SubmitEvent): Promise<void> {
		e.preventDefault();
		const bytes = (s: string) => new TextEncoder().encode(s.trim()).length;
		if (!longName.trim() || bytes(longName) > 39) return void (error = m.adm_cli_long_hint());
		if (!shortName.trim() || bytes(shortName) > 4) return void (error = m.adm_cli_short_hint());
		saving = true;
		try {
			if (await onsave(longName.trim(), shortName.trim())) open = false;
		} finally {
			saving = false;
		}
	}
</script>

<Modal bind:open {title}>
	<form class="adm-stack" onsubmit={save}>
		<TextField
			label={m.adm_cli_long_name()}
			hint={m.adm_cli_long_hint()}
			bind:value={longName}
			maxlength={39}
			required
		/>
		<TextField
			label={m.adm_cli_short_name()}
			hint={m.adm_cli_short_hint()}
			bind:value={shortName}
			maxlength={4}
			required
		/>
		{#if error}<p class="adm-note danger" role="alert">{error}</p>{/if}
		{#if note}<p class="adm-muted">{note}</p>{/if}
		<div class="adm-row end">
			<Button variant="ghost" onclick={() => (open = false)}>{m.adm_cancel()}</Button>
			<Button type="submit" variant="primary" loading={saving}>{m.adm_save()}</Button>
		</div>
	</form>
</Modal>
