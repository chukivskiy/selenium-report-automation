# Selenium Report Automation

Python automation project using Selenium WebDriver to interact with an HTML report containing a table and a Plotly doughnut chart.

## Requirements

- Python 3.10+
- Google Chrome
- Selenium

## Installation

```bash
pip install selenium
```

## Run

```bash
python selenium_report.py
```

## Output

Generated files are saved in the `output/` directory:

- `table.csv` — extracted table data.
- `doughnut0.csv`, `doughnut1.csv`, etc. — chart data for each filter state.
- `screenshot0.png`, `screenshot1.png`, etc. — chart screenshots.

The browser closes automatically after execution.
