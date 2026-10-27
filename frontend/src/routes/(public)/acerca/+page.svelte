<!-- Acerca (17.1): qué es, canal mostrado, aviso de privacidad (bloques, nunca HTML), atribuciones y versión. -->
<script lang="ts">
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import { m } from '$lib/paraglide/messages';
	import { site } from '$lib/stores/site.svelte';
	import NoticeBlocks from '$lib/components/notice/NoticeBlocks.svelte';

	const s = $derived(site.data);
	const SAFE = /^https?:\/\//i;
	const software = [{ name: 'MapLibre GL JS', url: 'https://maplibre.org', text: 'BSD-3-Clause' }];
	const attributions = $derived([
		...s.attributions,
		...software.filter((x) => !s.attributions.some((a) => a.name === x.name))
	]);
</script>

<svelte:head><title>{m.about_title()} · {s.name}</title></svelte:head>

<div class="page-scroll page-pad about">
	<h1 class="page-title">{m.about_title()}</h1>

	<section aria-labelledby="a-what">
		<h2 id="a-what" class="section-title">{m.about_what()}</h2>
		{#if s.description}<p class="lead">{s.description}</p>{/if}
		<p>{m.about_what_body()}</p>
	</section>

	<section aria-labelledby="a-ch">
		<h2 id="a-ch" class="section-title">{m.about_channels()}</h2>
		{#if s.public_channels.length}
			<ul class="chips">
				{#each s.public_channels as ch (ch)}<li>{ch}</li>{/each}
			</ul>
		{:else}
			<p class="muted">{m.about_no_channels()}</p>
		{/if}
	</section>

	{#if s.notice.length}
		<section aria-labelledby="a-priv" class="notice card">
			<h2 id="a-priv" class="sr-only">{m.about_privacy()}</h2>
			<NoticeBlocks blocks={s.notice} />
		</section>
	{/if}

	<section aria-labelledby="a-attr">
		<h2 id="a-attr" class="section-title">{m.about_attributions()}</h2>
		<ul class="attr">
			{#each attributions as a (a.name)}
				<li>
					{#if a.url && SAFE.test(a.url)}
						<a href={a.url} target="_blank" rel="noopener noreferrer"
							>{a.name}<ExternalLink size={14} aria-hidden="true" /></a
						>
					{:else}
						<strong>{a.name}</strong>
					{/if}
					{#if a.text}<span class="muted"> — {a.text}</span>{/if}
				</li>
			{/each}
		</ul>
	</section>

	<section aria-labelledby="a-soft">
		<h2 id="a-soft" class="section-title">{m.about_software()}</h2>
		<p>{m.about_software_author()}</p>
		<p>{m.about_software_body()}</p>
		{#if s.version}<p class="muted">{m.about_version({ version: s.version })}</p>{/if}
	</section>
</div>

<style>
	.about {
		max-width: 760px;
	}

	p {
		margin: 0 0 10px;
		line-height: 1.55;
		font-size: 0.9375rem;
	}

	.lead {
		font-weight: 600;
	}

	.muted {
		color: var(--text-2);
	}

	.chips {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.chips li {
		padding: 4px 12px;
		border-radius: 999px;
		background: var(--accent-soft);
		font-weight: 650;
		font-size: 0.875rem;
	}

	.notice {
		margin-top: 20px;
		padding: 4px 16px 6px;
	}

	.attr {
		margin: 0;
		padding-left: 18px;
		font-size: 0.875rem;
		line-height: 1.6;
	}

	.attr a {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		min-height: 32px;
	}
</style>
