"""Qué tipo de contrato es, dentro de los que mencionan paellas.

Muchos contratos dicen "paella" pero no son el servicio de paella: la leña, la
orquesta o las sillas de "la noche de las paellas", o la reparación de un
"paellero" (barbacoa de obra). Aquí se separan:

- SERVICIO:     el ayuntamiento contrata a alguien que cocina y sirve la paella (tu servicio).
- INGREDIENTES: compra arroz, carne, etc. y la cocinan ellos (hay demanda: se les puede ofrecer el servicio).
- EVENTO:       otros servicios para un evento de paellas (leña, orquesta, sillas, seguridad...).
- EQUIPAMIENTO: paelleros, cocinas, obras, reparaciones. No es comida.
"""

from __future__ import annotations

import re

from comun import normalizar

SERVICIO = "Servicio de paella"
INGREDIENTES = "Ingredientes para paellas"
EVENTO = "Otros servicios del evento"
EQUIPAMIENTO = "Equipamiento u obras"
CATEGORIAS = (SERVICIO, INGREDIENTES, EVENTO, EQUIPAMIENTO)


def _re(*partes: str) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(partes) + r")")


EQUIPO = _re(
    r"paeller[oa]s?\b", r"paelleros", r"sarten basculant", r"paella basculant", r"marmita", r"repar",
    r"homologacio", r"proyecto", r"projecte", r"obras?\b", r"obres", r"vallad", r"cerramiento",
    r"campana", r"geotecn", r"aceras", r"candados", r"mueble", r"electrodomestic", r"memoria valorada",
    r"pla de la paella", r"kit de paeller", r"paellers", r"instal lacio", r"programador",
)
EVENTO_AUX = _re(
    r"llenya", r"lena\b", r"lenas", r"orquest", r"dj\b", r"dj s", r"discomovil", r"disco movil", r"disco paellas",
    r"sonido", r"so i llum", r"iluminacio", r"luz\b", r"llum", r"escenario", r"sillas", r"cadires", r"mesas\b",
    r"carpa", r"wc\b", r"sanitari", r"ambulanci", r"seguridad", r"vigilancia", r"limpieza", r"neteja",
    r"generador", r"grupo? electrogen", r"grupelectrogen", r"vasos", r"cubrevasos", r"menaje", r"bebidas?",
    r"begudes", r"refrescos", r"control de? acce", r"control acces", r"tanques", r"hinchables", r"charanga",
    r"trofeos", r"pergaminos", r"extintores", r"camion", r"acta de", r"test de", r"estudio", r"bus\b",
    r"palmitos", r"impresion", r"entradas", r"actuacio", r"musical", r"animacion", r"amenizacion",
    r"actividades infantiles", r"esculturas", r"arena", r"grifos", r"docencia", r"curso", r"aforos",
    r"montaje", r"desmontaje", r"recapte", r"produccion del evento", r"show", r"karaoke", r"caramelos",
    r"camions", r"frigorific", r"taller", r"materiales? varios", r"lloguer", r"alquiler", r"sorra",
    r"urinaris", r"contenidor", r"seguretat", r"valles", r"carpes", r"sonoritzacio", r"il luminacio",
    r"grup musical", r"orquestra", r"seguro", r"polissa", r"poliza", r"responsabilitat", r"juegos",
    r"asistencia extrahospitalaria", r"assistencia extrahospitalaria", r"sanitario",
)
INGRED = _re(
    r"ingredient", r"carnic", r"carne", r"carn\b", r"arroz\b", r"arros\b", r"aceite", r"aliment", r"pollo", r"conejo",
    r"productos? (de )?alimentacio", r"productes", r"comestibles", r"suministros? para (el )?concurso",
)
SERVICIO_FUERTE = _re(
    r"elaboracio", r"elaborar", r"realitzacio", r"realizacio", r"preparacio", r"cocinado", r"cocinar\b",
    r"servicio de (la )?paella", r"servicio paella", r"servei de paella", r"paella (gigante|gegant|monumental|colectiva|popular)",
    r"paelles? gegants?", r"paellas? gigantes?", r"racion", r"degustacion", r"comensales", r"\d+ person",
    r"catering", r"paella para", r"paella per", r"paella y", r"paella i", r"paella comida", r"paellas? para",
    r"suministro,? (de )?paella", r"subministrament d arros", r"arros al forn",
)


def categoria(objeto: str) -> str:
    """Clasifica un contrato que menciona paellas según su objeto."""
    t = normalizar(objeto)
    servicio = SERVICIO_FUERTE.search(t)
    evento = EVENTO_AUX.search(t)
    equipo = EQUIPO.search(t)
    ingred = INGRED.search(t)
    # Lo que va primero en el texto suele ser lo que se contrata:
    # "Alquiler de sillas para la paella gigante" -> evento; "Paella gigante y alquiler de sillas" -> servicio.
    if equipo and not (servicio and servicio.start() < equipo.start()):
        return EQUIPAMIENTO
    if evento and not (servicio and servicio.start() < evento.start()):
        return EVENTO
    if ingred and not (servicio and servicio.start() < ingred.start()):
        return INGREDIENTES
    if servicio:
        return SERVICIO
    # Solo dice "Paella ..." o "Paellas para el día 9 de octubre": casi siempre es el servicio.
    return SERVICIO


_AYUNTAMIENTO = re.compile(r"ayuntamiento|ajuntament|alcald|concejal|regidor|junta de gobierno|patronato municipal",
                           re.I)


def es_ayuntamiento(organo: str) -> bool:
    """El órgano es un ayuntamiento (o un organismo municipal), no una universidad, Diputación, etc."""
    return bool(_AYUNTAMIENTO.search(organo or ""))


# Nombres distintos para el mismo municipio
ALIAS = {
    "castello": "Castelló de la Plana",
    "castellon": "Castelló de la Plana",
    "castellon de la plana": "Castelló de la Plana",
    "castello de la plana": "Castelló de la Plana",
    "san vicente raspeig": "Sant Vicent del Raspeig",
    "san vicente del raspeig": "Sant Vicent del Raspeig",
}


def nombre_municipio(nombre: str) -> str:
    return ALIAS.get(normalizar(nombre), nombre)
