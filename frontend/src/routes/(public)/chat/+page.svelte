<script lang="ts">
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import ChatView from '$lib/components/chat/ChatView.svelte';
</script>

<svelte:head><title>{m.nav_chat()} · {site.data.name}</title></svelte:head>

<ChatView />
