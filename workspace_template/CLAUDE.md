# Reels Studio: instrucciones para Claude

Estás dentro de la carpeta de **un proyecto de video** de Reels Studio. Una community manager (no técnica)
te pide reels verticales cortos para sus clientes. Tu trabajo es escribir **specs** (JSON) que el motor
convierte en video. Nunca escribís código ni tocás el motor: sólo specs y notas.

## Qué hay en esta carpeta

| ruta | qué es |
|---|---|
| `entrada/instrucciones.md` | lo que ella quiere: guion, textos, datos (fecha, lugar), duración, tono |
| `entrada/crudos/` | videos crudos del cliente (el material que se edita) |
| `entrada/referencias/` | video(s) de referencia: el **estilo** a imitar (ritmo de cortes, cantidad de texto por plano, animación). También puede haber **imágenes** (capturas de posteos o reels que le gustan): miralas con Read e imitá tipografía, colores, cantidad de texto y disposición |
| `entrada/adjuntos/` | imágenes que adjuntó en un pedido de cambio ("así quiero el título"): el pedido te dice cuáles mirar |
| `analisis/resumen.md` | **empezá por acá**: duración, cortes y tempo de la referencia, movimiento por segundo de cada crudo |
| `analisis/<video>/hoja_NN.jpg` | hojas de contacto (un cuadro cada 0.5 s con su segundo abajo). Son imágenes: miralas con Read |
| `analisis/<video>/cortes.jpg` | (referencias) primer cuadro de cada plano |
| `cliente.json` | marca del cliente: colores, fuentes, pie de página, oscurecido por defecto, notas de tono |
| `entrada/plantilla.json` | (si existe) un estilo ya aprobado: `spec` (estructura base: planos, escenas, animación, música) y `reglas` (qué lo hace reconocible). Usalo como base y adaptá textos, crudos y marca |
| `aprendizajes.md` | (si existe) preferencias de este cliente aprendidas en videos anteriores. **Respetalas siempre** |
| `musica_disponible.json` | pistas con licencia que ella subió. Sólo usalas si lo pide; si no, música sintetizada |
| `versiones/vN/spec.json` | una versión del video. **Nunca modifiques una versión anterior** |
| `versiones/vN/stills/` | cuadros de vista previa que genera `reels stills` |
| `versiones/vN/notas.md` | qué se pidió y qué cambió en esa versión |

## Comandos (los únicos que podés correr)

- `reels check versiones/vN` → valida el spec contra los crudos (errores y avisos en español).
- `reels stills versiones/vN` → genera `versiones/vN/stills/t*.jpg` (un cuadro por escena, cuando el texto
  ya terminó de entrar) y `hoja.jpg`. Para momentos puntuales: `reels stills versiones/vN --times 0.4,3.2,7.8`.

No renderices el video completo: eso lo hace ella desde la app.

## Cómo trabajar

### Primera versión (te lo piden con la carpeta `versiones/v1/` vacía)
1. Leé `entrada/instrucciones.md`, `cliente.json` y `analisis/resumen.md`.
2. Mirá las hojas de la referencia y `cortes.jpg`: cuántos planos, cuánto dura cada uno, cuántas líneas de
   texto por plano, dónde van (casi siempre en el tercio de arriba), qué palabra va resaltada, cuándo entra
   cada línea, si hay pie de página fijo, cómo termina.
3. Mirá las hojas de cada crudo y elegí **los mejores momentos** (acción, caras, pelota, gente festejando;
   evitá cuadros movidos, fuera de foco o con dedos). `movimiento_por_segundo` ayuda a encontrar la acción.
4. Escribí `versiones/v1/spec.json`.
5. `reels check versiones/v1` → corregí hasta que no haya errores.
6. `reels stills versiones/v1` y **mirá cada cuadro** (Read de los .jpg). Corregí si: un texto se corta o
   se sale del cuadro, tapa una cara o lo importante de la imagen, no se lee contra el fondo (subí `darken`
   o movelo), el encuadre corta cabezas, o el plano elegido es feo. Repetí stills hasta que esté bien.
7. Escribí `versiones/v1/notas.md` (qué armaste y por qué, en 3–6 líneas).

### Cambios (te lo piden con `versiones/vN/spec.json` ya copiado de la versión anterior)
1. Leé el pedido. Modificá **lo mínimo** en `versiones/vN/spec.json` (la copia ya está hecha).
2. `reels check`, `reels stills`, mirá los cuadros afectados, corregí.
3. Escribí `versiones/vN/notas.md` con el pedido y lo que cambiaste.

### Gastá pocos pasos (cada lectura de imagen y cada comando consume del límite de uso de ella)
- Si hay `entrada/plantilla.json` **o** ya hay una versión anterior, **no mires las hojas de la referencia**: el
  estilo ya está decidido. Mirá sólo las hojas de los crudos (para elegir tomas) si hace falta.
- En un cambio, no leas `analisis/` salvo que el pedido sea sobre las tomas ("otra toma", "más acción").
  Un cambio de color, texto, tamaño o tiempos no necesita mirar nada: editá el spec directo.
- Stills: generá **una** vez, mirá sólo los cuadros de las escenas que tocaste (`--times` con esos segundos).
  Como máximo **2 rondas** de stills por pedido.
- No releas archivos que ya leíste en esta conversación.

### Aprendizajes del cliente
Si un pedido revela una **preferencia duradera** del cliente (no algo de este video), agregala como un bullet corto
en `aprendizajes.md` (ej. `- Prefiere el título más grande y sin emojis`, `- Nunca usar amarillo`). Así el próximo
video sale bien de entrada. No anotes cosas de un solo video ("cambiar la fecha al 12").

### Siempre
- Terminá con un **resumen corto en español rioplatense** (2–4 líneas, sin tecnicismos: nada de "spec",
  "JSON", "t0") de qué hiciste y, si algo no se pudo, por qué. Ese texto se le muestra a ella tal cual.
- **Nunca dejes textos de relleno** ("acá va la frase clave", "[TÍTULO]", "texto de ejemplo"): el video se
  publica tal cual. Siempre escribí textos reales, cortos y con gancho, pensados para el público de ella.
  Si te piden "una frase clave" o "un slogan", **inventalo vos** (es tu trabajo de copywriter).
  Si falta un dato que no se puede inventar (fecha, dirección, precio), armá el texto sin ese dato
  ("¡Inscripciones abiertas!" en vez de una fecha falsa) y avisalo en el resumen. `reels check` rechaza el relleno.
- Todas las escenas tienen que tener texto: un video sin textos no sirve.
- Nunca bajes nada de internet (ni música ni fuentes). Sólo escribí dentro de esta carpeta.

## El spec

Lienzo 1080×1920 (vertical). Tiempos en segundos. Coordenadas en px del lienzo (`y` = distancia desde arriba).

```jsonc
{
  "format": { "w": 1080, "h": 1920, "fps": 30, "duration": 11.0 },
  "client": "slug-del-cliente",
  "style": {
    "accent": "#caffbf",          // color de las palabras entre *asteriscos*
    "text": "#ffffff",
    "display_font": "Archivo",    // títulos: grotesca ancha en mayúsculas
    "display_stretch": 125, "display_weight": 900,
    "serif_font": "Playfair",     // subtítulos finos
    "darken": 0.32,               // oscurecido general (0.25–0.45). Más alto = el texto se lee mejor
    "top_gradient": 0.20, "bottom_gradient": 0.35,
    "contrast": 1.10, "saturation": 1.18, "vignette": 0.28
  },
  "shots": [   // planos: cubren [0, duration) SIN huecos ni superposición, ordenados
    { "clip": "IMG_9001.MOV",     // nombre del archivo en entrada/crudos/
      "t0": 0.0, "t1": 2.0,       // cuándo se ve en el video
      "src_in": 0.20,             // desde qué segundo del crudo
      "speed": 1.0,               // 0.45–1.0 cámara lenta (limpia con crudos a 60 fps), >1 acelerado
      "zoom": [1.00, 1.10],       // zoom al empezar y al terminar el plano (≥ 1.0)
      "center": [[540, 980], [540, 900]],  // punto del crudo que queda en el centro, al empezar y al terminar
      "transition_in": "cut",     // cut | whip (látigo con blur) | flash | zoom_punch
      "handheld": 5 }             // opcional: flote de cámara de este plano (px)
  ],
  "camera": { "beat_punch": 0.018, "entry_punch": 0.10, "handheld": 5,
              "shakes": [{ "t": 7.0, "amp": 26 }] },     // sacudones (en el drop, en un impacto)
  "effects": [{ "type": "flash", "t": 7.0 },              // flash blanco
              { "type": "fade_out", "t": 10.6, "dur": 0.4 }],  // también "fade_in"
  "scenes": [  // bloques de texto; cada escena se ve entre t0 y t1
    { "t0": 0.0, "t1": 2.0, "lines": [
      { "kind": "display", "text": "CLUB NORTE", "size": 38, "y": 330, "delay": 0.0, "spacing": "0.12em" },
      { "kind": "display", "text": "⚡ TORNEO", "size": 112, "y": 385, "delay": 0.10 },
      { "kind": "display", "text": "*PRIMAVERA*", "size": 112, "y": 500, "delay": 0.30 },
      { "kind": "serif", "text": "Una jornada a puro fútbol.", "size": 60, "y": 620, "delay": 0.5 },
      { "kind": "emoji", "text": "⚽🔥", "size": 120, "y": 700, "delay": 0.9 } ] }
  ],
  "footer": ["LÍNEA 1 DEL PIE", "línea 2"],   // fijo abajo (y≈1700), entra una vez y se queda
  "music": { "mode": "synth", "bpm": 120, "key": "Am", "progression": ["Am","F","C","G"],
             "build": [5.0, 6.5],   // redoble que acelera (opcional)
             "gap": [6.5, 7.0],     // silencio antes del drop (opcional)
             "drop": 7.0,           // golpe fuerte (opcional)
             "whooshes": [2.0, 4.0],  // en los cortes con látigo
             "pops": [7.95],          // cuando aparecen emojis
             "target_lufs": -12 }
  // o { "mode": "file", "path": "<path tal cual de musica_disponible.json>", "offset": 3.2, "license": "<licencia de ahí>" }
  // o { "mode": "none" }
}
```

### Reglas y criterios
- **Texto**: `kind` = `display` (títulos, en mayúsculas automáticamente), `serif` (frase fina),
  `emoji`. Las palabras entre `*asteriscos*` van en el color de acento. `y` es el borde de arriba de la línea.
  El alto de una línea ≈ `size`. Dejá ~10 px entre líneas display y ~20 px antes de una serif.
  Cualquier línea más ancha que 960 px se achica sola, pero mejor elegir tamaños que entren
  (display a 112 px entran ~10–11 caracteres; a 84 px ~14; serif a 60 px ~30).
- Texto en el **tercio de arriba** (y 280–1000); abajo (y > 1650) está el pie. Nada entre 1550 y 1680.
- Máximo 3–4 líneas por escena, salvo el cierre. Cada escena tiene que poder leerse: ≥ 1.8 s en pantalla
  después de que entra la última línea; el último texto ≥ 2 s antes del fundido.
- `delay` escalonado 0.1–0.35 s entre líneas (display cae letra por letra; serif sube; emoji hace pop).
- **Cortes sobre la grilla de beats** (60/bpm s; a 120 BPM cada 0.5 s). `reels check` avisa si no.
  Los cortes de la escena de texto y del plano conviene que coincidan.
- `src_in + (t1 - t0) * speed` no puede pasar la duración del crudo.
- Crudo horizontal: se recorta al centro para 9:16; usá `center` para elegir qué parte se ve.
  `center` está en coordenadas del crudo ya ajustado a 1080×1920. Con zoom 1.0 el centro tiene que ser
  (540, 960) o se ven bordes espejados: con zoom z el centro puede moverse ±540·(1−1/z) en x y ±960·(1−1/z) en y.
- Duración: la que pidan; si no dicen, lo de la referencia (típico 9–15 s).
- Usá los colores, fuentes, pie y `darken` de `cliente.json` salvo que el pedido diga otra cosa.
- Estructura típica: gancho (0–2 s) → info (qué, cuándo) → build → drop con el mensaje principal → cierre
  con lugar/contacto.

### Pedidos típicos → qué tocar
| pedido | cambio |
|---|---|
| "el verde más claro" | `style.accent` más claro (mismo tono) |
| "alargalo a 11 s" | `format.duration`, estirar el último plano y la última escena, mover `fade_out` y `music` |
| "que se lea mejor" | subir `darken`, bajar texto a zona más oscura, o `size` más grande |
| "otra toma al principio" | cambiar `src_in`/`clip` del primer plano (mirá las hojas del crudo) |
| "más rápido / más dinámico" | planos más cortos, `whip` en los cortes, `bpm` más alto |
| "sin música" | `"music": { "mode": "none" }` |
