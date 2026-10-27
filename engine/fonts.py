"""Catálogo de tipografías incluidas (todas libres: OFL / Apache). El nombre es el que va en el spec."""
from __future__ import annotations

# nombre (= archivo en assets/fonts), categoría, para qué sirve
CATALOG: list[dict] = [
    # impacto: títulos grandes, en mayúsculas
    {"name": "Archivo", "cat": "impacto", "desc": "grotesca ancha y pesada, deportiva/urbana (la de siempre)"},
    {"name": "Anton", "cat": "impacto", "desc": "condensada altísima, muy de reel y anuncio"},
    {"name": "BebasNeue", "cat": "impacto", "desc": "condensada limpia, eventos y promos"},
    {"name": "Oswald", "cat": "impacto", "desc": "condensada versátil, noticias e info"},
    {"name": "Unbounded", "cat": "impacto", "desc": "redondeada y ancha, tech/joven"},
    {"name": "RubikMonoOne", "cat": "impacto", "desc": "bloque redondeado, divertida y gamer"},
    # moderna: títulos y textos en minúscula, limpia
    {"name": "Montserrat", "cat": "moderna", "desc": "geométrica clásica, sirve para todo"},
    {"name": "Poppins", "cat": "moderna", "desc": "geométrica amable, emprendimientos y servicios"},
    {"name": "Bricolage", "cat": "moderna", "desc": "con personalidad, editorial/diseño"},
    {"name": "Syne", "cat": "moderna", "desc": "rara y artística, moda y arte"},
    {"name": "DMSans", "cat": "moderna", "desc": "neutra y legible, corporativo"},
    # elegante: serif para frases o títulos finos
    {"name": "Playfair", "cat": "elegante", "desc": "serif clásica de contraste (la de siempre)"},
    {"name": "DMSerifDisplay", "cat": "elegante", "desc": "serif display, gastronomía y lifestyle"},
    {"name": "Fraunces", "cat": "elegante", "desc": "serif cálida y suave, cafés, deco, bienestar"},
    {"name": "InstrumentSerif", "cat": "elegante", "desc": "serif fina y moderna, moda y premium"},
    {"name": "AbrilFatface", "cat": "elegante", "desc": "serif negrísima, títulos editoriales"},
    # manuscrita: toques a mano
    {"name": "Caveat", "cat": "manuscrita", "desc": "escritura a mano natural, cercana"},
    {"name": "Pacifico", "cat": "manuscrita", "desc": "cursiva redonda, verano/dulce/retro"},
    {"name": "PermanentMarker", "cat": "manuscrita", "desc": "marcador grueso, urbano y descontracturado"},
    # mono
    {"name": "SpaceMono", "cat": "mono", "desc": "monoespaciada, tech, datos, máquina de escribir"},
]

NAMES = [f["name"] for f in CATALOG]
