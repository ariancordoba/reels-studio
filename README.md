# Reels Studio

App local para generar reels verticales a partir de crudos + referencia + instrucciones.
Claude (vía Claude Code) analiza la referencia y escribe el guion; el motor local renderiza.

## Instalar (Windows, compu y laptop)

1. Instalar Claude Code e iniciar sesión (una vez): abrir una terminal, escribir `claude` y seguir el login.
2. Doble clic en `INSTALAR.bat`: instala uv, Python 3.12, dependencias y Chromium, y crea el acceso directo
   "Reels Studio" en el escritorio y en el menú Inicio. Se puede volver a correr para reparar.
3. En la primera apertura: nombre + carpeta de datos. En las dos máquinas elegir **la misma carpeta de OneDrive**.

`ABRIR.bat` abre la app sin consola (lo mismo que el acceso directo). Logs: `%LOCALAPPDATA%\ReelsStudio\logs`.

## Cómo está armado

| carpeta | qué hay |
|---|---|
| `engine/` | motor: spec (contrato), análisis, proxies, textos (Chromium), composición, música, stills, CLI |
| `app/` | servidor FastAPI + ventana (pywebview), cola de trabajos, `ClaudeRunner`, flujo de versiones |
| `ui/` | interfaz React + Tailwind. `ui/dist` es lo que sirve la app (ya compilado: no hace falta Node) |
| `workspace_template/CLAUDE.md` | instrucciones que lee Claude dentro de cada proyecto |
| `assets/` | fuentes (OFL), ícono |

Datos (sincronizados): `<carpeta>/clientes`, `<carpeta>/proyectos/<fecha>-<nombre>/versiones/vN`, `musica`,
`plantillas`. Caches pesados (cuadros de crudos, textos) en `%LOCALAPPDATA%\ReelsStudio\cache`.
Un `proyecto.lock` evita que las dos máquinas trabajen el mismo proyecto a la vez.

## CLI

```
uv run reels check   <proyecto | versión | spec.json>   # valida el spec contra los crudos
uv run reels stills  <…> [--times 0.5,3.2]              # cuadros sueltos + hoja de contacto
uv run reels render  <…> [--draft]                      # video final 1080p (o borrador 540p)
uv run reels music   <…>                                # sólo la música (wav)
uv run reels analyze <proyecto>                         # hojas de contacto, cortes, tempo
uv run reels nuevo --titulo T --cliente slug --crudos a.mov --referencias r.mp4 --instrucciones "…"
uv run reels pedir <proyecto> "el verde más claro"      # versión nueva con Claude
```

`--json` (antes del subcomando) imprime un evento JSON por línea (lo usa la app).

## Desarrollo

```
uv run python -m app.main --browser     # servidor en http://127.0.0.1:8765 sin ventana
cd ui && npm install && npm run dev     # UI con recarga en caliente (proxy a :8765)
cd ui && npm run build                  # recompilar ui/dist
uv run pytest                           # tests (incluye regresión contra el video aprobado, ~2 min)
```

La regresión contra el video aprobado usa material privado en `ejemplo/` (no está en el repo): sin esos archivos
esos tests se saltean solos.

## Compartir y publicar actualizaciones

1. Subí el número en `VERSION` (ej. `0.2.1`).
2. `uv run python scripts/empaquetar.py --notas "qué cambió"` → `dist/reels-studio-<versión>.zip` (sin tests ni
   videos de ejemplo) + `dist/update.json` con el hash.
3. Publicarlo, una de dos:
   - **GitHub (recomendado):** repo **público**, creá un release con tag `v0.2.1` y adjuntá el zip.
     En `update_source.txt` poné `github:usuario/repo` (una sola vez, antes de pasarles el primer zip).
   - **Cualquier hosting:** subí el zip, poné su URL en `update.json` (`--url …`), subí `update.json` y poné su URL
     en `update_source.txt`.
4. Tus amigos: Ajustes → "Buscar actualizaciones" → "Actualizar ahora". La app se cierra, hace backup, se actualiza,
   corre `uv sync` y se vuelve a abrir (si algo falla, vuelve sola a la versión anterior).

Para la primera instalación se les pasa el zip: lo descomprimen en cualquier lado y hacen doble clic en
`INSTALAR.bat` (copia la app a `%LOCALAPPDATA%\Programs\ReelsStudio`). `LEEME.txt` explica todo paso a paso.

## Ahorro de tokens

- **Plantillas:** un video aprobado (o un estilo que Claude aprende una sola vez de una referencia) se reusa; la
  primera versión la arma el motor (`engine/autofill.py`: elige tramos por movimiento + nitidez) sin Claude.
- **Ajustes rápidos** (acento, oscurecido, tamaño de texto, música) y la pestaña Guion: sin Claude.
- **Aprendizajes por cliente:** Claude anota preferencias duraderas en `aprendizajes.md`; se copian al cliente y se
  respetan en los videos siguientes.
- **Uso de Claude** (Ajustes): Equilibrado = modelo más capaz para la primera versión y Sonnet para cambios.
- `CLAUDE.md` le pide a Claude no volver a mirar la referencia cuando ya hay estilo, y máximo 2 rondas de stills.

## Licencias

- Curvas de animación propias (`engine/motion.py`, `engine/text_comp/motion.js`); no se usa código
  PolyForm Noncommercial.
- `assets/fonts`: Archivo, Playfair y Noto Color Emoji (OFL, licencias al lado).
- Música: sintetizada por el motor, o pistas subidas con la licencia anotada.
- `referencia_motor_v0/` es el prototipo original, sólo como referencia (no lo usa la app).
