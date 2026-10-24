import type { LandingStrings } from "../en/landing";

export const landing: LandingStrings = {
  headline: ["Tu carta, explicada.", "Tu llamada, hecha."],
  sub: "Leemos cartas de inmigración en tu idioma, verificamos que son reales y esperamos en la línea con la agencia por ti.",
  tryIt: "Pruébalo en WhatsApp",
  watch: "Ver una llamada en vivo",
  scan: "O escanea con tu teléfono",
  thenSend: "El mensaje ya está escrito. Solo presiona enviar:",

  demo: {
    live: "Llamada en curso",
    agency: "USCIS",
    onHold: "en espera",
    dialing: "Llamando a USCIS",
    menu: "Pasando el menú telefónico",
    hold: "Estamos en espera con USCIS",
    human: "Contestó una persona",
    humanSub: "Te estamos llamando para que te unas.",
    feed: {
      verified: "Confirmamos el número oficial en uscis.gov",
      dialing: "Llamamos a USCIS",
      menu: "Elegimos la opción 2 del menú",
      hold: "Estamos en espera. Tú no tienes que esperar.",
      human: "Contestó una persona. Te estamos llamando.",
    },
    ago: (min: number) => (min === 0 ? "ahora" : `hace ${min} min`),
  },

  features: {
    explain: {
      kicker: "1 · Envía una foto",
      title: "Cada carta, en palabras que conoces.",
      body: "Envía una foto de tu carta por WhatsApp. Te decimos qué es, qué tienes que hacer y para cuándo, en tu idioma.",
      docType: "Aviso de entrevista de asilo",
      bubble: "Es tu entrevista de asilo. Es el jueves 12 de noviembre a las 9:00 a. m. Lleva tu pasaporte y un intérprete.",
    },
    verify: {
      kicker: "2 · Verificamos que es real",
      title: "Las estafas copian cartas reales. Nosotros verificamos.",
      body: "Comparamos la carta con fuentes oficiales. Cuando llamamos, usamos el número del sitio web de la agencia, nunca el que aparece en la carta.",
      real: "Esta carta es real",
      official: "Número oficial, de uscis.gov",
      officialNote: "Llamamos a este",
      printed: "Número impreso en la carta",
      printedNote: "Nunca lo marcamos",
    },
    hold: {
      kicker: "3 · Esperamos en la línea",
      title: "Horas en espera. No las tuyas.",
      body: "Llamamos a la agencia, pasamos el menú y esperamos. Cuando contesta una persona real, suena tu teléfono y te unes a la llamada.",
      waited: "Esperamos",
      answered: "Contestó una persona",
      ringing: "Tu teléfono está sonando",
    },
  },

  promises: {
    title: "Lo que nunca haremos.",
    items: [
      { title: "Llamar a un número de tu carta", body: "Solo al número oficial del sitio de la agencia." },
      { title: "Hablar por ti", body: "Cuando pregunten quién eres, contestas tú. No nosotros." },
      { title: "Llamar sin tu permiso", body: "Te preguntamos antes, cada vez, y guardamos tu respuesta." },
      { title: "Guardar lo que quieres borrar", body: "Mira todo lo que sabemos de ti. Bórralo con un toque." },
    ],
  },

  closing: {
    title: ["¿Te llegó una carta?", "Envíanos una foto."],
    sub: "Solo necesitas una foto. Español e inglés por ahora.",
  },
};
