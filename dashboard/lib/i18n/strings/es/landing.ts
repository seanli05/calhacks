import type { LandingStrings } from "../en/landing";

export const landing: LandingStrings = {
  headline: ["¡Hola! Soy Avocado.", "Tus documentos, más fáciles."],
  sub: "Empezar una nueva vida en otro país, con todos sus formularios, es difícil. Con Avocado puedes escribir por WhatsApp en tu idioma, enviar los formularios que no entiendes y hacer que llamemos a los representantes por ti. ¡Todo en tu propio idioma!",
  tryIt: "Pruébalo en WhatsApp",
  watch: "Ver un ejemplo",
  scan: "¿Estás en una computadora? Escanea esto con tu teléfono.",
  thenSend: "El mensaje ya está escrito. Solo presiona enviar:",
  perks: ["Sin apps nuevas: es por WhatsApp", "Español · English · دری", "Nada pasa sin tu permiso"],
  loading: "Preparando…",

  chat: {
    name: "Avocado",
    status: "Responde en un minuto",
    user: "¿Me ayudas con esta carta?",
    explain: "Es tu aviso de entrevista de asilo. Es el jueves 12 de noviembre a las 9:00 a. m. Lleva tu pasaporte y un intérprete.",
    real: "Esta carta es real. La revisamos en uscis.gov.",
    ask: "¿Quieres que llamemos a USCIS por ti? Esperamos en la línea y te llamamos cuando conteste una persona.",
    yes: "Sí, por favor",
    calling: "Perfecto. Estamos llamando a USCIS. Te llamamos cuando conteste una persona.",
    typing: "escribiendo",
  },

  steps: {
    says: ["¡Recibido! Déjame verla.", "Es real. Esto es lo que significa.", "Te llamo cuando conteste alguien."],
    sub: "Tres pasos. Tú solo haces el primero.",
    title: "Cómo funciona",
    items: [
      { title: "Envía una foto", body: "Tómale una foto a la carta y mándanosla por WhatsApp." },
      { title: "La explicamos y revisamos", body: "Qué dice, la fecha, qué llevar y si es real." },
      { title: "Llamamos por ti", body: "Si dices que sí, esperamos en la línea y te llamamos cuando conteste una persona." },
    ],
  },

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
      { k: "Idiomas", v: "Español · English · دری" },
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
      rest: " Mira lo que se guarda. Quita lo que quieras.",
      facts: ["Prefiere español", "Tiene dos hijos", "Entrevista el 12 de nov.", "Necesita intérprete", "Pidió llamadas después de las 5 p. m."],
      deleteAll: "Borrar mi perfil",
      delete: "Quitar",
      deleted: "(quitado)",
      cta: "Ver tu perfil",
    },
  },

  promises: {
    title: "Nuestra promesa para ti",
    greeting: "Hola,",
    sub: "Tú siempre decides. Avocado cumple estas promesas en cada carta y cada llamada.",
    signoff: "Con cariño,",
    items: [
      { title: "Solo marcamos números oficiales", body: "El número que llamamos siempre viene del sitio web de la oficina, nunca de la carta." },
      { title: "Tú hablas por ti", body: "Nunca decimos tu A-Number, número de recibo ni fecha de nacimiento. Eso lo contestas tú." },
      { title: "Preguntamos antes de cada llamada", body: "No pasa nada hasta que dices que sí." },
      { title: "Borra lo que quieras", body: "Mira lo que recordamos de ti y quita una cosa o todo." },
    ],
  },

  example: {
    back: "Volver al inicio",
    title: "Mira cómo ayuda Avocado",
    sub: "Una carta, de la foto a la llamada. Se reproduce sola.",
    pause: "Pausa",
    play: "Reproducir",
    prev: "Anterior",
    next: "Siguiente",
    step: (n: number, total: number) => `Paso ${n} de ${total}`,
    alt: "La página de Avocado para esta carta",
    done: "¿Listo para probarlo con tu propia carta?",
    slides: [
      { title: "Tu carta, explicada", body: "Avocado lee la carta, te la explica en tu idioma y revisa en el sitio oficial que sea real. Luego te pregunta si quieres que llame." },
      { title: "Dices que sí y Avocado llama", body: "Con tu permiso, Avocado llama al número oficial y pasa el menú telefónico por ti." },
      { title: "Avocado espera en la línea", body: "No tienes que esperar junto al teléfono. Puedes ver lo que pasa en vivo." },
      { title: "Tu teléfono suena", body: "Cuando contesta una persona, Avocado te llama para que te unas y traduce lo que dice, en vivo." },
      { title: "Recibes un resumen", body: "Después de la llamada, recibes lo que se dijo y tus próximos pasos, en tu idioma." },
    ],
  },

  closing: {
    title: ["¿Te llegó una carta?", "Envíanos una foto."],
    sub: "Solo necesitas una foto. En español, inglés o dari.",
  },
};
