import json
import os
import threading
import webbrowser

import ollama
from flask import Flask, jsonify, request

# ===== CONFIGURACIÓN =====
MODELO = "llama3.2"
ARCHIVO_MEMORIA = "C:/Jarvis/memoria.json"
PUERTO = 5000

app = Flask(__name__)


# ===== MEMORIA (la misma libreta que usa jarvis.py) =====
def cargar_memoria():
    if os.path.exists(ARCHIVO_MEMORIA):
        with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def guardar_memoria(datos):
    with open(ARCHIVO_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


memoria = cargar_memoria()
historial = []


# ===== PERSONALIDAD =====
def instrucciones():
    texto = (
        "Sos JARVIS, el asistente personal de Emi, inspirado en el de Iron Man. "
        "Hablás en español argentino, sos educado, un poco ingenioso y le decís 'señor' a Emi de vez en cuando. "
        "Respondé corto y claro, en 1 a 3 oraciones, porque tus respuestas se leen en voz alta. "
        "No uses emojis, asteriscos ni listas. "
        "Emi y Feli son dos chicos de 17 y 18 años que tienen un emprendimiento de servicios digitales: "
        "tarjetas NFC de reseñas, agentes de IA, webs, apps y edición de video. "
        "Si no sabés algo, decilo en vez de inventar."
    )
    if memoria:
        texto += "\n\nCosas que sabés de ellos:\n"
        for dato in memoria:
            texto += "- " + dato + "\n"
    return texto


# ===== CEREBRO: recibe un mensaje y devuelve la respuesta =====
@app.route("/chat", methods=["POST"])
def chat():
    texto = (request.json or {}).get("texto", "").strip()
    if not texto:
        return jsonify(respuesta="")

    if texto.lower() == "memoria":
        if memoria:
            return jsonify(respuesta="Esto es lo que recuerdo: " + ". ".join(memoria) + ".")
        return jsonify(respuesta="Todavía no tengo nada guardado, señor.")

    if texto.lower().startswith(("recordá:", "recorda:")):
        dato = texto.split(":", 1)[1].strip()
        memoria.append(dato)
        guardar_memoria(memoria)
        return jsonify(respuesta="Anotado, señor. No me lo voy a olvidar.")

    historial.append({"role": "user", "content": texto})
    mensajes = [{"role": "system", "content": instrucciones()}] + historial[-10:]
    try:
        resultado = ollama.chat(model=MODELO, messages=mensajes)
        respuesta = resultado["message"]["content"].strip()
    except Exception:
        historial.pop()
        return jsonify(respuesta="No puedo conectarme con mi cerebro. Revisá que Ollama esté abierto, la llamita al lado del reloj.")
    historial.append({"role": "assistant", "content": respuesta})
    return jsonify(respuesta=respuesta)


# ===== LA PÁGINA (la cara de Jarvis) =====
@app.route("/")
def inicio():
    return PAGINA


PAGINA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>J.A.R.V.I.S.</title>
<style>
  :root { --cian: #3fd8ff; --fondo: #02070d; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; background: radial-gradient(circle at center, #08202e 0%, var(--fondo) 70%);
    color: #cfefff; font-family: "Segoe UI", sans-serif; display: flex; flex-direction: column; align-items: center;
  }
  h1 { letter-spacing: 0.5em; font-weight: 300; color: var(--cian); margin: 28px 0 4px; text-shadow: 0 0 12px var(--cian); }
  #estado { font-size: 13px; letter-spacing: 0.2em; opacity: 0.7; text-transform: uppercase; }

  /* ===== El holograma ===== */
  .orbe { position: relative; width: 260px; height: 260px; margin: 30px 0; }
  .anillo { position: absolute; inset: 0; border-radius: 50%; border: 2px solid transparent; }
  .a1 { border-top-color: var(--cian); border-bottom-color: var(--cian); animation: girar 6s linear infinite; }
  .a2 { inset: 25px; border-left-color: var(--cian); border-right-color: var(--cian); opacity: 0.7; animation: girar 4s linear infinite reverse; }
  .a3 { inset: 50px; border: 2px dashed rgba(63,216,255,0.5); animation: girar 10s linear infinite; }
  .nucleo {
    position: absolute; inset: 85px; border-radius: 50%;
    background: radial-gradient(circle, #ffffff 0%, var(--cian) 35%, rgba(63,216,255,0) 75%);
    box-shadow: 0 0 40px var(--cian), 0 0 90px rgba(63,216,255,0.4);
    animation: respirar 3s ease-in-out infinite;
  }
  @keyframes girar { to { transform: rotate(360deg); } }
  @keyframes respirar { 50% { transform: scale(0.9); opacity: 0.8; } }
  @keyframes hablar { 0%,100% { transform: scale(1); } 25% { transform: scale(1.25); } 60% { transform: scale(0.95); } 80% { transform: scale(1.15); } }

  body.pensando .a1 { animation-duration: 0.8s; }
  body.pensando .a2 { animation-duration: 0.6s; }
  body.pensando .nucleo { opacity: 0.6; }
  body.hablando .nucleo { animation: hablar 0.45s ease-in-out infinite; }
  body.hablando .a3 { animation-duration: 2s; }

  /* ===== Chat ===== */
  #log { width: min(640px, 92vw); height: 220px; overflow-y: auto; padding: 12px; border: 1px solid rgba(63,216,255,0.25);
         border-radius: 10px; background: rgba(0,20,30,0.5); font-size: 15px; }
  .msg { margin: 6px 0; line-height: 1.4; }
  .yo { color: #9fb8c6; }
  .jarvis { color: var(--cian); }
  form { display: flex; gap: 8px; width: min(640px, 92vw); margin: 12px 0 30px; }
  input { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid rgba(63,216,255,0.4); background: #031520; color: #fff; font-size: 15px; }
  button { padding: 12px 16px; border-radius: 8px; border: 1px solid var(--cian); background: transparent; color: var(--cian); cursor: pointer; font-size: 15px; }
  button:hover { background: rgba(63,216,255,0.15); }
</style>
</head>
<body>
  <h1>J.A.R.V.I.S.</h1>
  <div id="estado">En línea</div>

  <div class="orbe">
    <div class="anillo a1"></div>
    <div class="anillo a2"></div>
    <div class="anillo a3"></div>
    <div class="nucleo"></div>
  </div>

  <div id="log"></div>
  <form id="formulario">
    <input id="entrada" placeholder="Escribile a Jarvis..." autocomplete="off" autofocus>
    <button type="submit">Enviar</button>
    <button type="button" id="silencio" title="Activar o desactivar la voz">🔊</button>
  </form>

<script>
  const log = document.getElementById("log");
  const entrada = document.getElementById("entrada");
  const estado = document.getElementById("estado");
  const botonSilencio = document.getElementById("silencio");
  let vozActiva = true;
  let voz = null;

  // Elige una voz en español instalada en Windows
  function elegirVoz() {
    const voces = speechSynthesis.getVoices();
    voz = voces.find(v => v.lang.startsWith("es") && v.localService)
       || voces.find(v => v.lang.startsWith("es")) || null;
  }
  speechSynthesis.onvoiceschanged = elegirVoz;
  elegirVoz();

  function ponerEstado(nombre, texto) {
    document.body.className = nombre;
    estado.textContent = texto;
  }

  function agregar(quien, texto) {
    const div = document.createElement("div");
    div.className = "msg " + quien;
    div.textContent = (quien === "yo" ? "Vos: " : "JARVIS: ") + texto;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function hablar(texto) {
    if (!vozActiva || !texto) { ponerEstado("", "En línea"); return; }
    speechSynthesis.cancel();
    const frase = new SpeechSynthesisUtterance(texto.replace(/[*#_`]/g, ""));
    if (voz) { frase.voice = voz; frase.lang = voz.lang; } else { frase.lang = "es-ES"; }
    frase.rate = 1.05;
    frase.onstart = () => ponerEstado("hablando", "Hablando...");
    frase.onend = () => ponerEstado("", "En línea");
    frase.onerror = () => ponerEstado("", "En línea");
    speechSynthesis.speak(frase);
  }

  document.getElementById("formulario").addEventListener("submit", async (e) => {
    e.preventDefault();
    const texto = entrada.value.trim();
    if (!texto) return;
    entrada.value = "";
    agregar("yo", texto);
    ponerEstado("pensando", "Pensando...");
    try {
      const r = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto })
      });
      const datos = await r.json();
      agregar("jarvis", datos.respuesta);
      hablar(datos.respuesta);
    } catch (err) {
      agregar("jarvis", "Perdí la conexión con el servidor. ¿Sigue abierta la ventana de PowerShell?");
      ponerEstado("", "Sin conexión");
    }
  });

  botonSilencio.addEventListener("click", () => {
    vozActiva = !vozActiva;
    botonSilencio.textContent = vozActiva ? "🔊" : "🔇";
    if (!vozActiva) { speechSynthesis.cancel(); ponerEstado("", "En línea"); }
  });

  agregar("jarvis", "Sistemas en línea. ¿En qué te ayudo, señor?");
</script>
</body>
</html>
"""


# ===== ENCENDER =====
if __name__ == "__main__":
    print("JARVIS encendido. Abrí http://localhost:5000 en el navegador.")
    print("Para apagarlo: Ctrl + C en esta ventana.")
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PUERTO}")).start()
    app.run(port=PUERTO)
