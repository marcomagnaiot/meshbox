<script lang="ts">
	import { Popover } from 'bits-ui';
	import SunMoon from '@lucide/svelte/icons/sun-moon';
	import { m } from '$lib/paraglide/messages';
	import AppearanceControls from './AppearanceControls.svelte';
</script>

<Popover.Root>
	<Popover.Trigger class="btn-icon" aria-label={m.appearance_title()} title={m.appearance_title()}>
		<SunMoon size={20} aria-hidden="true" />
	</Popover.Trigger>
	<Popover.Portal>
		<Popover.Content
			class="menu-surface"
			side="bottom"
			align="end"
			sideOffset={10}
			collisionPadding={12}
		>
			<AppearanceControls />
		</Popover.Content>
	</Popover.Portal>
</Popover.Root>
