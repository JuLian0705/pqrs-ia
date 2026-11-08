"""Mide la precisión del clasificador contra 20 PQRS etiquetadas a mano.

Uso (desde la carpeta backend):
    python evaluacion/evaluar_clasificador.py --modo ia       # Llama vía Ollama
    python evaluacion/evaluar_clasificador.py --modo reglas   # respaldo por palabras clave

Genera evaluacion/resultados_<modo>.md (tabla lista para pegar en el informe)
y evaluacion/resultados_<modo>.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

from app.config import settings  # noqa: E402
from app.services.clasificador import clasificar  # noqa: E402

CAMPOS = ("tipo", "categoria", "prioridad")


def evaluar(modo: str) -> dict:
    casos = json.loads((RAIZ / "dataset_pqrs.json").read_text(encoding="utf-8"))
    filas, tiempos, fallbacks = [], [], 0
    aciertos = {c: 0 for c in CAMPOS}

    for caso in casos:
        r = clasificar(caso["asunto"], caso["descripcion"], usar_ia=(modo == "ia"))
        if modo == "ia" and r.origen != "ia":
            fallbacks += 1
        tiempos.append(r.duracion_ms)
        obtenido = {c: getattr(r, c) for c in CAMPOS}
        ok = {c: obtenido[c] == caso["esperado"][c] for c in CAMPOS}
        for c in CAMPOS:
            aciertos[c] += ok[c]
        filas.append({"id": caso["id"], "asunto": caso["asunto"], "esperado": caso["esperado"],
                      "obtenido": obtenido, "aciertos": ok, "origen": r.origen, "ms": r.duracion_ms})
        marca = " ".join("✔" if ok[c] else "✘" for c in CAMPOS)
        print(f"#{caso['id']:>2} {marca}  {caso['asunto'][:40]:<40} {r.origen:<6} {r.duracion_ms} ms")

    total = len(casos)
    return {
        "modo": modo,
        "modelo": settings.ollama_modelo if modo == "ia" else "reglas",
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total": total,
        "precision": {c: round(100 * aciertos[c] / total, 1) for c in CAMPOS},
        "aciertos": aciertos,
        "casos_completos": sum(all(f["aciertos"].values()) for f in filas),
        "tiempo_promedio_ms": round(statistics.mean(tiempos)),
        "tiempo_max_ms": max(tiempos),
        "fallbacks_a_reglas": fallbacks,
        "filas": filas,
    }


def a_markdown(res: dict) -> str:
    p, a, n = res["precision"], res["aciertos"], res["total"]
    lineas = [
        f"# Evaluación del clasificador ({res['modo']})",
        "",
        f"- Modelo: `{res['modelo']}`  ",
        f"- Fecha: {res['fecha']}  ",
        f"- Casos evaluados: {n}  ",
        f"- Tiempo promedio por PQRS: {res['tiempo_promedio_ms']} ms (máximo {res['tiempo_max_ms']} ms)  ",
    ]
    if res["modo"] == "ia":
        lineas.append(f"- Casos en que la IA falló y se usó el respaldo por reglas: {res['fallbacks_a_reglas']}  ")
    lineas += [
        "",
        "| Campo | Aciertos | Precisión |",
        "|---|---|---|",
        f"| Tipo (P/Q/R/S) | {a['tipo']}/{n} | {p['tipo']} % |",
        f"| Categoría | {a['categoria']}/{n} | {p['categoria']} % |",
        f"| Prioridad | {a['prioridad']}/{n} | {p['prioridad']} % |",
        f"| Los tres campos correctos | {res['casos_completos']}/{n} | {round(100 * res['casos_completos'] / n, 1)} % |",
        "",
        "## Detalle por caso",
        "",
        "| # | Asunto | Tipo esp./obt. | Categoría esp./obt. | Prioridad esp./obt. |",
        "|---|---|---|---|---|",
    ]
    for f in res["filas"]:
        celdas = []
        for c in CAMPOS:
            esp, obt = f["esperado"][c], f["obtenido"][c]
            celdas.append(f"{esp} / {obt}" + ("" if esp == obt else " ✘"))
        lineas.append(f"| {f['id']} | {f['asunto']} | " + " | ".join(celdas) + " |")
    return "\n".join(lineas) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modo", choices=["ia", "reglas"], default="ia")
    args = parser.parse_args()

    res = evaluar(args.modo)
    (RAIZ / f"resultados_{args.modo}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (RAIZ / f"resultados_{args.modo}.md").write_text(a_markdown(res), encoding="utf-8")
    p = res["precision"]
    print(f"\nPrecisión → tipo {p['tipo']} % | categoría {p['categoria']} % | prioridad {p['prioridad']} %")
    print(f"Resultados guardados en evaluacion/resultados_{args.modo}.md")


if __name__ == "__main__":
    main()
