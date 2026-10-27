// Armado de la lista del chat: orden cronológico, separadores de día, respuestas y
// reacciones. `reply_id` apunta al `packet_id` del mensaje original; si `emoji` es verdadero,
// el texto es una reacción y se muestra como chip sobre el original (17.1).
import type { Message } from '$lib/api/types';
import { matches } from '$lib/utils/text';

export interface Reaction {
	emoji: string;
	from: Message[];
}

export type ChatItem =
	| { kind: 'day'; key: string; day: string; ts: number }
	| {
			kind: 'message';
			key: string;
			message: Message;
			/** Mensaje respondido: `undefined` si no es respuesta, `null` si no está cargado. */
			replyTo: Message | null | undefined;
			reactions: Reaction[];
	  }
	| { kind: 'reaction'; key: string; message: Message };

export function sortMessages(messages: Iterable<Message>): Message[] {
	return [...messages].sort((a, b) => a.ts - b.ts || a.pk - b.pk);
}

export function buildChatItems(
	messages: Iterable<Message>,
	dayOf: (ts: number) => string,
	query = ''
): ChatItem[] {
	const sorted = sortMessages(messages);
	const byPacket = new Map<number, Message>();
	for (const m of sorted)
		if (m.packet_id !== null && m.packet_id !== undefined) byPacket.set(m.packet_id, m);

	const reactionsOf = new Map<number, Map<string, Message[]>>();
	const orphanReactions = new Set<number>();
	for (const m of sorted) {
		if (!m.emoji || m.reply_id === null || m.reply_id === undefined) continue;
		const target = byPacket.get(m.reply_id);
		if (!target) {
			orphanReactions.add(m.pk);
			continue;
		}
		let byEmoji = reactionsOf.get(target.pk);
		if (!byEmoji) {
			byEmoji = new Map();
			reactionsOf.set(target.pk, byEmoji);
		}
		const list = byEmoji.get(m.text) ?? [];
		list.push(m);
		byEmoji.set(m.text, list);
	}

	const items: ChatItem[] = [];
	let lastDay = '';
	const q = query.trim();
	for (const m of sorted) {
		const isReaction = m.emoji && m.reply_id !== null && m.reply_id !== undefined;
		if (isReaction && !orphanReactions.has(m.pk)) continue; // va como chip del original
		if (q && !matches(q, m.text, m.from_name, m.from)) continue;
		const day = dayOf(m.ts);
		if (day !== lastDay) {
			items.push({ kind: 'day', key: `day-${day}`, day, ts: m.ts });
			lastDay = day;
		}
		if (isReaction) {
			items.push({ kind: 'reaction', key: `m-${m.pk}`, message: m });
			continue;
		}
		const reactions = [...(reactionsOf.get(m.pk)?.entries() ?? [])].map(([emoji, from]) => ({
			emoji,
			from
		}));
		const replyTo =
			m.reply_id === null || m.reply_id === undefined
				? undefined
				: (byPacket.get(m.reply_id) ?? null);
		items.push({ kind: 'message', key: `m-${m.pk}`, message: m, replyTo, reactions });
	}
	return items;
}
