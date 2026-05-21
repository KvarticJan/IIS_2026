import os
import shutil
import stat
from pathlib import Path


GX_SITE_DIR = Path("gx/uncommitted/data_docs/local_site")
EVIDENTLY_REPORTS_DIR = Path("reports/data_testing")
OUTPUT_DIR = Path(os.getenv("REPORT_SITE_DIR", "reports/site"))


def _copy_gx_reports() -> None:
    if not (GX_SITE_DIR / "index.html").exists():
        raise FileNotFoundError(f"Great Expectations report site not found at {GX_SITE_DIR}")

    destination = OUTPUT_DIR / "gx"
    shutil.copytree(GX_SITE_DIR, destination)


def _copy_evidently_reports() -> list[Path]:
    report_paths = sorted(EVIDENTLY_REPORTS_DIR.glob("*.html"))
    if not report_paths:
        raise FileNotFoundError(f"Evidently HTML reports not found in {EVIDENTLY_REPORTS_DIR}")

    destination = OUTPUT_DIR / "evidently"
    destination.mkdir(parents=True, exist_ok=True)

    copied_reports = []
    for report_path in report_paths:
        copied_path = destination / report_path.name
        shutil.copy2(report_path, copied_path)
        copied_reports.append(copied_path)

    return copied_reports


def _write_index(evidently_reports: list[Path]) -> None:
    evidently_links = "\n".join(
        f'<li><a href="evidently/{report.name}">{report.stem}</a></li>' for report in evidently_reports
    )

    index_html = f"""<!doctype html>
<html lang="sl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IIS 2026 Reports</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5d6d7e;
      --paper: #f7f3ea;
      --card: #fffaf0;
      --accent: #1f7a6d;
      --line: #dfd4bf;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 16%, rgba(31, 122, 109, 0.18), transparent 28rem),
        linear-gradient(135deg, #f7f3ea, #ece2d0);
      min-height: 100vh;
    }}
    main {{
      max-width: 980px;
      margin: 0 auto;
      padding: 4rem 1.5rem;
    }}
    h1 {{
      font-size: clamp(2.5rem, 7vw, 5.5rem);
      line-height: 0.92;
      margin: 0 0 1rem;
      letter-spacing: -0.05em;
    }}
    p {{
      color: var(--muted);
      font-size: 1.1rem;
      max-width: 720px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1rem;
      margin-top: 2rem;
    }}
    section {{
      background: color-mix(in srgb, var(--card) 86%, white);
      border: 1px solid var(--line);
      border-radius: 1.25rem;
      padding: 1.25rem;
      box-shadow: 0 1rem 2.5rem rgba(23, 32, 42, 0.08);
    }}
    h2 {{
      margin-top: 0;
    }}
    a {{
      color: var(--accent);
      font-weight: 700;
    }}
    ul {{
      columns: 2;
      padding-left: 1.2rem;
    }}
    li {{
      break-inside: avoid;
      margin: 0.35rem 0;
    }}
  </style>
</head>
<body>
  <main>
    <h1>IIS 2026 report portal</h1>
    <p>Samodejno zbrana validacijska porocila za podatkovni cevovod: Great Expectations za shemo in kakovost podatkov ter Evidently za drift porocila po merilnih mestih.</p>
    <div class="grid">
      <section>
        <h2>Great Expectations</h2>
        <p>Data Docs z rezultati validacije vseh merilnih mest.</p>
        <a href="gx/index.html">Odpri GX porocilo</a>
      </section>
      <section>
        <h2>Evidently</h2>
        <p>HTML porocila testov podatkov po merilnih mestih.</p>
        <ul>
          {evidently_links}
        </ul>
      </section>
    </div>
  </main>
</body>
</html>
"""
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")


def _handle_remove_readonly(function, path, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def build_report_site() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR, onerror=_handle_remove_readonly)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _copy_gx_reports()
    evidently_reports = _copy_evidently_reports()
    _write_index(evidently_reports)
    print(f"Report site built at {OUTPUT_DIR}", flush=True)


if __name__ == "__main__":
    build_report_site()
