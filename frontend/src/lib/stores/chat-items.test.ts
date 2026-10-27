import { describe, expect, it } from 'vitest';
import type { Message } from '$lib/api/types';
import { buildChatItems } from './chat-items';

const msg = (pk: number, ts: number, extra: Partial<Message> = {}): Message => ({
	pk,
	ts,
	from: '!aaaa0001',
	from_name: 'Nodo A',
	channel: 'LongFast',
	text: `mensaje ${pk}`,
	reply_id: null,
	emoji: false,
	packet_id: 1000 + pk,
	...extra
});

const day = (ts: number) => (ts < 100 ? 'd1' : 'd2');

describe('lista del chat (17.1)', () => {
	it('ordena cronológicamente y separa por día', () => {
		const items = buildChatItems([msg(3, 150), msg(1, 10), msg(2, 20)], day);
		expect(items.map((i) => i.kind)).toEqual(['day', 'message', 'message', 'day', 'message']);
		expect(items.filter((i) => i.kind === 'message').map((i) => i.message.pk)).toEqual([1, 2, 3]);
	});

	it('las reacciones (emoji) van como chip del mensaje original (reply_id = packet_id)', () => {
		const original = msg(1, 10);
		const r1 = msg(2, 11, {
			emoji: true,
			text: '👍',
			reply_id: 1001,
			from: '!aaaa0002',
			from_name: 'B'
		});
		const r2 = msg(3, 12, {
			emoji: true,
			text: '👍',
			reply_id: 1001,
			from: '!aaaa0003',
			from_name: 'C'
		});
		const r3 = msg(4, 13, { emoji: true, text: '❤️', reply_id: 1001 });
		const items = buildChatItems([original, r1, r2, r3], day);
		const messages = items.filter((i) => i.kind === 'message');
		expect(messages).toHaveLength(1);
		const first = messages[0];
		if (first.kind !== 'message') throw new Error();
		expect(first.reactions.map((r) => [r.emoji, r.from.length])).toEqual([
			['👍', 2],
			['❤️', 1]
		]);
	});

	it('una reacción a un mensaje no cargado se muestra sola', () => {
		const items = buildChatItems([msg(5, 10, { emoji: true, text: '👍', reply_id: 999 })], day);
		expect(items.map((i) => i.kind)).toEqual(['day', 'reaction']);
	});

	it('las respuestas citan el original; si no está cargado, lo dicen', () => {
		const items = buildChatItems(
			[msg(1, 10), msg(2, 11, { reply_id: 1001 }), msg(3, 12, { reply_id: 4242 }), msg(4, 13)],
			day
		);
		const byPk = new Map(items.filter((i) => i.kind === 'message').map((i) => [i.message.pk, i]));
		const reply = byPk.get(2);
		const orphan = byPk.get(3);
		const plain = byPk.get(4);
		expect(reply?.kind === 'message' && reply.replyTo?.pk).toBe(1);
		expect(orphan?.kind === 'message' && orphan.replyTo).toBeNull();
		expect(plain?.kind === 'message' && plain.replyTo).toBeUndefined();
	});

	it('la búsqueda filtra por texto y nombre, sin acentos', () => {
		const items = buildChatItems(
			[msg(1, 10, { text: 'Llegué bien' }), msg(2, 11, { text: 'otra cosa', from_name: 'Ñandú' })],
			day,
			'llegue'
		);
		expect(items.filter((i) => i.kind === 'message')).toHaveLength(1);
		expect(buildChatItems([msg(2, 11, { from_name: 'Ñandú' })], day, 'nandu')).toHaveLength(2);
	});
});
