<script lang="ts">
	import Compass from '@lucide/svelte/icons/compass';
	import { page } from '$app/state';
	import { m } from '$lib/paraglide/messages';
	import Button from '$lib/components/ui/Button.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
</script>

<svelte:head
	><title>{page.status === 404 ? m.not_found_title() : m.error_generic()}</title></svelte:head
>

<main id="contenido" class="error-page">
	<h1 class="sr-only">{page.status === 404 ? m.not_found_title() : m.error_generic()}</h1>
	<EmptyState
		icon={Compass}
		title={page.status === 404 ? m.not_found_title() : m.error_generic()}
		description={page.status === 404 ? m.not_found_body() : (page.error?.message ?? '')}
	>
		<Button href="/" variant="primary">{m.go_home()}</Button>
	</EmptyState>
</main>

<style>
	.error-page {
		min-height: 100dvh;
		display: grid;
		place-items: center;
		padding: 24px;
	}
</style>
