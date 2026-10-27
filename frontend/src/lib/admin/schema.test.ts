import { describe, expect, it } from 'vitest';
import { clean, defaults, fieldKind, resolve, validate, withDefaults } from './schema';
import type { JsonSchema } from './types';

// Forma de los esquemas de pydantic: $defs, anyOf con null, enum, listas y objetos anidados.
const ROOT: JsonSchema = {
	type: 'object',
	$defs: {
		Scope: {
			type: 'object',
			properties: {
				nodes: { type: 'array', items: { type: 'string' }, default: [] },
				channel: { anyOf: [{ type: 'string' }, { type: 'null' }], default: null }
			}
		},
		Field: {
			type: 'object',
			properties: {
				path: { type: 'string', maxLength: 120 },
				unit: { type: 'string', maxLength: 12 }
			},
			required: ['path']
		}
	},
	properties: {
		patterns: { type: 'array', items: { type: 'string' }, minItems: 1 },
		mode: { type: 'string', enum: ['any', 'all'], default: 'any' },
		hops: { type: 'integer', minimum: 0, maximum: 7, default: 3 },
		scope: { $ref: '#/$defs/Scope' },
		fields: { type: 'array', items: { $ref: '#/$defs/Field' } },
		url: { type: 'string', pattern: 'https?://.+', maxLength: 500 },
		notes: { type: 'string', maxLength: 2000 },
		token: { type: 'string', writeOnly: true, minLength: 10 },
		public: { type: 'boolean' }
	},
	required: ['patterns', 'token']
};

describe('resolve', () => {
	it('sigue $ref y separa anyOf con null', () => {
		const scope = resolve(ROOT.properties!.scope, ROOT).schema;
		expect(Object.keys(scope.properties ?? {})).toEqual(['nodes', 'channel']);
		const channel = resolve(scope.properties!.channel, ROOT);
		expect(channel).toMatchObject({ nullable: true, schema: { type: 'string' } });
	});

	it('acepta type como lista con null', () => {
		expect(resolve({ type: ['integer', 'null'] }, ROOT)).toEqual({
			schema: { type: 'integer' },
			nullable: true
		});
	});
});

describe('fieldKind', () => {
	it.each([
		['patterns', 'string-list'],
		['mode', 'enum'],
		['hops', 'integer'],
		['scope', 'object'],
		['fields', 'object-list'],
		['url', 'string'],
		['notes', 'text'],
		['token', 'secret'],
		['public', 'boolean']
	])('%s → %s', (key, kind) => {
		expect(fieldKind(ROOT.properties![key], ROOT)).toBe(kind);
	});
});

describe('defaults y withDefaults', () => {
	it('toma los default, arma los objetos anidados y deja listas vacías', () => {
		expect(defaults(ROOT)).toEqual({
			patterns: [],
			mode: 'any',
			hops: 3,
			scope: { nodes: [], channel: null },
			fields: [],
			public: false
		});
	});

	it('conserva lo guardado y completa claves nuevas', () => {
		const v = withDefaults(ROOT, { hops: 5, scope: { nodes: ['!a1b2c3d4'] } });
		expect(v.hops).toBe(5);
		expect(v.mode).toBe('any');
		expect(v.scope).toEqual({ nodes: ['!a1b2c3d4'], channel: null });
	});
});

describe('validate', () => {
	const base = { ...defaults(ROOT), patterns: ['sos'], token: 'x'.repeat(12) };

	it('un valor completo no tiene errores', () => {
		expect(validate(ROOT, base)).toEqual({});
	});

	it('marca obligatorios, límites y elementos de listas por ruta', () => {
		const errors = validate(ROOT, {
			...base,
			token: '',
			hops: 9,
			mode: 'otro',
			fields: [{ path: '' }]
		});
		expect(Object.keys(errors).sort()).toEqual(['fields.0.path', 'hops', 'mode', 'token']);
	});

	it('un secreto ya guardado no es obligatorio', () => {
		const errors = validate(ROOT, { ...base, token: '' }, ROOT, '', {
			secretsSet: (path) => path === 'token'
		});
		expect(errors).toEqual({});
	});

	it('controla minItems y largo mínimo', () => {
		const errors = validate(ROOT, { ...base, patterns: [], token: 'corto' });
		expect(Object.keys(errors).sort()).toEqual(['patterns', 'token']);
	});
});

describe('clean', () => {
	it('quita opcionales vacíos y secretos sin escribir, conserva null donde se admite', () => {
		const out = clean(ROOT, {
			patterns: ['sos'],
			mode: 'any',
			hops: 3,
			scope: { nodes: [], channel: null },
			fields: [{ path: 'temperature', unit: '' }],
			url: '',
			notes: '   ',
			token: '',
			public: false
		});
		expect(out).toEqual({
			patterns: ['sos'],
			mode: 'any',
			hops: 3,
			scope: { nodes: [], channel: null },
			fields: [{ path: 'temperature' }],
			public: false
		});
	});

	it('envía el secreto cuando se escribe', () => {
		expect(clean(ROOT, { patterns: ['a'], token: 'nuevo-secreto' }).token).toBe('nuevo-secreto');
	});
});
