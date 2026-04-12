# IIS 2026

Projekt za predmet Inzenirstvo inteligentnih sistemov.

## Zagon projekta

Za namestitev odvisnosti in pripravo okolja:

```powershell
python -m uv sync
```

Za zajem svezi podatkov:

```powershell
python -m uv run python src/data/fetch_air_data.py
```

Za predprocesiranje podatkov za vse merilne postaje:

```powershell
python -m uv run python src/data/preprocess_air_data.py
```

## Struktura

- `data/raw/air/air_data.xml`: surovi XML podatki iz ARSO
- `data/preprocessed/air/*.csv`: predprocesirani podatki po merilnih postajah
- `src/data/`: skripte za zajem in obdelavo podatkov
- `.github/workflows/`: GitHub Actions poteki dela

## DVC

DVC je inicializiran in podatki so pripravljeni za verzioniranje z `dvc add data`.
Oddaljeni DagsHub remote in DVC cevovodi (`dvc.yaml`) se dodajo v naslednjem koraku.
