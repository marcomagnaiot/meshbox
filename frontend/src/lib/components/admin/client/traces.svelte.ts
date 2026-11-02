// Traceroutes desde la ficha de un nodo, que es la misma en la pestaña Nodos y al tocar a quien
// escribió en Mensajes: los saltos elegidos y el último pedido a cada nodo. Quedan acá y no en
// la ficha para que siga esperando la respuesta aunque se cierre o se abra desde la otra pestaña.

export interface TraceSent {
	/** Hora del pedido en el servidor: la respuesta tiene que ser posterior. */
	at: number;
	/** Hora del pedido en la PC (ms), para medir la espera. */
	t0: number;
	hops: number;
}

class TraceStore {
	hops = $state(3);
	sent = $state<Record<string, TraceSent>>({});
}

export const traces = new TraceStore();
