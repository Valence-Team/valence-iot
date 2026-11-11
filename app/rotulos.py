import json
from pathlib import Path

from pydantic import TypeAdapter

from app.schemas import Contrato, Cultura

ROTULOS_PATH = Path(__file__).resolve().parent.parent / "dados" / "rotulos.json"


class Rotulo(Contrato):
    rotulo: str
    classe_plant_village: str
    cultura: Cultura
    nome: str
    nome_cientifico: str | None
    saudavel: bool


def carregar_rotulos(caminho: Path = ROTULOS_PATH) -> dict[str, Rotulo]:
    lista = TypeAdapter(list[Rotulo]).validate_python(
        json.loads(caminho.read_text(encoding="utf-8"))
    )
    return {item.rotulo: item for item in lista}
