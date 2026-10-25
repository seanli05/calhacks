import type { LandingStrings } from "../en/landing";

export const landing: LandingStrings = {
  headline: ["¡Hola! Soy Avocado.", "Sus documentos, más fáciles."],
  sub: "Empezar una nueva vida en otro país, con todos sus formularios, es difícil. Con Avocado puede escribir por WhatsApp en su idioma, enviar los formularios que no entiende y pedirnos que llamemos a los representantes por usted. ¡Todo en su propio idioma!",
  tryIt: "Pruébelo en WhatsApp",
  watch: "Ver un ejemplo",
  scan: "¿Está en una computadora? Escanee esto con su teléfono.",
  thenSend: "El mensaje ya está escrito. Solo presione enviar:",
  perks: ["Sin apps nuevas: es por WhatsApp", "Español · English · دری", "Nada pasa sin su permiso"],
  loading: "Preparando…",

  chat: {
    name: "Avocado",
    status: "Responde en un minuto",
    user: "¿Me ayuda con esta carta?",
    explain: "Es su aviso de entrevista de asilo. Es el jueves 12 de noviembre a las 9:00 a. m. Lleve su pasaporte y un intérprete.",
    real: "Esta carta es real. La revisamos en uscis.gov.",
    ask: "¿Quiere que llamemos a USCIS por usted? Esperamos en la línea y le llamamos cuando conteste una persona.",
    yes: "Sí, por favor",
    calling: "Perfecto. Estamos llamando a USCIS. Le llamamos cuando conteste una persona.",
    typing: "escribiendo",
  },

  steps: {
    says: ["¡Recibido! Déjeme verla.", "Es real. Esto es lo que significa.", "Le llamo cuando conteste alguien."],
    sub: "Tres pasos. Usted solo hace el primero.",
    title: "Cómo funciona",
    items: [
      { title: "Envíe una foto", body: "Tómele una foto a la carta y mándenosla por WhatsApp." },
      { title: "La explicamos y revisamos", body: "Qué dice, la fecha, qué llevar y si es real." },
      { title: "Llamamos por usted", body: "Si dice que sí, esperamos en la línea y le llamamos cuando conteste una persona." },
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
    title: "Nuestra promesa para usted",
    greeting: "Hola,",
    sub: "Usted siempre decide. Avocado cumple estas promesas en cada carta y cada llamada.",
    signoff: "Con cariño,",
    items: [
      { title: "Solo marcamos números oficiales", body: "El número que llamamos siempre viene del sitio web de la oficina, nunca de la carta." },
      { title: "Usted habla por sí mismo", body: "Nunca decimos su A-Number, número de recibo ni fecha de nacimiento. Eso lo contesta usted." },
      { title: "Preguntamos antes de cada llamada", body: "No pasa nada hasta que usted dice que sí." },
      { title: "Borre lo que quiera", body: "Vea lo que recordamos de usted y quite una cosa o todo." },
    ],
  },

  example: {
    back: "Volver al inicio",
    title: "Vea cómo ayuda Avocado",
    sub: "Una carta, de la foto a la llamada. Se reproduce sola.",
    pause: "Pausa",
    play: "Reproducir",
    prev: "Anterior",
    next: "Siguiente",
    step: (n: number, total: number) => `Paso ${n} de ${total}`,
    alt: "La página de Avocado para esta carta",
    done: "¿Listo para probarlo con su propia carta?",
    slides: [
      { title: "Su carta, explicada", body: "Avocado lee la carta, se la explica en su idioma y revisa en el sitio oficial que sea real. Luego le pregunta si quiere que llame." },
      { title: "Usted dice que sí y Avocado llama", body: "Con su permiso, Avocado llama al número oficial y pasa el menú telefónico por usted." },
      { title: "Avocado espera en la línea", body: "No tiene que esperar junto al teléfono. Puede ver lo que pasa en vivo." },
      { title: "Su teléfono suena", body: "Cuando contesta una persona, Avocado le llama para que se una y traduce lo que dice, en vivo." },
      { title: "Recibe un resumen", body: "Después de la llamada, recibe lo que se dijo y sus próximos pasos, en su idioma." },
    ],
  },

  closing: {
    title: ["¿Le llegó una carta?", "Envíenos una foto."],
    sub: "Solo necesita una foto. En español, inglés o dari.",
  },
};
