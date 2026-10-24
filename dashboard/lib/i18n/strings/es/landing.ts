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

  ticker: {
    label: "En cada llamada",
    items: [
      { k: "Número marcado", v: "verificado en uscis.gov" },
      { k: "Menú telefónico", v: "lo pasamos nosotros" },
      { k: "Tiempo en espera", v: "nuestro, no tuyo" },
      { k: "Tu permiso", v: "lo pedimos siempre" },
      { k: "Tu A-Number", v: "nunca lo decimos" },
      { k: "Idiomas", v: "Español · English" },
    ],
  },

  bento: {
    title: ["Todo lo que una carta te pide.", "Resuelto por WhatsApp."],
    explain: {
      lead: "Tu carta, explicada",
      rest: " en tu idioma: la fecha, el lugar y qué llevar.",
      docType: "Aviso de entrevista de asilo",
      bubble: "Es tu entrevista de asilo: jueves 12 de noviembre a las 9:00 a. m. Lleva tu pasaporte y un intérprete.",
      ask: "¿Quieres que llamemos a USCIS por ti?",
      yes: "Sí, por favor",
    },
    verify: {
      lead: "Verificada con USCIS",
      rest: " antes de creer una sola línea.",
      verdict: "Esta carta es real",
      checks: [
        "Formulario I-797C, edición vigente",
        "Todos los enlaces son de uscis.gov",
        "El número de recibo tiene el formato correcto",
        "No pide pagos ni tarjetas de regalo",
        "Sin amenazas de arresto o deportación",
        "Sin ofertas de \"notarios\"",
      ],
      official: "Número oficial encontrado en uscis.gov",
    },
    menu: {
      lead: "Menús telefónicos,",
      rest: " resueltos. Marcamos las opciones correctas.",
      prompt: "“Para hablar con un representante, oprima 2.”",
      options: [
        { key: "1", text: "Estado del caso" },
        { key: "2", text: "Hablar con un representante" },
        { key: "3", text: "Cambio de dirección" },
      ],
      chosen: 1,
    },
    hold: {
      lead: "Esperamos en la línea.",
      rest: " Tú sigues con tu día.",
      onHold: "en espera",
    },
    ring: {
      lead: "Tu teléfono suena",
      rest: " en cuanto contesta una persona.",
      answered: "Contestó una persona",
      calling: "Te estamos llamando",
      cta: "Ver una llamada en vivo",
    },
    prep: {
      lead: "Listo para la entrevista.",
      rest: " Palabras clave en inglés y qué llevar.",
      days: "días para tu entrevista",
      words: [
        { term: "interpreter", meaning: "intérprete" },
        { term: "receipt notice", meaning: "aviso de recibo" },
      ],
      checklist: ["Lleva tu pasaporte", "Lleva un intérprete", "Tu cónyuge e hijos deben venir"],
    },
    memory: {
      lead: "Tus datos, tu decisión.",
      rest: " Mira lo que sabemos. Borra lo que quieras.",
      facts: ["Prefiere español", "Tiene dos hijos", "Entrevista el 12 de nov.", "Necesita intérprete", "Pidió llamadas después de las 5 p. m."],
      deleteAll: "Borrar todo",
      delete: "Borrar",
      deleted: "(borrado)",
      cta: "Lo que sabemos de ti",
    },
  },

  promises: {
    title: "Lo que nunca haremos.",
    sub: "Son reglas en nuestro código, no ajustes.",
    items: [
      { title: "Marcar un número sin verificar", body: "Solo el número oficial, del sitio de la propia agencia." },
      { title: "Hablar por ti", body: "Nunca decimos tu A-Number, número de recibo ni fecha de nacimiento. Contestas tú." },
      { title: "Llamar sin tu permiso", body: "Te preguntamos antes de cada llamada y guardamos tu respuesta." },
      { title: "Guardar lo que borras", body: "Borra lo que quieras, o todo, cuando quieras." },
    ],
  },

  closing: {
    title: ["¿Te llegó una carta?", "Envíanos una foto."],
    sub: "Solo necesitas una foto. Español e inglés por ahora.",
  },
};
