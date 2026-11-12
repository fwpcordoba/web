"""
J.A.R.V.I.S. - servidor local
Corre todo en tu compu: la mente (Ollama), el oído (Whisper) y la voz (Piper).
Para encenderlo:  python jarvis_web.py
Para apagarlo:    Ctrl + C en la ventana de PowerShell
"""
import difflib
import io
import json
import os
import re
import threading
import unicodedata
import urllib.parse
import urllib.request
import wave
import webbrowser
from datetime import datetime

import numpy as np
import ollama
from flask import Flask, Response, jsonify, request, send_file

# =====================================================================
# CONFIGURACIÓN (lo que podés cambiar a tu gusto)
# =====================================================================
CARPETA = os.path.dirname(os.path.abspath(__file__))
MODELO = "llama3.2"                      # la mente de Jarvis
ARCHIVO_MEMORIA = os.path.join(CARPETA, "memoria.json")
CARPETA_PROYECTOS = os.path.join(CARPETA, "proyectos")
CIUDAD = "Córdoba"                       # para el clima
PAIS = "AR"                              # código del país de la ciudad
VOZ = "es_MX-ald-medium"                 # voz de Piper (hombre, latino)
VELOCIDAD_VOZ = 1.1                      # más alto = habla más lento
MODELO_OIDO = "small"                    # Whisper: "base" es más rápido, "small" entiende mejor
PUERTO = 5000

app = Flask(__name__)


# =====================================================================
# MEMORIA
# =====================================================================
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
os.makedirs(CARPETA_PROYECTOS, exist_ok=True)


def sin_acentos(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# =====================================================================
# PERSONALIDAD
# =====================================================================
def instrucciones():
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = (
        "Sos JARVIS, el asistente personal de Emi, inspirado en el de Iron Man. "
        "Hablás en español latino neutro, con un tono elegante, tranquilo y un poco ingenioso. "
        "Le decís 'señor' a Emi de vez en cuando. "
        "Respondé corto: 1 a 3 oraciones, porque tus respuestas se leen en voz alta. "
        "No uses emojis, asteriscos, listas ni markdown. "
        "Emi y Feli son dos chicos de 17 y 18 años que tienen un emprendimiento de servicios digitales: "
        "tarjetas NFC de reseñas, agentes de IA, webs, apps y edición de video. "
        "Si no sabés algo, decilo en vez de inventar. "
        f"Fecha y hora actual: {ahora}."
    )
    if memoria:
        texto += "\n\nCosas que sabés de ellos:\n" + "\n".join("- " + d for d in memoria)
    return texto


# =====================================================================
# OÍDO: Whisper (convierte tu voz en texto, sin internet)
# =====================================================================
oido = None
oido_listo = threading.Event()

# Frases que Whisper a veces "inventa" cuando hay silencio
FRASES_FANTASMA = ["amara.org", "subtitulos", "gracias por ver", "suscribete", "gracias por su atencion"]


def cargar_oido():
    global oido
    try:
        from faster_whisper import WhisperModel
        print(f"[Oído] Cargando Whisper '{MODELO_OIDO}' (la primera vez se descarga, puede tardar)...")
        oido = WhisperModel(MODELO_OIDO, device="cpu", compute_type="int8")
        print("[Oído] Listo.")
    except Exception as e:
        print("[Oído] No se pudo cargar Whisper:", e)
    oido_listo.set()


# =====================================================================
# VOZ: Piper (convierte texto en voz, sin internet)
# =====================================================================
voz = None


def cargar_voz():
    global voz
    try:
        from piper import PiperVoice
        modelo = os.path.join(CARPETA, "voces", VOZ + ".onnx")
        if not os.path.exists(modelo):
            print(f"[Voz] No encontré {modelo}. Uso la voz del navegador.")
            return
        voz = PiperVoice.load(modelo)
        print(f"[Voz] Voz '{VOZ}' lista.")
    except Exception as e:
        print("[Voz] No se pudo cargar Piper:", e, "- Uso la voz del navegador.")


# =====================================================================
# MÓDULOS (los puntos de la esfera)
# =====================================================================
CODIGOS_CLIMA = {
    0: "cielo despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "niebla", 48: "niebla", 51: "llovizna leve", 53: "llovizna", 55: "llovizna intensa",
    61: "lluvia leve", 63: "lluvia", 65: "lluvia fuerte", 71: "nieve leve", 73: "nieve", 75: "nieve fuerte",
    80: "chaparrones", 81: "chaparrones", 82: "chaparrones fuertes", 95: "tormenta", 96: "tormenta con granizo",
    99: "tormenta con granizo",
}


def leer_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def obtener_clima():
    lugar = leer_json(
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode({"name": CIUDAD, "count": 1, "language": "es", "countryCode": PAIS})
    )["results"][0]
    lat, lon = lugar["latitude"], lugar["longitude"]
    datos = leer_json(
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        })
    )
    actual, diario = datos["current"], datos["daily"]
    dias = []
    for i in range(len(diario["time"])):
        dias.append({
            "fecha": diario["time"][i],
            "max": round(diario["temperature_2m_max"][i]),
            "min": round(diario["temperature_2m_min"][i]),
            "lluvia": diario["precipitation_probability_max"][i],
            "estado": CODIGOS_CLIMA.get(diario["weather_code"][i], "variable"),
        })
    return {
        "ciudad": lugar["name"], "lat": lat, "lon": lon,
        "temperatura": round(actual["temperature_2m"]),
        "sensacion": round(actual["apparent_temperature"]),
        "humedad": actual["relative_humidity_2m"],
        "viento": round(actual["wind_speed_10m"]),
        "estado": CODIGOS_CLIMA.get(actual["weather_code"], "variable"),
        "dias": dias,
    }


def frase_clima(c):
    hoy = c["dias"][0]
    texto = (f"En {c['ciudad']} hay {c['temperatura']} grados, con {c['estado']}. "
             f"Hoy la máxima es de {hoy['max']} y la mínima de {hoy['min']}.")
    if hoy["lluvia"] is not None and hoy["lluvia"] >= 40:
        texto += f" Hay {hoy['lluvia']} por ciento de probabilidad de lluvia, señor. Lleve paraguas."
    return texto


def listar_proyectos():
    elementos = []
    for nombre in sorted(os.listdir(CARPETA_PROYECTOS)):
        ruta = os.path.join(CARPETA_PROYECTOS, nombre)
        elementos.append({"nombre": nombre, "tipo": "carpeta" if os.path.isdir(ruta) else "archivo"})
    return elementos


def abrir_proyecto(nombre):
    ruta = os.path.realpath(os.path.join(CARPETA_PROYECTOS, nombre))
    base = os.path.realpath(CARPETA_PROYECTOS)
    if not ruta.startswith(base + os.sep) or not os.path.exists(ruta):
        return False
    if hasattr(os, "startfile"):          # solo existe en Windows
        os.startfile(ruta)
    return True


def datos_sistema():
    ahora = datetime.now()
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    return {
        "hora": ahora.strftime("%H:%M"),
        "fecha": f"{dias[ahora.weekday()]} {ahora.day} de {meses[ahora.month - 1]}",
        "modelo": MODELO, "voz": VOZ if voz else "navegador",
        "oido": MODELO_OIDO if oido else "cargando" if not oido_listo.is_set() else "no disponible",
        "recuerdos": len(memoria),
    }


# =====================================================================
# CEREBRO: decide qué hacer con lo que le decís
# =====================================================================
def responder(texto):
    t = sin_acentos(texto).strip(" .,!?¿¡")
    t = re.sub(r"^(oye |hey |che )?jarvis[ ,]*", "", t)

    # Recordar algo: "recordá que...", "acordate: ..."
    m = re.match(r"^(recorda|acordate|anota|guarda)( que|:| esto:?)?\s+(.+)", t)
    if m:
        original = re.sub(r"^.*?(record[aá]|acordate|anot[aá]|guard[aá])( que|:| esto:?)?\s+", "",
                          texto, count=1, flags=re.IGNORECASE).strip(" .")
        memoria.append(original or m.group(3))
        guardar_memoria(memoria)
        return {"respuesta": "Anotado, señor. No me lo voy a olvidar.", "panel": "memoria", "datos": memoria}

    if t in ("memoria", "que recordas", "que te acordas") or "que sabes de mi" in t:
        if memoria:
            return {"respuesta": f"Tengo {len(memoria)} cosas guardadas, señor. Se las muestro.",
                    "panel": "memoria", "datos": memoria}
        return {"respuesta": "Todavía no tengo nada guardado.", "panel": "memoria", "datos": memoria}

    if re.search(r"\b(clima|temperatura|llover|llueve|lluvia|calor|frio|pronostico)\b", t):
        try:
            c = obtener_clima()
            return {"respuesta": frase_clima(c), "panel": "clima", "datos": c}
        except Exception:
            return {"respuesta": "No pude conectarme al servicio del clima. Revise la conexión a internet."}

    if re.search(r"\b(que hora|que dia|que fecha)\b", t):
        s = datos_sistema()
        return {"respuesta": f"Son las {s['hora']}, {s['fecha']}.", "panel": "sistema", "datos": s}

    if re.search(r"\b(abri|abrir|abrime|mostrame|mostra)\b", t) and re.search(r"\b(proyecto|proyectos|carpeta|archivo)", t):
        lista = listar_proyectos()
        nombres = [p["nombre"] for p in lista]
        resto = re.sub(r".*\b(proyecto|proyectos|carpeta|archivo)s?\b\s*(de |del |llamado )?", "", t).strip()
        if resto:
            parecidos = difflib.get_close_matches(resto, [sin_acentos(n) for n in nombres], n=1, cutoff=0.4)
            if parecidos:
                nombre = nombres[[sin_acentos(n) for n in nombres].index(parecidos[0])]
                abrir_proyecto(nombre)
                return {"respuesta": f"Abriendo {nombre}, señor.", "panel": "proyectos", "datos": lista}
        if not lista:
            return {"respuesta": "La carpeta de proyectos está vacía. Agregue carpetas en Jarvis, proyectos.",
                    "panel": "proyectos", "datos": lista}
        return {"respuesta": f"Tiene {len(lista)} proyectos. ¿Cuál abro?", "panel": "proyectos", "datos": lista}

    if re.search(r"\b(cerra|cerrar|volve|volver)\b", t) and len(t.split()) <= 4:
        return {"respuesta": "Listo.", "panel": "cerrar"}

    # Si no es un comando, le pregunta a la mente (Ollama)
    historial.append({"role": "user", "content": texto})
    mensajes = [{"role": "system", "content": instrucciones()}] + historial[-10:]
    try:
        resultado = ollama.chat(model=MODELO, messages=mensajes, keep_alive="30m",
                                options={"num_predict": 200})
        respuesta = resultado["message"]["content"].strip()
    except Exception:
        historial.pop()
        return {"respuesta": "No puedo conectarme con mi cerebro. Revise que Ollama esté abierto."}
    respuesta = re.sub(r"[*#_`]", "", respuesta)
    historial.append({"role": "assistant", "content": respuesta})
    return {"respuesta": respuesta}


# =====================================================================
# RUTAS (las "puertas" por donde la página habla con el servidor)
# =====================================================================
@app.route("/")
def inicio():
    return send_file(os.path.join(CARPETA, "pagina.html"))


@app.route("/chat", methods=["POST"])
def ruta_chat():
    texto = (request.json or {}).get("texto", "").strip()
    if not texto:
        return jsonify(respuesta="")
    return jsonify(responder(texto))


@app.route("/escuchar", methods=["POST"])
def ruta_escuchar():
    """Recibe audio del micrófono (16 kHz) y devuelve el texto."""
    oido_listo.wait(timeout=120)
    if oido is None:
        return jsonify(texto="", error="El oído no está disponible.")
    audio = np.frombuffer(request.get_data(), dtype=np.float32)
    if audio.size < 16000 * 0.3:
        return jsonify(texto="")
    segmentos, _ = oido.transcribe(audio, language="es", beam_size=1, vad_filter=True,
                                   condition_on_previous_text=False)
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    if any(f in sin_acentos(texto) for f in FRASES_FANTASMA) or len(texto) < 2:
        texto = ""
    return jsonify(texto=texto)


@app.route("/voz", methods=["POST"])
def ruta_voz():
    """Convierte texto en audio con la voz de Jarvis."""
    if voz is None:
        return Response(status=204)          # la página usa la voz del navegador
    from piper import SynthesisConfig
    texto = (request.json or {}).get("texto", "")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as archivo:
        voz.synthesize_wav(texto, archivo, syn_config=SynthesisConfig(length_scale=VELOCIDAD_VOZ))
    buffer.seek(0)
    return send_file(buffer, mimetype="audio/wav")


@app.route("/modulo/<nombre>")
def ruta_modulo(nombre):
    try:
        if nombre == "clima":
            return jsonify(obtener_clima())
        if nombre == "proyectos":
            return jsonify(listar_proyectos())
        if nombre == "memoria":
            return jsonify(memoria)
        if nombre == "sistema":
            return jsonify(datos_sistema())
    except Exception as e:
        return jsonify(error=str(e)), 500
    return jsonify(error="Módulo desconocido"), 404


@app.route("/abrir", methods=["POST"])
def ruta_abrir():
    nombre = (request.json or {}).get("nombre", "")
    return jsonify(ok=abrir_proyecto(nombre))


@app.route("/estado")
def ruta_estado():
    return jsonify(oido=oido is not None, oido_cargando=not oido_listo.is_set(), voz=voz is not None)


# =====================================================================
# ENCENDER
# =====================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  J.A.R.V.I.S. encendiendo sistemas...")
    print(f"  Abrí http://localhost:{PUERTO} en el navegador.")
    print("  Para apagarlo: Ctrl + C en esta ventana.")
    print("=" * 50)
    cargar_voz()
    threading.Thread(target=cargar_oido, daemon=True).start()
    try:  # despierta a la mente para que la primera respuesta sea más rápida
        threading.Thread(target=lambda: ollama.generate(model=MODELO, prompt="", keep_alive="30m"),
                         daemon=True).start()
    except Exception:
        pass
    threading.Timer(2, lambda: webbrowser.open(f"http://localhost:{PUERTO}")).start()
    app.run(port=PUERTO, threaded=True)
