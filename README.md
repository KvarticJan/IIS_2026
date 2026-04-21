# IIS 2026

Projekt za predmet Inzenirstvo inteligentnih sistemov.

## Zagon projekta

Za namestitev odvisnosti in pripravo okolja:

```powershell
python -m uv sync
```

Za zajem svezih podatkov:

```powershell
uv run python src/data/fetch_air_data.py
```

Za predprocesiranje podatkov za vse merilne postaje:

```powershell
uv run python src/data/preprocess_air_data.py
```

Za validacijo podatkov z Great Expectations:

```powershell
uv run python gx/run_checkpoint.py
```

Za testiranje podatkov z Evidently:

```powershell
uv run python src/data/test_data.py
```

Za namensko osvezitev Evidently referenc, ce se je baseline legitimno spremenil:

```powershell
$env:EVIDENTLY_REFRESH_REFERENCE_ON_FAILURE="1"
uv run python src/data/test_data.py
Remove-Item Env:EVIDENTLY_REFRESH_REFERENCE_ON_FAILURE
```

Za ucenje modela:

```powershell
uv run python src/model/train.py
```

## Sledenje eksperimentom

Projekt podpira sledenje eksperimentom z MLflow.

- Lokalno se brez dodatnih nastavitev belezenje shrani v mapo `mlruns/`.
- Na GitHub workflowu se belezenje poslje na DagsHub MLflow endpoint `https://dagshub.com/KvarticJan/IIS_2026.mlflow`.

Za lokalni oddaljeni MLflow zagon po potrebi nastavis:

```powershell
$env:MLFLOW_TRACKING_URI="https://dagshub.com/KvarticJan/IIS_2026.mlflow"
$env:MLFLOW_TRACKING_USERNAME="KvarticJan"
$env:MLFLOW_TRACKING_PASSWORD="<tvoj_dagshub_token>"
uv run python src/model/train.py
```

Za GitHub Actions dodaj secreta:

- `MLFLOW_TRACKING_USERNAME`
- `MLFLOW_TRACKING_PASSWORD`

## Struktura

- `data/raw/air/air_data.xml`: surovi XML podatki iz ARSO
- `data/preprocessed/air/*.csv`: predprocesirani podatki po merilnih postajah
- `data/reference/air/*.csv`: referencni podatki za Evidently drift teste
- `gx/`: Great Expectations kontekst, expectation suite-i in data docs
- `models/`: nauceni modeli in serializirani preprocessing pipeline-i
- `reports/`: Evidently in model evaluation porocila
- `src/data/`: skripte za zajem, obdelavo, validacijo in testiranje podatkov
- `src/model/`: skripte za pripravo casovnih oken in ucenje modela
- `.github/workflows/`: GitHub Actions poteki dela

## DVC

Projekt uporablja DVC pipeline:

- `fetch`: zajem surovih ARSO podatkov
- `preprocess`: priprava CSV datotek za vse merilne postaje
- `validate`: Great Expectations validacija
- `test_data`: Evidently drift testiranje
- `train`: ucenje LSTM modela za izbrano postajo

Za zagon celotnega cevovoda:

```powershell
python -m dvc repro
```

Za prvi osvezitveni zagon po vecji spremembi podatkov lahko pred `dvc repro` zacasno nastavis:

```powershell
$env:EVIDENTLY_REFRESH_REFERENCE_ON_FAILURE="1"
python -m dvc repro test_data train
Remove-Item Env:EVIDENTLY_REFRESH_REFERENCE_ON_FAILURE
```
