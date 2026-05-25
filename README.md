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

Evidently primerja zadnje `data_testing.compare_window_rows` vrstice iz `params.yaml`, da dnevni prirast zgodovine ne povzroca laznih alarmov na celotnem arhivu.

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

Privzeto se zaradi `train.station: "all"` v `params.yaml` modeli naucijo za vsa merilna mesta, ki imajo dovolj veljavnih `PM10` vrednosti. Merilna mesta brez uporabnih ciljnih vrednosti se zabelezijo kot preskocena v `reports/model_training/summary.json`.

Za hiter lokalni test ene postaje lahko uporabis:

```powershell
$env:TRAIN_STATION="E410"
uv run python src/model/train.py
Remove-Item Env:TRAIN_STATION
```

Trening shrani:

- `models/model_<postaja>.keras`
- `models/model_<postaja>.onnx`
- `models/pipeline_<postaja>.pkl`
- `reports/model_training/<postaja>.json`

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

## GitHub Actions nacin validacije

Scheduled `Fetch data on schedule` zagon samodejno osvezi Evidently reference, ce drift pade, ker je namenjen rednemu premikanju podatkovnega baseline-a.

Rocni `Run workflow` zagon je privzeto strog. `refresh_reference = true` izberi samo takrat, ko zelis novo stanje podatkov sprejeti kot novo referenco.

Workflow `Train model` se zazene po uspesno zakljucenem workflowu `Fetch data on schedule` in za dnevni CI privzeto trenira demonstracijsko postajo `E410`, da scheduled zagon ne traja predolgo. Rocno ga lahko zazenes tudi z `train_station = all`, s cimer preveris zahtevo, da modelna skripta deluje za vsa merilna mesta.

## Objavljena porocila

Workflow `Fetch data on schedule` po uspesnem podatkovnem cevovodu zgradi staticki portal `reports/site`, ki zdruzi:

- Great Expectations Data Docs iz `gx/uncommitted/data_docs/local_site`
- Evidently HTML porocila iz `reports/data_testing`

Portal je objavljen na:

- https://iis2026.netlify.app

Netlify site je `iis2026`, njegov `site_id` pa je ze nastavljen v GitHub workflowu:

- `792b62f5-56d0-4b4a-9dd0-4fd88b303300`

Za samodejno objavo iz GitHub Actions dodaj samo se GitHub Actions secret:

- `NETLIFY_AUTH_TOKEN`

Priporocen postopek za token:

1. V Netlify odpri `User settings` -> `Applications` -> `Personal access tokens` in ustvari token.
2. V GitHub repozitoriju odpri `Settings` -> `Secrets and variables` -> `Actions` in dodaj secret `NETLIFY_AUTH_TOKEN`.
3. Rocno zazeni workflow `Fetch data on schedule`; po uspesnem zagonu mora Netlify osveziti portal z GX in Evidently porocili.

Ce secret ni nastavljen, se deploy preskoci, podatkovni DVC pipeline pa se vedno ostane uporaben.

## Struktura

- `data/raw/air/air_data.xml`: surovi XML podatki iz ARSO
- `data/preprocessed/air/*.csv`: predprocesirani podatki po merilnih postajah
- `data/reference/air/*.csv`: referencni podatki za Evidently drift teste
- `gx/`: Great Expectations kontekst, expectation suite-i in data docs
- `models/`: nauceni modeli in serializirani preprocessing pipeline-i
- `reports/`: Evidently, Netlify in model evaluation porocila
- `src/data/`: skripte za zajem, obdelavo, validacijo in testiranje podatkov
- `src/model/`: skripte za pripravo casovnih oken in ucenje modela
- `.github/workflows/`: GitHub Actions poteki dela

## DVC

Projekt uporablja DVC pipeline:

- `fetch`: zajem surovih ARSO podatkov
- `preprocess`: priprava CSV datotek za vse merilne postaje
- `validate`: Great Expectations validacija
- `test_data`: Evidently drift testiranje
- `train`: ucenje LSTM modelov in ONNX izvoz za izbrana merilna mesta

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
