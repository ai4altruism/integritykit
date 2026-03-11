"""
Orientación de redacción para frases tentativas vs directas en español.

Este módulo proporciona orientación sobre cómo redactar actualizaciones de COP en español
según el estado de verificación, incluyendo frases tentativas culturalmente apropiadas
para elementos en revisión y lenguaje directo para elementos verificados.

Usage:
    Use esta orientación al generar borradores de COP para asegurar redacción
    culturalmente apropiada que transmita correctamente certeza o incertidumbre.
"""

from typing import Literal


# Frases tentativas comunes en español para información no verificada
HEDGED_PHRASES_SPANISH = [
    "Según informes no confirmados",
    "Sin confirmar",
    "Se reporta que",
    "Presuntamente",
    "Se está investigando",
    "Pendiente de confirmación",
    "De acuerdo con informes preliminares",
    "Informes iniciales sugieren",
    "Se busca confirmación de",
    "Requiere verificación",
    "Información preliminar indica",
    "Aún no confirmado",
]

# Frases directas para información verificada
DIRECT_PHRASES_SPANISH = [
    "Se confirma",
    "Confirmado",
    "Verificado",
    "Oficialmente",
    "Según fuentes oficiales",
    "Se ha confirmado",
    "Está confirmado que",
    "De manera oficial",
]

# Frases de corrección para información desmentida
CORRECTION_PHRASES_SPANISH = [
    "CORRECCIÓN",
    "DESMENTIDO",
    "RECTIFICACIÓN",
    "Los informes anteriores de... son incorrectos",
    "Contrario a informes previos",
    "Se corrige la información anterior",
]

# Verbos conjugados para estados de verificación
VERIFICATION_VERBS = {
    "verified": {
        "to_be": "está",  # Main Street está cerrada
        "to_have": "ha",  # El refugio ha abierto
        "to_confirm": "se confirma",  # Se confirma el cierre
        "to_report": "informa",  # El DOT informa
    },
    "in_review": {
        "to_be": "estaría",  # Main Street estaría cerrada (condicional)
        "to_have": "habría",  # El refugio habría abierto
        "to_confirm": "se busca confirmar",  # Se busca confirmar el cierre
        "to_report": "reporta",  # Se reporta (no oficial)
    },
    "disproven": {
        "to_be": "no está",  # Main Street no está cerrada
        "to_have": "no ha",  # El refugio no ha cerrado
        "to_confirm": "se desmiente",  # Se desmiente el cierre
        "to_report": "se corrige",  # Se corrige el reporte
    },
}


def get_wording_guidance(
    verification_status: Literal["verified", "in_review", "disproven"],
    risk_tier: Literal["routine", "elevated", "high_stakes"],
) -> dict[str, str | list[str]]:
    """
    Obtiene orientación de redacción basada en el estado de verificación y nivel de riesgo.

    Args:
        verification_status: Estado de verificación del elemento
        risk_tier: Nivel de riesgo del elemento

    Returns:
        Diccionario con orientación de redacción incluyendo frases recomendadas,
        verbos y notas de estilo
    """
    if verification_status == "verified":
        return {
            "style": "direct_factual",
            "recommended_phrases": DIRECT_PHRASES_SPANISH,
            "verbs": VERIFICATION_VERBS["verified"],
            "example": "El puente de la Calle Principal está cerrado a todo tráfico desde las 14:00 hora del Pacífico debido a daños estructurales.",
            "notes": "Use lenguaje definitivo y tiempo presente indicativo. Declare los hechos directamente sin matices.",
        }
    elif verification_status == "in_review":
        guidance = {
            "style": "hedged_uncertain",
            "recommended_phrases": HEDGED_PHRASES_SPANISH,
            "verbs": VERIFICATION_VERBS["in_review"],
            "example": "Sin confirmar: Según informes, el puente de la Calle Principal podría estar cerrado. Se busca confirmación oficial del Departamento de Transporte del condado.",
            "notes": "Use lenguaje cauteloso y condicional. Haga explícita la incertidumbre. Declare lo que se sabe y lo que se desconoce.",
        }
        if risk_tier == "high_stakes":
            guidance["additional_requirements"] = [
                "Incluya el siguiente paso de verificación",
                "Especifique hora de reverificación",
                "Indique la fuente que se está contactando",
            ]
        return guidance
    else:  # disproven
        return {
            "style": "correction",
            "recommended_phrases": CORRECTION_PHRASES_SPANISH,
            "verbs": VERIFICATION_VERBS["disproven"],
            "example": "CORRECCIÓN: Los informes anteriores sobre el cierre del puente de la Calle Principal son incorrectos. El puente permanece abierto según el Departamento de Transporte del condado a las 15:00 hora del Pacífico.",
            "notes": "Comience con CORRECCIÓN o DESMENTIDO en mayúsculas. Declare claramente qué era incorrecto. Proporcione la información correcta.",
        }


def format_timestamp_spanish(timestamp: str, timezone: str = "hora del Pacífico") -> str:
    """
    Formatea una marca de tiempo para uso en COP en español.

    Args:
        timestamp: Marca de tiempo en formato ISO o similar
        timezone: Zona horaria a mostrar

    Returns:
        Marca de tiempo formateada apropiadamente para COP en español
    """
    # Ejemplo: "14:00 hora del Pacífico" o "14 de marzo, 15:30 hora del Este"
    # Esta es una función auxiliar para formateo consistente
    return f"{timestamp} {timezone}"


def get_date_format_spanish() -> str:
    """
    Retorna el formato de fecha recomendado para COP en español.

    Returns:
        Patrón de formato de fecha (e.g., "14 de marzo de 2026, 15:30 hora del Pacífico")
    """
    return "%d de %B de %Y, %H:%M"


# Ejemplos de elementos de línea completos para referencia
EXAMPLE_LINE_ITEMS_SPANISH = {
    "verified": """[VERIFICADO] El refugio en la Escuela Primaria Lincoln está operativo y acepta familias desde las 14:00 hora del Pacífico. Capacidad: 200 personas. Contacto: coordinador@refugio.org. (Fuente: Coordinador de Refugio Sarah Martinez, mensaje de Slack 2026-03-10 14:15)""",
    "in_review": """[EN REVISIÓN] Sin confirmar: Según informes, el refugio en la Escuela Primaria Lincoln estaría aceptando familias. Se busca confirmación del coordinador de refugio. Siguiente paso: Contactar a Sarah Martinez. Reverificar: 16:00 hora del Pacífico. (Fuente: mensaje de comunidad, pendiente de verificación)""",
    "in_review_high_stakes": """[EN REVISIÓN - ALTO RIESGO] Sin confirmar: Informes preliminares sugieren posible contaminación de suministro de agua en el sector este. REQUIERE VERIFICACIÓN URGENTE. Siguiente paso: Contactar inmediatamente al Departamento de Salud Pública. Reverificar: 15:30 hora del Pacífico. NO distribuir públicamente hasta confirmar. (Fuente: reporte de residente, sin confirmar)""",
    "disproven": """[DESMENTIDO] CORRECCIÓN: Los informes anteriores de cierre del refugio en la Escuela Primaria Lincoln son incorrectos. El refugio permanece abierto y operativo según confirmación del coordinador Sarah Martinez a las 15:00 hora del Pacífico. (Fuente: Verificación directa con coordinador de refugio)""",
}


# Orientación para facilitadores sobre cuándo usar cada estilo
FACILITATOR_GUIDANCE_SPANISH = """
Guía de Redacción para Facilitadores - COP en Español

1. INFORMACIÓN VERIFICADA (Estilo Directo):
   - Use cuando tenga confirmación de fuente autorizada
   - Emplee tiempo presente indicativo
   - Sea específico y definitivo
   - Ejemplo: "El puente está cerrado" (no "estaría cerrado")

2. INFORMACIÓN EN REVISIÓN (Estilo Tentativo):
   - Use cuando la información no esté confirmada
   - Emplee frases como "Sin confirmar", "Según informes"
   - Use tiempo condicional cuando sea apropiado
   - Ejemplo: "El puente podría estar cerrado" o "El puente estaría cerrado"
   - Declare explícitamente qué se está verificando

3. INFORMACIÓN DE ALTO RIESGO EN REVISIÓN:
   - Siempre incluya próximo paso de verificación
   - Especifique hora exacta de reverificación
   - Considere no publicar hasta verificar si el riesgo es crítico
   - Sea explícito sobre la incertidumbre

4. CORRECCIONES Y DESMENTIDOS:
   - Comience con "CORRECCIÓN:" o "DESMENTIDO:" en mayúsculas
   - Declare claramente qué era incorrecto
   - Proporcione la información correcta
   - Incluya cuándo se confirmó la corrección

5. FORMATEO DE FECHAS Y HORAS:
   - Use formato de 24 horas: 14:00, no 2:00 PM
   - Incluya siempre zona horaria: "14:00 hora del Pacífico"
   - Fechas: "14 de marzo de 2026" (día primero)

6. CONSIDERACIONES CULTURALES:
   - El español permite más flexibilidad en orden de palabras
   - Use voz activa cuando sea posible
   - "Se confirma" es apropiado para voz pasiva formal
   - Evite anglicismos innecesarios
"""
