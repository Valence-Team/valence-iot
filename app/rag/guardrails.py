import re
import unicodedata
from enum import StrEnum

EXPLICACAO_FIXA = (
    "Não há informação suficiente para explicar este caso com segurança. "
    "Ele foi encaminhado para um agrônomo, que vai analisar a foto e o relato e orientar "
    "o que fazer. Enquanto isso, não aplique nenhum produto sem orientação técnica."
)


class MotivoBloqueio(StrEnum):
    DOSE = "DOSE"
    PRODUTO = "PRODUTO"
    SEM_CITACAO = "SEM_CITACAO"
    VAZIA = "VAZIA"


# Padrões de dose
_NUMERO = r"\d+(?:[.,]\d+)?"
_UNIDADE = r"(?:ml|mL|l|L|litros?|g|gramas?|kg|quilos?|cc|cm3|ppm)"
_AREA = r"(?:ha|hectares?|alqueires?|litros?|l|L|planta|pé|m2|m²|100\s*l)"
PADROES_DOSE = (
    re.compile(rf"{_UNIDADE}\s*(?:/|por)\s*{_AREA}\b", re.I),
    re.compile(r"\bpor\s+(?:cada\s+)?(?:litro|hectare|alqueire|bomba|pulveriza[cç][aã]o)\b", re.I),
    re.compile(rf"\b{_NUMERO}\s*%\s*(?:de\s+)?(?:calda|solu[cç][aã]o|concentra)", re.I),
    re.compile(r"\bdose\s+de\s+\d", re.I),
)

# Princípios ativos e nomes comerciais comuns em milho, tomate e batata
PRODUTOS = (
    "abamectina",
    "acefato",
    "acetamiprido",
    "azoxistrobina",
    "bifentrina",
    "boscalida",
    "calda bordalesa",
    "calda vicosa",
    "captana",
    "carbendazim",
    "cimoxanil",
    "ciproconazol",
    "clorantraniliprole",
    "clorfenapir",
    "clorotalonil",
    "clorpirifos",
    "deltametrina",
    "oxicloreto de cobre",
    "sulfato de cobre",
    "hidroxido de cobre",
    "base de cobre",
    "difenoconazol",
    "dimetomorfe",
    "espinetoram",
    "espinosade",
    "fipronil",
    "fluazinam",
    "glifosato",
    "imidacloprido",
    "indoxacarbe",
    "lambda-cialotrina",
    "lambdacialotrina",
    "mancozebe",
    "mancozeb",
    "metalaxil",
    "metomil",
    "piraclostrobina",
    "propinebe",
    "tebuconazol",
    "tiametoxam",
    "tiofanato",
    "trifloxistrobina",
    "actara",
    "amistar",
    "bravonil",
    "cabrio",
    "curzate",
    "decis",
    "dithane",
    "engeo",
    "karate",
    "lannate",
    "manzate",
    "orthene",
    "priori",
    "ridomil",
    "vertimec",
    "roundup",
)
_PRODUTOS = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in PRODUTOS) + r")\b", re.I)
# Aceita [1], [1][2] e [1, 3]
_CITACAO = re.compile(r"\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\]")


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def citacoes(texto: str) -> set[int]:
    return {int(n) for grupo in _CITACAO.findall(texto) for n in re.findall(r"\d+", grupo)}


def verificar(texto: str, quantidade_trechos: int) -> MotivoBloqueio | None:
    if not texto.strip():
        return MotivoBloqueio.VAZIA
    if any(padrao.search(texto) for padrao in PADROES_DOSE):
        return MotivoBloqueio.DOSE
    if _PRODUTOS.search(_sem_acento(texto)):
        return MotivoBloqueio.PRODUTO
    validas = {n for n in citacoes(texto) if 1 <= n <= quantidade_trechos}
    if not validas:
        return MotivoBloqueio.SEM_CITACAO
    return None


# Remove raciocínio que algum provedor devolva junto do texto e marcação de Markdown
_RACIOCINIO = re.compile(r"<think>.*?</think>", re.S | re.I)
_ENFASE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.S)


def limpar(texto: str | None) -> str:
    texto = _RACIOCINIO.sub("", texto or "")
    texto = _ENFASE.sub(lambda m: m.group(1) or m.group(2), texto)
    return texto.strip()
