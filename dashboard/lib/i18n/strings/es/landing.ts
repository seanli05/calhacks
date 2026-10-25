import type { LandingStrings } from "../en/landing";

export const landing: LandingStrings = {
  headline: ["Su carta, explicada.", "Su llamada, hecha."],
  sub: "Leemos cartas de inmigración en su idioma, verificamos que son reales y esperamos en la línea con la agencia por usted.",
  tryIt: "Pruébelo en WhatsApp",
  watch: "Ver una llamada en vivo",
  scan: "O escanee con su teléfono",
  thenSend: "El mensaje ya está escrito. Solo presione enviar:",

  demo: {
    live: "Llamada en curso",
    agency: "USCIS",
    onHold: "en espera",
    dialing: "Llamando a USCIS",
    menu: "Pasando el menú telefónico",
    hold: "Estamos en espera con USCIS",
    human: "Contestó una persona",
    humanSub: "Le estamos llamando para que se una.",
    feed: {
      verified: "Confirmamos el número oficial en uscis.gov",
      dialing: "Llamamos a USCIS",
      menu: "Elegimos la opción 2 del menú",
      hold: "Estamos en espera. Usted no tiene que esperar.",
      human: "Contestó una persona. Le estamos llamando.",
    },
    ago: (min: number) => (min === 0 ? "ahora" : `hace ${min} min`),
  },

  ticker: {
    label: "En cada llamada",
    items: [
      { k: "Número marcado", v: "verificado en uscis.gov" },
      { k: "Menú telefónico", v: "lo pasamos nosotros" },
      { k: "Tiempo en espera", v: "nuestro, no suyo" },
      { k: "Su permiso", v: "lo pedimos siempre" },
      { k: "Su A-Number", v: "nunca lo decimos" },
      { k: "Idiomas", v: "Español · English · دری" },
    ],
  },

  bento: {
    title: ["Todo lo que una carta le pide.", "Resuelto por WhatsApp."],
    explain: {
      lead: "Su carta, explicada",
      rest: " en su idioma: la fecha, el lugar y qué llevar.",
      docType: "Aviso de entrevista de asilo",
      bubble: "Es su entrevista de asilo: jueves 12 de noviembre a las 9:00 a. m. Lleve su pasaporte y un intérprete.",
      ask: "¿Quiere que llamemos a USCIS por usted?",
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
        "Sin ofertas de “notarios”",
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
      rest: " Usted sigue con su día.",
      onHold: "en espera",
    },
    ring: {
      lead: "Su teléfono suena",
      rest: " en cuanto contesta una persona.",
      answered: "Contestó una persona",
      calling: "Le estamos llamando",
      cta: "Ver una llamada en vivo",
    },
    prep: {
      lead: "Listo para la entrevista.",
      rest: " Palabras clave en inglés y qué llevar.",
      days: "días para su entrevista",
      words: [
        { term: "interpreter", meaning: "intérprete" },
        { term: "receipt notice", meaning: "aviso de recibo" },
      ],
      checklist: ["Lleve su pasaporte", "Lleve un intérprete", "Su cónyuge e hijos deben venir"],
    },
    memory: {
      lead: "Sus datos, su decisión.",
      rest: " Vea lo que se guarda. Quite lo que quiera.",
      facts: ["Prefiere español", "Tiene dos hijos", "Entrevista el 12 de nov.", "Necesita intérprete", "Pidió llamadas después de las 5 p. m."],
      deleteAll: "Borrar mi perfil",
      delete: "Quitar",
      deleted: "(quitado)",
      cta: "Ver su perfil",
    },
  },

  promises: {
    title: "Lo que nunca haremos.",
    sub: "Son reglas en nuestro código, no ajustes.",
    items: [
      { title: "Marcar un número sin verificar", body: "Solo el número oficial, del sitio de la propia agencia." },
      { title: "Hablar por usted", body: "Nunca decimos su A-Number, número de recibo ni fecha de nacimiento. Usted contesta." },
      { title: "Llamar sin su permiso", body: "Le preguntamos antes de cada llamada y guardamos su respuesta." },
      { title: "Guardar lo que usted borra", body: "Borre lo que quiera, o todo, cuando quiera." },
    ],
  },

  closing: {
    title: ["¿Le llegó una carta?", "Envíenos una foto."],
    sub: "Solo necesita una foto. Español, inglés y dari por ahora.",
  },
};
