// Rutas de administración (sección 12.4). Solo la sesión por ahora; el resto de las áreas se
// agregan cuando el backend las publique.
import { api } from './client';
import type { AdminSession } from './types';

const AUTH = '/api/v1/admin/auth';

export const adminApi = {
	login: (username: string, password: string) =>
		api.post<AdminSession>(`${AUTH}/login`, { username, password }),
	me: () => api.get<AdminSession>(`${AUTH}/me`),
	logout: () => api.post<{ ok: boolean }>(`${AUTH}/logout`),
	changePassword: (current: string, next: string) =>
		api.post<{ ok: boolean }>(`${AUTH}/password`, { current, new: next })
};
