// Formularios generados desde JSON Schema (18.3): el backend (pydantic) define las reglas y el
// panel valida igual antes de enviar. Cubre el subconjunto que usan las reglas de alerta y los
// plugins: objetos anidados ($ref/$defs), anyOf con null, enum/const, números con límites,
// textos con largo y patrón, listas de textos o números y listas de objetos.
import { m } from '$lib/paraglide/messages';
import type { JsonSchema } from './types';

export type FieldKind =
	| 'boolean'
	| 'integer'
	| 'number'
	| 'string'
	| 'secret'
	| 'text'
	| 'enum'
	| 'multi-enum'
	| 'string-list'
	| 'number-list'
	| 'object'
	| 'object-list'
	| 'unknown';

export interface Resolved {
	schema: JsonSchema;
	nullable: boolean;
}

/** Sigue `$ref` dentro de `$defs`, une `allOf` y separa `anyOf [X, null]`. */
export function resolve(schema: JsonSchema, root: JsonSchema): Resolved {
	let s: JsonSchema = schema;
	let nullable = false;
	for (let guard = 0; guard < 8; guard++) {
		if (s.$ref) {
			const name = s.$ref.replace(/^#\/(\$defs|definitions)\//, '');
			const target = root.$defs?.[name];
			const { $ref: _ref, ...rest } = s;
			s = target ? { ...target, ...rest } : rest;
			continue;
		}
		if (s.allOf && s.allOf.length) {
			const { allOf, ...rest } = s;
			s = Object.assign({}, ...allOf, rest);
			continue;
		}
		const alts = s.anyOf ?? s.oneOf;
		if (alts && alts.length) {
			const nonNull = alts.filter((a) => a.type !== 'null');
			nullable = nullable || nonNull.length < alts.length;
			const { anyOf: _a, oneOf: _o, ...rest } = s;
			s = nonNull.length === 1 ? { ...nonNull[0], ...rest } : { ...rest, type: 'string' };
			continue;
		}
		break;
	}
	if (Array.isArray(s.type)) {
		nullable = nullable || s.type.includes('null');
		s = { ...s, type: s.type.find((t) => t !== 'null') };
	}
	return { schema: s, nullable };
}

export function fieldKind(schema: JsonSchema, root: JsonSchema): FieldKind {
	const { schema: s } = resolve(schema, root);
	if (s.enum || s.const !== undefined) return 'enum';
	switch (s.type) {
		case 'boolean':
			return 'boolean';
		case 'integer':
			return 'integer';
		case 'number':
			return 'number';
		case 'string':
			if (s.writeOnly || s.format === 'password') return 'secret';
			// Direcciones y correos en una línea aunque admitan textos largos.
			if (s.format === 'uri' || s.format === 'email' || /^\^?https\?/.test(s.pattern ?? ''))
				return 'string';
			if ((s.maxLength ?? 0) > 500 || s.format === 'textarea') return 'text';
			return 'string';
		case 'array': {
			const item = s.items ? resolve(s.items, root).schema : {};
			if (item.enum) return 'multi-enum';
			if (item.type === 'number' || item.type === 'integer') return 'number-list';
			if (item.type === 'object' || item.properties) return 'object-list';
			return 'string-list';
		}
		case 'object':
			return 'object';
		default:
			return s.properties ? 'object' : 'unknown';
	}
}

/** Valor inicial con los `default` del esquema (los objetos anidados también). */
export function defaults(schema: JsonSchema, root: JsonSchema = schema): Record<string, unknown> {
	const { schema: s } = resolve(schema, root);
	const out: Record<string, unknown> = {};
	for (const [key, prop] of Object.entries(s.properties ?? {})) {
		const r = resolve(prop, root);
		if (r.schema.default !== undefined) out[key] = structuredClone(r.schema.default);
		else if (r.schema.const !== undefined) out[key] = r.schema.const;
		else if (fieldKind(prop, root) === 'object') out[key] = defaults(prop, root);
		else if (r.schema.type === 'array') out[key] = [];
		else if (r.schema.type === 'boolean') out[key] = false;
	}
	return out;
}

/** Une un valor guardado con los defaults (claves nuevas del esquema). */
export function withDefaults(
	schema: JsonSchema,
	value: Record<string, unknown> | null | undefined,
	root: JsonSchema = schema
): Record<string, unknown> {
	const base = defaults(schema, root);
	const out: Record<string, unknown> = { ...base, ...(value ?? {}) };
	const { schema: s } = resolve(schema, root);
	for (const [key, prop] of Object.entries(s.properties ?? {})) {
		if (fieldKind(prop, root) === 'object' && out[key] && typeof out[key] === 'object') {
			out[key] = withDefaults(prop, out[key] as Record<string, unknown>, root);
		}
	}
	return out;
}

function isEmpty(v: unknown): boolean {
	return v === undefined || v === null || (typeof v === 'string' && v.trim() === '');
}

/** Valida y devuelve errores por ruta (`scope.nodes`, `fields.0.path`). */
export function validate(
	schema: JsonSchema,
	value: unknown,
	root: JsonSchema = schema,
	path = '',
	opts: { secretsSet?: (path: string) => boolean } = {}
): Record<string, string> {
	const errors: Record<string, string> = {};
	const { schema: s, nullable } = resolve(schema, root);
	const put = (msg: string) => {
		if (!errors[path]) errors[path] = msg;
	};

	if (isEmpty(value)) return errors; // obligatorio se revisa desde el objeto padre

	if (s.enum && !s.enum.some((e) => e === value)) put(m.adm_field_invalid());
	if (s.const !== undefined && value !== s.const) put(m.adm_field_invalid());

	switch (s.type) {
		case 'integer':
		case 'number': {
			const n = typeof value === 'number' ? value : Number(value);
			if (!Number.isFinite(n) || (s.type === 'integer' && !Number.isInteger(n))) {
				put(m.adm_field_invalid());
				break;
			}
			if (s.minimum !== undefined && n < s.minimum) put(m.adm_min_value({ min: s.minimum }));
			if (s.exclusiveMinimum !== undefined && n <= s.exclusiveMinimum)
				put(m.adm_min_value({ min: s.exclusiveMinimum }));
			if (s.maximum !== undefined && n > s.maximum) put(m.adm_max_value({ max: s.maximum }));
			if (s.exclusiveMaximum !== undefined && n >= s.exclusiveMaximum)
				put(m.adm_max_value({ max: s.exclusiveMaximum }));
			break;
		}
		case 'string': {
			if (typeof value !== 'string') {
				put(m.adm_field_invalid());
				break;
			}
			if (s.minLength !== undefined && value.length < s.minLength)
				put(m.adm_min_length({ min: s.minLength }));
			if (s.maxLength !== undefined && value.length > s.maxLength)
				put(m.adm_max_length({ max: s.maxLength }));
			if (s.pattern && !safeRegex(s.pattern)?.test(value)) put(m.adm_pattern());
			break;
		}
		case 'array': {
			if (!Array.isArray(value)) {
				put(m.adm_field_invalid());
				break;
			}
			if (s.minItems !== undefined && value.length < s.minItems)
				put(m.adm_min_value({ min: s.minItems }));
			if (s.maxItems !== undefined && value.length > s.maxItems)
				put(m.adm_max_value({ max: s.maxItems }));
			if (s.items) {
				value.forEach((item, i) => {
					Object.assign(errors, validate(s.items as JsonSchema, item, root, join(path, i), opts));
				});
			}
			break;
		}
		case 'object': {
			if (typeof value !== 'object' || Array.isArray(value)) {
				put(m.adm_field_invalid());
				break;
			}
			const obj = value as Record<string, unknown>;
			for (const key of s.required ?? []) {
				const p = join(path, key);
				const prop = s.properties?.[key];
				const secret = prop && fieldKind(prop, root) === 'secret';
				if (isEmpty(obj[key]) && !(secret && opts.secretsSet?.(p))) errors[p] = m.adm_required();
			}
			for (const [key, prop] of Object.entries(s.properties ?? {})) {
				Object.assign(errors, validate(prop, obj[key], root, join(path, key), opts));
			}
			break;
		}
	}
	void nullable;
	return errors;
}

function join(path: string, key: string | number): string {
	return path ? `${path}.${key}` : String(key);
}

function safeRegex(pattern: string): RegExp | null {
	try {
		return new RegExp(pattern);
	} catch {
		return null;
	}
}

/**
 * Valor para enviar: quita opcionales vacíos (así rige el default del servidor), deja `null`
 * donde el esquema lo admite y omite secretos sin escribir (sin cambios).
 */
export function clean(
	schema: JsonSchema,
	value: Record<string, unknown>,
	root: JsonSchema = schema
): Record<string, unknown> {
	const { schema: s } = resolve(schema, root);
	const out: Record<string, unknown> = {};
	const required = new Set(s.required ?? []);
	for (const [key, prop] of Object.entries(s.properties ?? {})) {
		const v = value[key];
		const r = resolve(prop, root);
		const kind = fieldKind(prop, root);
		if (kind === 'secret' && isEmpty(v)) continue;
		if (isEmpty(v)) {
			if (r.nullable && v === null) out[key] = null;
			else if (required.has(key)) out[key] = v ?? null;
			continue;
		}
		if (kind === 'object' && typeof v === 'object' && !Array.isArray(v)) {
			out[key] = clean(prop, v as Record<string, unknown>, root);
		} else if (kind === 'object-list' && Array.isArray(v) && r.schema.items) {
			out[key] = v.map((item) =>
				item && typeof item === 'object'
					? clean(r.schema.items as JsonSchema, item as Record<string, unknown>, root)
					: item
			);
		} else {
			out[key] = v;
		}
	}
	// Claves que no están en el esquema (si el esquema las admite) se conservan.
	if (s.additionalProperties !== false) {
		for (const [key, v] of Object.entries(value))
			if (!(key in out) && !(key in (s.properties ?? {}))) out[key] = v;
	}
	return out;
}

/** Título legible de un campo: el del esquema o la clave con espacios. */
export function titleOf(key: string, schema: JsonSchema, root: JsonSchema): string {
	const { schema: s } = resolve(schema, root);
	if (s.title) return s.title;
	const t = key.replace(/_/g, ' ');
	return t.charAt(0).toUpperCase() + t.slice(1);
}
