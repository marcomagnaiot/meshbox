// Ficha «Cómo conectarse»: textos derivados de los datos de radio que publica el sitio.
import type { JoinInfo } from '$lib/api/types';

/** Frecuencia en MHz con la coma o el punto del idioma (926,125). */
export function formatMhz(mhz: number, locale: string): string {
	return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(mhz);
}

/** Línea corta para la barra: «ANZ · MediumFast · 926,125 MHz». */
export function joinSummary(j: JoinInfo, locale: string): string {
	const parts = [j.region, j.preset_name];
	if (j.frequency_mhz) parts.push(`${formatMhz(j.frequency_mhz, locale)} MHz`);
	else if (j.slot) parts.push(`slot ${j.slot}`);
	return parts.filter(Boolean).join(' · ');
}

/** Enlace para llamar o escribir si el contacto trae un teléfono (8 dígitos o más). */
export function phoneHref(contact: string): string | null {
	const m = contact.match(/\+?[\d\s().-]{8,}/);
	if (!m) return null;
	const digits = m[0].replace(/[^\d+]/g, '');
	return digits.replace(/\D/g, '').length >= 8 ? `tel:${digits}` : null;
}
